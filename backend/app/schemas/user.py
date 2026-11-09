from datetime import datetime

from pydantic import BaseModel


class UserMeVO(BaseModel):
    """用户视图对象"""
    userId: str
    nickname: str | None = None
    avatarUrl: str | None = None
    phoneMasked: str | None = None
    emailMasked: str | None = None
    createdAt: datetime | None = None


class UserMePatchDTO(BaseModel):
    """用户输入对象（PATCH /users/me 的入参，字段都可选）"""
    nickname: str | None = None
    avatarUrl: str | None = None

