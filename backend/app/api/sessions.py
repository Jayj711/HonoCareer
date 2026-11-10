"""场景选择与会话接口：创建、列表、详情、修改、删除、结束。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.session import (
    SessionCreateDTO,
    SessionFinishDTO,
    SessionPatchDTO,
)
from app.services import session as session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("")
async def create_session(
    dto: SessionCreateDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """创建模拟会话。"""
    vo = await session_service.create_session(db, user_id, dto)
    return Result.success(data=vo)


@router.get("")
async def list_sessions(
    mode: str | None = Query(None),
    status: str | None = Query(None),
    cursor: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """分页查询当前用户会话列表。"""
    page = await session_service.list_sessions(db, user_id, mode, status, cursor)
    return Result.success(data=page)


@router.get("/{session_id}")
async def get_session(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询会话详情。"""
    vo = await session_service.get_session(db, user_id, session_id)
    return Result.success(data=vo)


@router.patch("/{session_id}")
async def patch_session(
    session_id: int,
    dto: SessionPatchDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """修改会话（标题 / 交互形态）。"""
    await session_service.patch_session(db, user_id, session_id, dto)
    return Result.success()


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除会话。"""
    await session_service.delete_session(db, user_id, session_id)
    return Result.success()


@router.post("/{session_id}/finish")
async def finish_session(
    session_id: int,
    dto: SessionFinishDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """结束会话。"""
    vo = await session_service.finish_session(db, user_id, session_id, dto)
    return Result.success(data=vo)
