"""对话消息服务：发送（幂等 + 触发后台 Agent）、分页查询、SSE 事件流。"""
import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import run_response
from app.core.error import BizError, ErrorCode
from app.db import AsyncSessionFactory
from app.db.models import Messages, ResponseEvents, Responses
from app.schemas.common import PageResult
from app.schemas.message import (
    MessageKind,
    MessageRole,
    MessageSendDTO,
    MessageSendStatus,
    MessageSendVO,
    MessageVO,
    SSEEventType,
)
from app.services.session import _get_owned_session, _parse_id

PAGE_SIZE = 20
POLL_INTERVAL = 0.3  # SSE 轮询间隔（秒）

# 后台生成任务引用，防止被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def _to_vo(m: Messages) -> MessageVO:
    return MessageVO(
        messageId=str(m.id),
        sessionId=str(m.session_id),
        seq=m.seq,
        role=MessageRole(m.role),
        kind=MessageKind(m.kind),
        content=m.content,
        inputMode=m.input_mode,
        stage=m.stage,
        createdAt=m.create_time,
        asrConfidence=m.asr_confidence,
    )


async def _next_seq(db: AsyncSession, session_id: int) -> int:
    cur = (
        await db.execute(
            select(func.max(Messages.seq)).where(Messages.session_id == session_id)
        )
    ).scalar_one()
    return (cur or 0) + 1


def _schedule(session_id: int, user_message_id: int, response_id: int) -> None:
    """用 asyncio 任务触发后台生成，持有引用避免被 GC。"""
    task = asyncio.create_task(run_response(session_id, user_message_id, response_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def send_message(
    db: AsyncSession, user_id: int, session_id: int, dto: MessageSendDTO
) -> MessageSendVO:
    """发送消息：校验归属 → 幂等 → 落库 user 消息 + response(queued) → 触发后台生成。"""
    session = await _get_owned_session(db, user_id, session_id)
    if session.status != "active":
        raise BizError(ErrorCode.PARAM_ERROR, "会话不在进行中，无法发送消息")

    # 幂等：clientMessageId 全局唯一，已存在则直接返回原响应，不重复推进阶段
    existing = (
        await db.execute(
            select(Messages).where(Messages.client_message_id == dto.clientMessageId)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.session_id != session_id:
            raise BizError(ErrorCode.CONFLICT, "clientMessageId 已被占用")
        response = (
            await db.execute(
                select(Responses).where(Responses.user_message_id == existing.id)
            )
        ).scalar_one_or_none()
        if response is None:
            raise BizError(ErrorCode.INTERNAL_ERROR, "消息已存在但无对应响应")
        return MessageSendVO(
            userMessageId=str(existing.id),
            responseId=str(response.id),
            status=MessageSendStatus(response.status),
        )

    # 落库 user 消息
    user_msg = Messages(
        session_id=session_id,
        seq=await _next_seq(db, session_id),
        role=MessageRole.user.value,
        kind=dto.kind.value,
        content=dto.content,
        input_mode=dto.inputMode.value,
        audio_id=dto.audioId,
        asr_confidence=None,
        stage=session.stage,
        client_message_id=dto.clientMessageId,
    )
    db.add(user_msg)
    await db.flush()

    # 落库 response(queued) + 首条 queued 事件
    response = Responses(
        session_id=session_id,
        user_message_id=user_msg.id,
        status=MessageSendStatus.queued.value,
    )
    db.add(response)
    await db.flush()
    db.add(ResponseEvents(response_id=response.id, type=SSEEventType.queued.value, data={}))
    await db.commit()

    # 触发后台生成任务（立即返回，AI 内容走 SSE）
    _schedule(session_id, user_msg.id, response.id)

    return MessageSendVO(
        userMessageId=str(user_msg.id),
        responseId=str(response.id),
        status=MessageSendStatus.queued,
    )


async def list_messages(
    db: AsyncSession, user_id: int, session_id: int, cursor: str | None, limit: int
) -> PageResult[MessageVO]:
    """分页查询会话消息（游标分页，按 id 正序，符合聊天时间序）。"""
    await _get_owned_session(db, user_id, session_id)  # 归属校验
    stmt = select(Messages).where(Messages.session_id == session_id)
    if cursor is not None:
        cursor_id = _parse_id(cursor, "分页游标")
        stmt = stmt.where(Messages.id > cursor_id)
    stmt = stmt.order_by(Messages.id.asc()).limit(limit + 1)

    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None

    return PageResult[MessageVO](
        items=[_to_vo(m) for m in items],
        nextCursor=next_cursor,
        hasMore=has_more,
    )


async def check_response_owned(
    db: AsyncSession, user_id: int, session_id: int, response_id: int
) -> None:
    """校验响应归属（会话 + 响应都属于当前用户，且响应属于该会话）。"""
    await _get_owned_session(db, user_id, session_id)
    response = (
        await db.execute(
            select(Responses).where(
                Responses.id == response_id, Responses.session_id == session_id
            )
        )
    ).scalar_one_or_none()
    if response is None:
        raise BizError(ErrorCode.NOT_FOUND, "响应不存在")


def parse_last_event_id(raw: str | None) -> int:
    """解析 SSE 的 Last-Event-ID 头，非法一律 40001，缺省从 0 开始。"""
    if raw is None or raw == "":
        return 0
    return _parse_id(raw, "事件id")


def _format_sse(ev: ResponseEvents, response_id: int) -> str:
    """把一条 ResponseEvents 行转成标准 SSE 文本帧。"""
    payload = {
        "type": ev.type,
        "responseId": str(response_id),
        "eventId": str(ev.id),
        "timestamp": ev.create_time.isoformat() if ev.create_time else None,
        "data": ev.data or {},
    }
    return f"id: {ev.id}\nevent: {ev.type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_response_events(response_id: int, after_id: int) -> AsyncIterator[str]:
    """SSE 事件流：轮询 response_events，逐条产出文本帧，直到 done 或响应终态。

    每次轮询用独立 session（读最新已提交数据，避免长事务快照看不到新事件）。
    """
    while True:
        async with AsyncSessionFactory() as db:
            rows = list(
                (
                    await db.execute(
                        select(ResponseEvents)
                        .where(
                            ResponseEvents.response_id == response_id,
                            ResponseEvents.id > after_id,
                        )
                        .order_by(ResponseEvents.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            response = (
                await db.execute(select(Responses).where(Responses.id == response_id))
            ).scalar_one_or_none()

            done = False
            for ev in rows:
                after_id = ev.id
                yield _format_sse(ev, response_id)
                if ev.type == SSEEventType.done.value:
                    done = True

            if done:
                break
            if response is None or response.status in (
                MessageSendStatus.completed.value,
                MessageSendStatus.failed.value,
            ):
                break

        await asyncio.sleep(POLL_INTERVAL)
