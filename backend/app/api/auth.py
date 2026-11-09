"""鉴权接口：登录、刷新令牌、登出、注册。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.auth import LoginDTO, RefreshTokenDTO, RegisterDTO
from app.schemas.common import Result
from app.services import auth as auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login(dto: LoginDTO, db: AsyncSession = Depends(get_db)):
    """登录：校验账号密码，返回 accessToken / refreshToken / 用户信息。"""
    vo = await auth_service.login(db, dto)
    return Result.success(data=vo)


@router.post("/refresh")
async def refresh(dto: RefreshTokenDTO, db: AsyncSession = Depends(get_db)):
    """刷新令牌：用旧 refreshToken 换一对新令牌（轮换）。"""
    vo = await auth_service.refresh(db, dto)
    return Result.success(data=vo)


@router.post("/logout")
async def logout(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """登出：吊销当前用户所有 refresh token，旧 token 全部失效。"""
    await auth_service.logout(db, user_id)
    return Result.success()


@router.post("/register")
async def register(dto: RegisterDTO, db: AsyncSession = Depends(get_db)):
    """注册：创建新用户，返回 userId。"""
    vo = await auth_service.register(db, dto)
    return Result.success(data=vo)
