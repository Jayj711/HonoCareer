"""对话消息接口：发送、查询、订阅 AI 响应流式事件（SSE）。"""
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.message import MessageSendDTO
from app.services import message as message_service

router = APIRouter(prefix="/api/v1/sessions", tags=["messages"])


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    dto: MessageSendDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """发送会话消息：立即返回 responseId，AI 内容走 SSE。"""
    vo = await message_service.send_message(db, user_id, session_id, dto)
    return Result.success(data=vo)


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: int,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """分页查询会话消息（游标分页，按时间正序）。"""
    page = await message_service.list_messages(db, user_id, session_id, cursor, limit)
    return Result.success(data=page)


@router.get("/{session_id}/responses/{response_id}/events")
async def subscribe_events(
    session_id: int,
    response_id: int,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """订阅 AI 响应流式事件（SSE），支持 Last-Event-ID 断点续传。"""
    await message_service.check_response_owned(db, user_id, session_id, response_id)
    after_id = message_service.parse_last_event_id(last_event_id)
    return StreamingResponse(
        message_service.stream_response_events(response_id, after_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
