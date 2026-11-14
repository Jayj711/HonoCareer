"""弱项接口：标记、查询列表、取消标记。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.weak_point import WeakPointCreateDTO
from app.services import weak_point as weak_point_service

router = APIRouter(tags=["weak-points"])


@router.post("/api/v1/sessions/{session_id}/weak-points")
async def create_weak_point(
    session_id: int,
    dto: WeakPointCreateDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """标记弱项。"""
    vo = await weak_point_service.create_weak_point(db, user_id, session_id, dto)
    return Result.success(data=vo)


@router.get("/api/v1/weak-points")
async def list_weak_points(
    mode: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询弱项列表（普通数组，按 mode 可选过滤）。"""
    items = await weak_point_service.list_weak_points(db, user_id, mode)
    return Result.success(data=items)


@router.delete("/api/v1/weak-points/{weak_point_id}")
async def delete_weak_point(
    weak_point_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """取消弱项标记。"""
    await weak_point_service.delete_weak_point(db, user_id, weak_point_id)
    return Result.success()
