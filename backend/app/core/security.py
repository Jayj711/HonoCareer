"""密码哈希与 JWT 令牌工具。"""
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希，返回可入库的哈希字符串。"""
    # bcrypt 只接受字节，所以先 encode；哈希结果再 decode 回字符串存入数据库
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配（登录时用）。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    """创建 JWT 访问令牌。

    payload 放三个标准字段：
    - sub：主体，存用户 id（JWT 规范里 sub 是字符串）
    - iat：签发时间
    - exp：过期时间，PyJWT 解码时会据此判断是否过期
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """解码并校验 JWT 访问令牌。

    验签失败、被篡改或过期时会抛 jwt 相关异常，由调用方捕获区分错误码。
    """
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


def generate_refresh_token() -> str:
    """生成不透明的刷新令牌（密码学安全的随机串，无需带信息）。"""
    return secrets.token_urlsafe(32)
