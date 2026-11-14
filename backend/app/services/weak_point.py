"""弱项服务：标记、查询列表、取消标记。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.scorecard import dimensions_for
from app.core.error import BizError, ErrorCode
from app.db.models import Messages, Sessions, WeakPoints
from app.schemas.weak_point import WeakPointCreateDTO, WeakPointVO
from app.services.session import _get_owned_session, _parse_id

_VALID_MODES = ("interview", "defense")


def _to_vo(w: WeakPoints) -> WeakPointVO:
    return WeakPointVO(
        weakPointId=str(w.id),
        sessionId=str(w.session_id) if w.session_id is not None else None,
        dimensionKey=w.dimension_key,
        messageIds=w.message_ids or [],
        note=w.note,
        createdAt=w.create_time,
    )


async def create_weak_point(
    db: AsyncSession, user_id: int, session_id: int, dto: WeakPointCreateDTO
) -> WeakPointVO:
    """标记弱项：校验会话归属 + 维度 key + messageIds 属于该会话。"""
    session = await _get_owned_session(db, user_id, session_id)

    allowed = {key for key, _ in dimensions_for(session.mode)}
    if dto.dimensionKey not in allowed:
        raise BizError(ErrorCode.PARAM_ERROR, "无效的维度key")

    message_ids: list[str] | None = None
    if dto.messageIds:
        raw_ids = list(dict.fromkeys(dto.messageIds))
        parsed = [_parse_id(x, "消息id") for x in raw_ids]
        found = set(
            (
                await db.execute(
                    select(Messages.id).where(
                        Messages.id.in_(parsed), Messages.session_id == session_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(found) != len(parsed):
            raise BizError(ErrorCode.NOT_FOUND, "消息不存在")
        message_ids = raw_ids

    wp = WeakPoints(
        user_id=user_id,
        session_id=session_id,
        dimension_key=dto.dimensionKey,
        message_ids=message_ids,
        note=dto.note,
    )
    db.add(wp)
    await db.commit()
    await db.refresh(wp)
    return _to_vo(wp)


async def list_weak_points(
    db: AsyncSession, user_id: int, mode: str | None
) -> list[WeakPointVO]:
    """查询当前用户弱项列表（普通数组，按 mode 可选过滤）。"""
    if mode is not None and mode not in _VALID_MODES:
        raise BizError(ErrorCode.PARAM_ERROR, "无效的mode")
    stmt = select(WeakPoints).where(WeakPoints.user_id == user_id)
    if mode is not None:
        stmt = stmt.join(Sessions, WeakPoints.session_id == Sessions.id).where(
            Sessions.mode == mode
        )
    stmt = stmt.order_by(WeakPoints.id.desc())
    rows = list((await db.execute(stmt)).scalars().all())
    return [_to_vo(w) for w in rows]


async def delete_weak_point(
    db: AsyncSession, user_id: int, weak_point_id: int
) -> None:
    """取消弱项标记：归属校验后删除。"""
    wp = (
        await db.execute(
            select(WeakPoints).where(
                WeakPoints.id == weak_point_id, WeakPoints.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        raise BizError(ErrorCode.NOT_FOUND, "弱项不存在")
    await db.delete(wp)
    await db.commit()
