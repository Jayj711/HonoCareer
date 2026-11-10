"""会话服务：创建、列表、详情、修改、删除、结束。"""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error import BizError, ErrorCode
from app.db.models import (
    DefenseMaterials,
    Profiles,
    Resumes,
    SessionMaterials,
    Sessions,
)
from app.schemas.common import PageResult
from app.schemas.session import (
    Scene,
    SessionCreateDTO,
    SessionCreateVO,
    SessionDetailVO,
    SessionFinishDTO,
    SessionFinishVO,
    SessionMode,
    SessionPatchDTO,
    SessionStatus,
    SessionVO,
)

PAGE_SIZE = 20

# 场景 -> 画像类型映射（与 profile.matches 一致）：答辩三场景都归 defense 画像
_SCENE_TO_PROFILE_TYPE = {
    Scene.employment: "employment",
    Scene.volunteer: "volunteer",
    Scene.club: "club",
    Scene.thesis: "defense",
    Scene.research: "defense",
    Scene.course: "defense",
}

_INTERVIEW_SCENES = {Scene.employment, Scene.volunteer, Scene.club}
_DEFENSE_SCENES = {Scene.thesis, Scene.research, Scene.course}

# 开场阶段（InterviewStage / DefenseStage 接口文档「待确认」，暂用占位）
INITIAL_STAGE = "opening"


def _default_first_prompt(mode: SessionMode) -> str:
    """阶段 6 由 Agent 生成真实开场白，阶段 5 先返回简单占位。"""
    if mode == SessionMode.defense:
        return "你好，欢迎参加本次模拟答辩，我是你的答辩老师，请先介绍一下你的课题吧。"
    return "你好，欢迎参加本次模拟面试，我是你的面试官，请先做个自我介绍吧。"


def _to_create_vo(s: Sessions) -> SessionCreateVO:
    return SessionCreateVO(
        sessionId=str(s.id),
        mode=s.mode,
        scene=s.scene,
        status=s.status,
        stage=s.stage or INITIAL_STAGE,
        profileSnapshotVersion=s.profile_snapshot_version,
        createdAt=s.create_time,
        firstPrompt=s.first_prompt,
    )


def _to_vo(s: Sessions) -> SessionVO:
    return SessionVO(
        sessionId=str(s.id),
        title=s.title,
        mode=s.mode,
        scene=s.scene,
        status=s.status,
        startedAt=s.start_time,
        endedAt=s.end_time,
        overallScore=s.overall_score,
    )


def _to_detail_vo(s: Sessions) -> SessionDetailVO:
    snapshot = s.profile_snapshot or {}
    summary = (
        {
            "displayName": snapshot.get("displayName"),
            "type": snapshot.get("type"),
        }
        if snapshot
        else None
    )
    return SessionDetailVO(
        sessionId=str(s.id),
        mode=s.mode,
        scene=s.scene,
        sceneConfig=s.scene_config,
        profileSnapshotSummary=summary,
        stage=s.stage,
        status=s.status,
        messagePageUrl=f"/api/v1/sessions/{s.id}/messages",
        reportStatus=s.report_status,
    )


