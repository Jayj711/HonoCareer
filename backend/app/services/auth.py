"""鉴权服务：注册、登录、刷新令牌、登出。"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.error import BizError, ErrorCode
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    verify_password,
)
from app.db.models import RefreshTokens, Users
from app.schemas.auth import (
    LoginDTO,
    LoginVO,
    RefreshTokenDTO,
    RegisterDTO,
    RegisterVO,
    TokenVO,
    UserVO,
)


def _utcnow() -> datetime:
    """返回当前 UTC 时间（去掉时区信息），与数据库 DATETIME 列保持一致。"""
    # MySQL 的 DATETIME 不存时区，用 naive UTC 统一比较，避免 8 小时偏差
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def register(db: AsyncSession, dto: RegisterDTO) -> RegisterVO:
    """注册：校验账号唯一后创建用户，返回新用户 id。"""
    # 账号已存在则报冲突
    result = await db.execute(select(Users).where(Users.account == dto.account))
    if result.scalar_one_or_none() is not None:
        raise BizError(ErrorCode.CONFLICT, "账号已存在")

    # 注册时 username 默认等于账号；email / avatar / phone 暂不收集，保持 NULL
    user = Users(
        account=dto.account,
        username=dto.account,
        password_hash=hash_password(dto.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)  # 刷新后拿到数据库自增的 id

    return RegisterVO(userId=str(user.id))


async def login(db: AsyncSession, dto: LoginDTO) -> LoginVO:
    """登录：校验账号密码，签发一对 token 并把 refresh token 落库。"""
    # 查不到用户或密码不匹配，统一报「账号或密码错误」，
    # 故意不区分具体原因，防止外部探测哪些账号存在
    result = await db.execute(select(Users).where(Users.account == dto.account))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(dto.password, user.password_hash):
        raise BizError(ErrorCode.UNAUTHORIZED, "账号或密码错误")

    # 生成访问令牌 + 刷新令牌
    access_token = create_access_token(user.id)
    refresh_token = generate_refresh_token()

    # refresh token 存库，方便后续校验过期与登出吊销
    db.add(
        RefreshTokens(
            user_id=user.id,
            token=refresh_token,
            client_type=dto.clientType,
            expires_time=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()

    return LoginVO(
        accessToken=access_token,
        refreshToken=refresh_token,
        expiresIn=settings.access_token_expire_minutes * 60,  # 秒
        user=UserVO(
            userId=str(user.id),
            nickname=user.username,
            avatarUrl=user.avatar_url,
        ),
    )


async def refresh(db: AsyncSession, dto: RefreshTokenDTO) -> TokenVO:
    """刷新令牌：校验旧 refresh token 有效后，吊销旧的并签发新的（轮换）。"""
    now = _utcnow()

    # 只认「未吊销」的 refresh token（revoked_time IS NULL 表示还没登出）
    result = await db.execute(
        select(RefreshTokens).where(
            RefreshTokens.token == dto.refreshToken,
            RefreshTokens.revoked_time.is_(None),
        )
    )
    rt = result.scalar_one_or_none()
    if rt is None or rt.expires_time <= now:
        raise BizError(ErrorCode.UNAUTHORIZED, "刷新令牌无效或已过期")

    # 轮换第一步：把旧 token 标记为已吊销（rt 是会话中的对象，改属性 commit 时会自动 UPDATE）
    rt.revoked_time = now

    # 轮换第二步：签发一条全新的 refresh token 记录
    new_refresh = generate_refresh_token()
    db.add(
        RefreshTokens(
            user_id=rt.user_id,
            token=new_refresh,
            client_type=rt.client_type,
            expires_time=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()

    return TokenVO(
        accessToken=create_access_token(rt.user_id),
        refreshToken=new_refresh,
        expiresIn=settings.access_token_expire_minutes * 60,  # 秒
    )


async def logout(db: AsyncSession, user_id: int) -> None:
    """登出：吊销该用户所有未吊销的 refresh token，使旧 token 全部失效。"""
    # logout 请求只带 accessToken，无法知道具体是哪一条 refresh token，
    # 所以一次性吊销该用户全部未吊销的 refresh token
    await db.execute(
        update(RefreshTokens)
        .where(RefreshTokens.user_id == user_id, RefreshTokens.revoked_time.is_(None))
        .values(revoked_time=_utcnow())
    )
    await db.commit()
