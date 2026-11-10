"""画像服务：个人画像的增删改查、匹配与简历导入。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error import BizError, ErrorCode
from app.db.models import Profiles, Resumes
from app.schemas.common import PageResult
from app.schemas.profile import (
    BaseInfo,
    ProfileCreateDTO,
    ProfileCreateVO,
    ProfileMatchVO,
    ProfilePatchDTO,
    ProfileVO,
    ResumeImportDTO,
    ResumeImportVO,
)

# 列表分页大小（每页最多返回多少条）
PAGE_SIZE = 20

# 场景 -> 画像类型映射：答辩的三种场景都归到 defense 画像（defense 与前三种互不复用）
SCENE_TO_TYPE = {
    "employment": "employment",
    "volunteer": "volunteer",
    "club": "club",
    "thesis": "defense",
    "research": "defense",
    "course": "defense",
}


def _to_vo(profile: Profiles) -> ProfileVO:
    """把 ORM 模型转成返回给前端的画像 VO。"""
    return ProfileVO(
        profileId=str(profile.id),
        type=profile.type,
        displayName=profile.display_name,
        baseInfo=BaseInfo.model_validate(profile.base_info) if profile.base_info else None,
        detail=profile.detail,
        completionStatus=profile.completion_status,
        version=profile.version,
        createdAt=profile.create_time,
        updatedAt=profile.update_time,
    )


async def _get_owned_profile(db: AsyncSession, user_id: int, profile_id: int) -> Profiles:
    """按 id 查画像，且必须是当前用户自己的；查不到统一抛「画像不存在」。"""
    result = await db.execute(
        select(Profiles).where(Profiles.id == profile_id, Profiles.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        # 不管是不存在还是属于别人，都报「画像不存在」，不泄露他人画像的存在性
        raise BizError(ErrorCode.NOT_FOUND, "画像不存在")
    return profile


async def list_profiles(
    db: AsyncSession, user_id: int, profile_type: str | None, cursor: str | None
) -> PageResult[ProfileVO]:
    """分页查询当前用户的画像列表（游标分页，按 id 倒序）。"""
    stmt = select(Profiles).where(Profiles.user_id == user_id)

    # 按类型过滤
    if profile_type is not None:
        stmt = stmt.where(Profiles.type == profile_type)

    # 游标：只取 id 小于 cursor（上一页最后一条的 id），实现向后翻页
    if cursor is not None:
        try:
            cursor_id = int(cursor)
        except ValueError:
            raise BizError(ErrorCode.PARAM_ERROR, "无效的分页游标")
        stmt = stmt.where(Profiles.id < cursor_id)

    # 多取一条，用来判断是否还有下一页
    stmt = stmt.order_by(Profiles.id.desc()).limit(PAGE_SIZE + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > PAGE_SIZE
    items = rows[:PAGE_SIZE]

    # 下一页的游标 = 本页最后一条的 id（还有下一页时才有值）
    next_cursor = str(items[-1].id) if has_more and items else None

    return PageResult[ProfileVO](
        items=[_to_vo(p) for p in items],
        nextCursor=next_cursor,
        hasMore=has_more,
    )


async def create_profile(db: AsyncSession, user_id: int, dto: ProfileCreateDTO) -> ProfileCreateVO:
    """新增画像：初始状态 draft、版本号 1。"""
    profile = Profiles(
        user_id=user_id,
        type=dto.type,
        display_name=dto.displayName,
        # baseInfo 可选：没传就存 NULL，传了就只存有值的字段（exclude_none 去掉 None 噪声）
        base_info=dto.baseInfo.model_dump(exclude_none=True) if dto.baseInfo else None,
        detail=dto.detail,
        completion_status="draft",
        version=1,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)  # 刷新后拿到数据库自增的 id

    return ProfileCreateVO(
        profileId=str(profile.id),
        completionStatus=profile.completion_status,
        version=profile.version,
    )


async def get_profile(db: AsyncSession, user_id: int, profile_id: int) -> ProfileVO:
    """查询单个画像详情。"""
    profile = await _get_owned_profile(db, user_id, profile_id)
    return _to_vo(profile)


async def update_profile(db: AsyncSession, user_id: int, profile_id: int, dto: ProfilePatchDTO) -> None:
    """更新画像（PATCH）：乐观锁校验版本，只更新传入的字段。"""
    profile = await _get_owned_profile(db, user_id, profile_id)

    # 乐观锁：版本对不上说明数据被别处改过，直接报冲突，让前端刷新后重试
    if dto.version != profile.version:
        raise BizError(ErrorCode.CONFLICT, "画像版本冲突，请刷新后重试")

    # 只更新传了值的字段（is not None 才改）
    if dto.displayName is not None:
        profile.display_name = dto.displayName
    if dto.baseInfo is not None:
        profile.base_info = dto.baseInfo.model_dump(exclude_none=True)
    if dto.detail is not None:
        profile.detail = dto.detail

    # 每次成功更新版本号 +1
    profile.version += 1
    await db.commit()


async def delete_profile(db: AsyncSession, user_id: int, profile_id: int) -> None:
    """删除画像。"""
    profile = await _get_owned_profile(db, user_id, profile_id)
    await db.delete(profile)
    await db.commit()


async def match_profiles(
    db: AsyncSession, user_id: int, scene: str, mode: str | None
) -> list[ProfileMatchVO]:
    """匹配画像（阶段二简单版）：按场景映射到画像类型，返回该类型全部画像。

    mode 暂不参与匹配，真正的检索 / 向量匹配留到阶段 8。
    """
    target_type = SCENE_TO_TYPE.get(scene)
    if target_type is None:
        raise BizError(ErrorCode.PARAM_ERROR, "无效的场景")

    result = await db.execute(
        select(Profiles).where(Profiles.user_id == user_id, Profiles.type == target_type)
    )
    profiles = result.scalars().all()

    # 简单版：matchReason 留空，isRecommended 一律 False
    return [
        ProfileMatchVO(profileId=str(p.id), type=p.type, isRecommended=False)
        for p in profiles
    ]


async def import_from_resume(
    db: AsyncSession, user_id: int, profile_id: int, dto: ResumeImportDTO
) -> ResumeImportVO:
    """从简历导入画像字段（阶段三实现）：把已确认简历的选中解析字段并入画像 detail。"""
    profile = await _get_owned_profile(db, user_id, profile_id)

    try:
        resume_id = int(dto.resumeId)
    except ValueError:
        raise BizError(ErrorCode.PARAM_ERROR, "无效的简历 ID")

    result = await db.execute(
        select(Resumes).where(Resumes.id == resume_id, Resumes.user_id == user_id)
    )
    resume = result.scalar_one_or_none()
    if resume is None:
        raise BizError(ErrorCode.NOT_FOUND, "简历不存在")
    if resume.status != "confirmed":
        raise BizError(ErrorCode.PARAM_ERROR, "简历未确认，无法导入")

    # 可选导入字段：education/projects/skills/certificates
    allowed = {"education", "projects", "skills", "certificates"}
    selected = [f for f in dto.selectedFields if f in allowed]

    # 把选中字段并入 profile.detail 的 resume 子键（映射细化留待联调）
    detail = dict(profile.detail or {})
    imported: dict = {}
    for field in selected:
        imported[field] = getattr(resume, f"parsed_{field}") or []
    detail["resume"] = imported

    profile.detail = detail
    profile.version += 1
    await db.commit()

    return ResumeImportVO(
        profileId=str(profile.id),
        version=profile.version,
        importedFields=selected,
    )