async def _get_owned_session(
    db: AsyncSession, user_id: int, session_id: int
) -> Sessions:
    """按 id 查会话，且必须是当前用户自己的；查不到统一抛「会话不存在」。"""
    result = await db.execute(
        select(Sessions).where(Sessions.id == session_id, Sessions.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise BizError(ErrorCode.NOT_FOUND, "会话不存在")
    return session


def _parse_id(raw: str, label: str) -> int:
    """把对外的字符串主键转成 int，非法直接抛 40001（避免裸 500 绕过统一响应）。"""
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise BizError(ErrorCode.PARAM_ERROR, f"无效的{label}")


async def create_session(
    db: AsyncSession, user_id: int, dto: SessionCreateDTO
) -> SessionCreateVO:
    """创建会话：校验画像/简历/材料归属，快照画像，落库并关联材料。"""
    # 1. mode 与 scene 一致性校验
    if dto.mode == SessionMode.interview and dto.scene not in _INTERVIEW_SCENES:
        raise BizError(ErrorCode.PARAM_ERROR, "面试模式与场景不匹配")
    if dto.mode == SessionMode.defense and dto.scene not in _DEFENSE_SCENES:
        raise BizError(ErrorCode.PARAM_ERROR, "答辩模式与场景不匹配")

    # 2. 幂等：clientSessionId 全局唯一，已存在则直接返回原会话
    existing = (
        await db.execute(
            select(Sessions).where(Sessions.client_session_id == dto.clientSessionId)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id != user_id:
            raise BizError(ErrorCode.CONFLICT, "clientSessionId 已被占用")
        return _to_create_vo(existing)

    # 3. 校验画像归属 + 类型匹配
    profile_id = _parse_id(dto.profileId, "画像id")
    profile = (
        await db.execute(
            select(Profiles).where(
                Profiles.id == profile_id, Profiles.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        raise BizError(ErrorCode.NOT_FOUND, "画像不存在")
    if profile.type != _SCENE_TO_PROFILE_TYPE[dto.scene]:
        raise BizError(ErrorCode.PARAM_ERROR, "画像类型与场景不匹配")

    # 4. 校验简历归属（可选）
    resume_id: int | None = None
    if dto.resumeId is not None:
        resume_id = _parse_id(dto.resumeId, "简历id")
        resume = (
            await db.execute(
                select(Resumes).where(
                    Resumes.id == resume_id, Resumes.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if resume is None:
            raise BizError(ErrorCode.NOT_FOUND, "简历不存在")

    # 5. 校验材料归属（可选），去重后逐个转 int
    material_ids: list[int] = []
    if dto.materialIds:
        material_ids = list(dict.fromkeys(_parse_id(raw, "材料id") for raw in dto.materialIds))
        result = await db.execute(
            select(DefenseMaterials.id).where(
                DefenseMaterials.id.in_(material_ids),
                DefenseMaterials.user_id == user_id,
            )
        )
        found = set(result.scalars().all())
        if len(found) != len(material_ids):
            raise BizError(ErrorCode.NOT_FOUND, "材料不存在")

    # 6. 快照画像（冻结画像，避免会话被后续画像编辑影响）
    profile_snapshot = {
        "type": profile.type,
        "displayName": profile.display_name,
        "baseInfo": profile.base_info,
        "detail": profile.detail,
    }

    session = Sessions(
        user_id=user_id,
        mode=dto.mode.value,
        scene=dto.scene.value,
        scene_config=(
            dto.sceneConfig.model_dump(exclude_none=True) if dto.sceneConfig else None
        ),
        profile_id=profile_id,
        profile_snapshot=profile_snapshot,
        profile_snapshot_version=profile.version,
        resume_id=resume_id,
        modality=dto.modality.value,
        title=None,
        status=SessionStatus.active.value,
        stage=INITIAL_STAGE,
        client_session_id=dto.clientSessionId,
        first_prompt=_default_first_prompt(dto.mode),
        overall_score=None,
        report_status=None,
        start_time=datetime.now(),
        end_time=None,
    )
    db.add(session)
    await db.flush()  # 拿到 session.id 以关联材料

    # 7. 关联材料
    for mid in material_ids:
        db.add(SessionMaterials(session_id=session.id, material_id=mid))

    await db.commit()
    await db.refresh(session)
    return _to_create_vo(session)


async def list_sessions(
    db: AsyncSession,
    user_id: int,
    mode: str | None,
    status: str | None,
    cursor: str | None,
) -> PageResult[SessionVO]:
    """分页查询当前用户会话列表（游标分页，按 id 倒序，可按 mode/status 过滤）。"""
    stmt = select(Sessions).where(Sessions.user_id == user_id)
    if mode is not None:
        stmt = stmt.where(Sessions.mode == mode)
    if status is not None:
        stmt = stmt.where(Sessions.status == status)
    if cursor is not None:
        cursor_id = _parse_id(cursor, "分页游标")
        stmt = stmt.where(Sessions.id < cursor_id)
    stmt = stmt.order_by(Sessions.id.desc()).limit(PAGE_SIZE + 1)

    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > PAGE_SIZE
    items = rows[:PAGE_SIZE]
    next_cursor = str(items[-1].id) if has_more and items else None

    return PageResult[SessionVO](
        items=[_to_vo(s) for s in items],
        nextCursor=next_cursor,
        hasMore=has_more,
    )


async def get_session(
    db: AsyncSession, user_id: int, session_id: int
) -> SessionDetailVO:
    """查询会话详情。"""
    session = await _get_owned_session(db, user_id, session_id)
    return _to_detail_vo(session)


async def patch_session(
    db: AsyncSession, user_id: int, session_id: int, dto: SessionPatchDTO
) -> None:
    """修改会话：只更新传入的字段（title / modality）。"""
    session = await _get_owned_session(db, user_id, session_id)
    if dto.title is not None:
        if not dto.title.strip():
            raise BizError(ErrorCode.PARAM_ERROR, "标题不能为空")
        session.title = dto.title.strip()
    if dto.modality is not None:
        session.modality = dto.modality.value
    await db.commit()


async def delete_session(db: AsyncSession, user_id: int, session_id: int) -> None:
    """删除会话：先清关联材料，再删会话（避免外键约束阻断删除）。"""
    session = await _get_owned_session(db, user_id, session_id)
    await db.execute(
        delete(SessionMaterials).where(SessionMaterials.session_id == session_id)
    )
    await db.delete(session)
    await db.commit()


async def finish_session(
    db: AsyncSession, user_id: int, session_id: int, dto: SessionFinishDTO
) -> SessionFinishVO:
    """结束会话：active -> completed（报告生成留到阶段 7，届时先置 generating_report）。"""
    session = await _get_owned_session(db, user_id, session_id)
    if session.status != SessionStatus.active.value:
        raise BizError(ErrorCode.PARAM_ERROR, "会话不在进行中，无法结束")
    session.status = SessionStatus.completed.value
    session.end_time = datetime.now()
    await db.commit()
    return SessionFinishVO(status=SessionStatus.completed, reportId=None)
