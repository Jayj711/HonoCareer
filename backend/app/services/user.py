"""用户服务：查询 / 更新当前用户信息（含敏感字段脱敏）。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error import BizError, ErrorCode
from app.db.models import Users
from app.schemas.user import UserMePatchDTO, UserMeVO


def _mask_phone(phone: str | None) -> str | None:
    """手机号脱敏：138****1234。空值或过短原样返回。"""
    if not phone:
        return phone
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone


def _mask_email(email: str | None) -> str | None:
    """邮箱脱敏：a****@x.com。空值或格式异常原样返回。"""
    if not email or "@" not in email:
        return email
    # 按第一个 @ 拆成名字和域名两部分（split 只切一次，防止域名里也有 @）
    name, domain = email.split("@", 1)
    # 名字只留首字母 + ****，名字为空则全 ****
    name = name[0] + "****" if name else "****"
    return f"{name}@{domain}"


async def _get_user(db: AsyncSession, user_id: int) -> Users:
    """按 id 查用户，查不到抛 NOT_FOUND。get_me / update_me 共用。"""
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise BizError(ErrorCode.NOT_FOUND, "用户不存在")
    return user


async def get_me(db: AsyncSession, user_id: int) -> UserMeVO:
    """查询当前用户信息，phone / email 脱敏后返回。"""
    user = await _get_user(db, user_id)
    return UserMeVO(
        userId=str(user.id),
        nickname=user.username,
        avatarUrl=user.avatar_url,
        phoneMasked=_mask_phone(user.phone),
        emailMasked=_mask_email(user.email),
        createdAt=user.create_time,
    )


async def update_me(db: AsyncSession, user_id: int, dto: UserMePatchDTO) -> None:
    """更新当前用户信息（PATCH：只更新传入的字段，没传的不动）。"""
    user = await _get_user(db, user_id)

    # 只更新传了值的字段（is not None 才改）
    if dto.nickname is not None:
        user.username = dto.nickname
    if dto.avatarUrl is not None:
        user.avatar_url = dto.avatarUrl

    await db.commit()
