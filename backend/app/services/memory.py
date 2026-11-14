"""长期记忆服务：设置读写、记忆查询/清除、会话结束后的记忆提炼。"""
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.memory import generate_memories
from app.core.error import BizError, ErrorCode
from app.db.models import Memories, MemorySettings, Sessions
from app.schemas.memory import (
    MemoryItemVO,
    MemorySettingsPatchDTO,
    MemorySettingsVO,
    RetentionPolicy,
)

logger = logging.getLogger(__name__)


def _to_settings_vo(settings: MemorySettings | None) -> MemorySettingsVO:
    """无设置行时返回默认值（enabled=False、permanent），不落库。"""
    if settings is None:
        return MemorySettingsVO(enabled=False)
    return MemorySettingsVO(
        enabled=settings.enabled,
        retentionPolicy=settings.retention_policy or RetentionPolicy.permanent.value,
    )


def _to_item_vo(m: Memories) -> MemoryItemVO:
    return MemoryItemVO(
        memoryId=str(m.id),
        content=m.content,
        source=m.source_session_id,
        createdAt=m.create_time,
    )


async def _get_settings(db: AsyncSession, user_id: int) -> MemorySettings | None:
    return (
        await db.execute(select(MemorySettings).where(MemorySettings.user_id == user_id))
    ).scalar_one_or_none()


async def get_memory_settings(db: AsyncSession, user_id: int) -> MemorySettingsVO:
    """查询长期记忆设置（无行返回默认值，不落库）。"""
    return _to_settings_vo(await _get_settings(db, user_id))


async def update_memory_settings(
    db: AsyncSession, user_id: int, dto: MemorySettingsPatchDTO
) -> None:
    """修改长期记忆设置（upsert：有则改、无则建；只改 enabled）。"""
    settings = await _get_settings(db, user_id)
    if settings is None:
        settings = MemorySettings(
            user_id=user_id,
            enabled=dto.enabled,
            retention_policy=RetentionPolicy.permanent.value,
        )
        db.add(settings)
    else:
        settings.enabled = dto.enabled
    await db.commit()


async def list_memories(db: AsyncSession, user_id: int) -> list[MemoryItemVO]:
    """查询当前用户长期记忆摘要（普通数组，按 id 倒序）。"""
    rows = list(
        (
            await db.execute(
                select(Memories)
                .where(Memories.user_id == user_id)
                .order_by(Memories.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_item_vo(m) for m in rows]


async def clear_memories(db: AsyncSession, user_id: int) -> None:
    """清除当前用户全部长期记忆（不动 memory_settings 开关）。"""
    await db.execute(delete(Memories).where(Memories.user_id == user_id))
    await db.commit()


async def sync_memories_from_session(
    db: AsyncSession, session: Sessions, transcript: list[dict]
) -> None:
    """会话结束后提炼长期记忆（开关关闭则跳过；失败不影响主流程）。

    由 report.run_report 在生成评分卡后调用，共用同一 db session，
    新增的 Memories 行随 run_report 的 commit 一起落库。
    """
    try:
        settings = await _get_settings(db, session.user_id)
        if settings is None or not settings.enabled:
            return
        summaries = await generate_memories(
            session.mode, session.profile_snapshot, transcript
        )
        for content in summaries:
            db.add(
                Memories(
                    user_id=session.user_id,
                    content=content,
                    source_session_id=str(session.id),
                )
            )
    except Exception:  # noqa: BLE001 —— 记忆提炼失败不影响报告主流程
        logger.exception("长期记忆提炼失败，已跳过（不影响报告）")
