"""Agent 总调度：把状态机、Prompt 与 LLM 串起来，后台生成一轮 AI 回复并落库 SSE 事件。

阶段 6 的两段式：POST /messages 只落库 queued 并立即返回，这里作为后台任务
真正调 LLM 流式生成，逐段写 response_events，最后落库 assistant 消息。
"""
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import build_system_prompt
from app.agent.state_machine import decide_turn
from app.db import AsyncSessionFactory
from app.db.models import (
    DefenseMaterials,
    Messages,
    Resumes,
    ResponseEvents,
    Responses,
    SessionMaterials,
    Sessions,
)
from app.llm.base import LLMClient
from app.llm.deepseek import DeepSeekClient
from app.schemas.message import InterviewStage, MessageKind, MessageRole, SSEEventType

# 单例 LLM 客户端（后续如需换 provider，只改这里）
_llm: LLMClient = DeepSeekClient()

HISTORY_LIMIT = 20  # 注入给 LLM 的最近消息条数


def _dump(obj) -> str:
    """JSON 结构转可读文本，空值返回空串。"""
    if obj in (None, "", [], {}):
        return ""
    return json.dumps(obj, ensure_ascii=False)


def _join(*parts: str) -> str:
    return "\n".join(p for p in parts if p)


async def _load_context(db: AsyncSession, session: Sessions) -> tuple[str, str]:
    """加载简历 / 答辩材料上下文文本（面试取简历，答辩取材料）。"""
    resume_text = ""
    if session.resume_id is not None:
        resume = (
            await db.execute(select(Resumes).where(Resumes.id == session.resume_id))
        ).scalar_one_or_none()
        if resume is not None:
            resume_text = _join(
                "教育经历：" + _dump(resume.parsed_education),
                "项目经历：" + _dump(resume.parsed_projects),
                "技能：" + _dump(resume.parsed_skills),
                "证书：" + _dump(resume.parsed_certificates),
            )

    material_text = ""
    material_ids = (
        (
            await db.execute(
                select(SessionMaterials.material_id).where(
                    SessionMaterials.session_id == session.id
                )
            )
        )
        .scalars()
        .all()
    )
    if material_ids:
        materials = (
            await db.execute(
                select(DefenseMaterials).where(DefenseMaterials.id.in_(material_ids))
            )
        ).scalars().all()
        chunks = []
        for m in materials:
            chunk = _join(
                f"主题：{m.parsed_topic or ''}",
                "大纲：" + _dump(m.parsed_outline),
                "关键点：" + _dump(m.parsed_key_points),
                "方法：" + _dump(m.parsed_methods),
                "结果：" + _dump(m.parsed_results),
            )
            if chunk:
                chunks.append(chunk)
        material_text = "\n\n".join(chunks)

    return resume_text, material_text


async def _load_history(db: AsyncSession, session_id: int) -> list[dict]:
    """加载最近消息，转成 LLM 需要的 [{"role", "content"}]（按时间正序）。"""
    rows = (
        (
            await db.execute(
                select(Messages)
                .where(Messages.session_id == session_id)
                .order_by(Messages.seq.desc())
                .limit(HISTORY_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [{"role": r.role, "content": r.content} for r in rows]


async def _count_questions(db: AsyncSession, session_id: int) -> int:
    """统计 questioning 阶段已问的问题数（assistant 的 question 消息数）。"""
    return (
        await db.execute(
            select(func.count())
            .select_from(Messages)
            .where(
                Messages.session_id == session_id,
                Messages.role == MessageRole.assistant.value,
                Messages.kind == MessageKind.question.value,
                Messages.stage == InterviewStage.questioning.value,
            )
        )
    ).scalar_one()


async def _write_event(
    db: AsyncSession, response_id: int, event_type: str, payload: dict | None = None
) -> None:
    """写一条 SSE 事件到 response_events。"""
    db.add(ResponseEvents(response_id=response_id, type=event_type, data=payload))
    await db.flush()


async def run_response(session_id: int, user_message_id: int, response_id: int) -> None:
    """后台任务：为一条用户消息生成 AI 回复，逐段写 SSE 事件并落库。

    使用独立 db session（请求级 session 在请求结束后已关闭）。
    任何异常都写 error 事件 + failed 状态，不向上抛。
    """
    try:
        async with AsyncSessionFactory() as db:
            session = (
                await db.execute(select(Sessions).where(Sessions.id == session_id))
            ).scalar_one_or_none()
            response = (
                await db.execute(select(Responses).where(Responses.id == response_id))
            ).scalar_one_or_none()
            if session is None or response is None:
                return

            # 1. thinking
            response.status = "thinking"
            await _write_event(db, response_id, SSEEventType.thinking.value)
            await db.commit()

            # 2. 计算本轮阶段与推进
            resume_text, material_text = await _load_context(db, session)
            history = await _load_history(db, session_id)
            question_count = await _count_questions(db, session_id)
            turn_stage, kind, next_stage = decide_turn(
                session.mode, session.stage or InterviewStage.opening.value, question_count
            )

            # 3. 阶段推进：写 stage_changed 事件 + 更新 sessions.stage
            if next_stage != session.stage:
                previous_stage = session.stage
                session.stage = next_stage
                await _write_event(
                    db,
                    response_id,
                    SSEEventType.stage_changed.value,
                    {"stage": next_stage, "previousStage": previous_stage},
                )
                await db.commit()

            # 4. 组装 prompt + 历史
            system = build_system_prompt(
                session.mode,
                session.scene,
                turn_stage,
                session.scene_config,
                session.profile_snapshot,
                resume_text,
                material_text,
            )
            messages = [{"role": "system", "content": system}, *history]

            # 5. 流式生成
            response.status = "generating"
            await db.commit()
            buffer: list[str] = []
            async for delta in _llm.stream_chat(messages):
                buffer.append(delta)
                await _write_event(
                    db, response_id, SSEEventType.message_delta.value, {"content": delta}
                )
                await db.commit()

            full = "".join(buffer)

            # 6. 落库 assistant 消息 + message_completed
            next_seq = (
                await db.execute(
                    select(func.max(Messages.seq)).where(Messages.session_id == session_id)
                )
            ).scalar_one()
            assistant = Messages(
                session_id=session_id,
                seq=(next_seq or 0) + 1,
                role=MessageRole.assistant.value,
                kind=kind,
                content=full,
                input_mode="text",
                stage=turn_stage,
                # assistant 消息无客户端幂等键，用响应 id 生成一个唯一占位
                client_message_id=f"assistant:{response_id}",
            )
            db.add(assistant)
            await db.flush()
            await _write_event(
                db,
                response_id,
                SSEEventType.message_completed.value,
                {"content": full, "messageId": str(assistant.id)},
            )

            # 7. 完成
            response.status = "completed"
            response.completed_time = datetime.now()
            await _write_event(db, response_id, SSEEventType.done.value)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 —— 后台任务必须兜底，不能让异常静默
        try:
            async with AsyncSessionFactory() as db:
                response = (
                    await db.execute(
                        select(Responses).where(Responses.id == response_id)
                    )
                ).scalar_one_or_none()
                if response is not None:
                    response.status = "failed"
                    await _write_event(
                        db,
                        response_id,
                        SSEEventType.error.value,
                        {"code": 50001, "message": str(exc)},
                    )
                    await _write_event(db, response_id, SSEEventType.done.value)
                    await db.commit()
        except Exception:  # noqa: BLE001 —— 兜底自身也不该再抛
            pass
