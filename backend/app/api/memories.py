"""长期记忆接口：设置读写、记忆查询/清除。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.memory import MemorySettingsPatchDTO
from app.services import memory as memory_service

router = APIRouter(prefix="/api/v1/users/me", tags=["memories"])


@router.get("/memory-settings")
async def get_memory_settings(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询长期记忆设置。"""
    vo = await memory_service.get_memory_settings(db, user_id)
    return Result.success(data=vo)


@router.patch("/memory-settings")
async def update_memory_settings(
    dto: MemorySettingsPatchDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """修改长期记忆设置。"""
    await memory_service.update_memory_settings(db, user_id, dto)
    return Result.success()


@router.get("/memories")
async def list_memories(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询长期记忆摘要（普通数组）。"""
    items = await memory_service.list_memories(db, user_id)
    return Result.success(data=items)


@router.delete("/memories")
async def clear_memories(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """清除全部长期记忆。"""
    await memory_service.clear_memories(db, user_id)
    return Result.success()
