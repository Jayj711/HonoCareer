"""当前用户接口：查询与更新个人资料。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.user import UserMePatchDTO
from app.services import user as user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
async def get_me(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息（phone / email 脱敏）。"""
    vo = await user_service.get_me(db, user_id)
    return Result.success(data=vo)


@router.patch("/me")
async def update_me(
    dto: UserMePatchDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户信息（PATCH：只更新传入的字段）。"""
    await user_service.update_me(db, user_id, dto)
    return Result.success()
