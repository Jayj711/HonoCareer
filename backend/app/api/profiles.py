"""画像接口：个人画像的增删改查、匹配与简历导入。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.profile import ProfileCreateDTO, ProfilePatchDTO, ResumeImportDTO
from app.services import profile as profile_service

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("")
async def list_profiles(
    type: str | None = Query(None),
    cursor: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """分页查询当前用户画像列表，可按类型过滤。"""
    page = await profile_service.list_profiles(db, user_id, type, cursor)
    return Result.success(data=page)


@router.post("")
async def create_profile(
    dto: ProfileCreateDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """新增画像，返回 profileId / completionStatus / version。"""
    vo = await profile_service.create_profile(db, user_id, dto)
    return Result.success(data=vo)


# 注意：/matches 必须定义在 /{profile_id} 之前，否则 "matches" 会被当成 profileId 捕获
@router.get("/matches")
async def list_matches(
    scene: str,
    mode: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """按场景匹配画像（阶段二简单版）。"""
    matches = await profile_service.match_profiles(db, user_id, scene, mode)
    return Result.success(data=matches)


@router.get("/{profile_id}")
async def get_profile(
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询单个画像详情。"""
    vo = await profile_service.get_profile(db, user_id, profile_id)
    return Result.success(data=vo)


@router.patch("/{profile_id}")
async def update_profile(
    profile_id: int,
    dto: ProfilePatchDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """更新画像（乐观锁版本校验，只更新传入字段）。"""
    await profile_service.update_profile(db, user_id, profile_id, dto)
    return Result.success()


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除画像。"""
    await profile_service.delete_profile(db, user_id, profile_id)
    return Result.success()


@router.post("/{profile_id}/resume-import")
async def import_from_resume(
    profile_id: int,
    dto: ResumeImportDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """从简历导入画像字段（阶段三实现）。"""
    vo = await profile_service.import_from_resume(db, user_id, profile_id, dto)
    return Result.success(data=vo)
