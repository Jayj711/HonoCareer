from pydantic import BaseModel

class LoginDTO(BaseModel):
    """登录DTO"""
    account: str
    password: str
    clientType: str

class UserVO(BaseModel):
    """用户视图对象"""
    userId: str
    nickname: str | None = None
    avatarUrl: str | None = None

class LoginVO(BaseModel):
    """登录视图对象"""
    accessToken: str
    refreshToken: str
    user: UserVO
    expiresIn: int

class RefreshTokenDTO(BaseModel):
    """刷新令牌DTO"""
    refreshToken: str

class TokenVO(BaseModel):
    """令牌视图对象"""
    accessToken: str
    refreshToken: str
    expiresIn: int

class RegisterDTO(BaseModel):
    """注册DTO"""
    account: str
    password: str
    #verificationCode 待定发送验证码接口

class RegisterVO(BaseModel):
    userId: str

