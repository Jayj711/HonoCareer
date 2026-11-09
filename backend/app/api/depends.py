"""公共依赖：从请求头解析当前用户身份。"""
import jwt
from fastapi import Header

from app.core.error import BizError, ErrorCode
from app.core.security import decode_access_token


def get_current_user_id(authorization: str | None = Header(None)) -> int:
    """FastAPI 依赖：校验 ``Authorization: Bearer {token}``，返回当前用户 id。

    校验失败抛 BizError，由全局异常处理器统一转成 Result.fail。
    """
    # 1. 请求头缺失，或不是 "Bearer " 开头 → 未登录
    if not authorization or not authorization.startswith("Bearer "):
        raise BizError(ErrorCode.UNAUTHORIZED, "未登录")

    # 2. 切掉 "Bearer " 前缀，只留真正的 token 字符串
    token = authorization[len("Bearer "):]

    # 3. 解码校验：过期 → 40102；其它无效（签名错/被篡改/格式错）→ 40101
    #    注意顺序：ExpiredSignatureError 是 InvalidTokenError 的子类，必须先捕获
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise BizError(ErrorCode.TOKEN_EXPIRED, "登录已过期")
    except jwt.InvalidTokenError:
        raise BizError(ErrorCode.UNAUTHORIZED, "无效的访问令牌")

    # 4. 从 payload 的 sub 取回用户 id（签发时存的是字符串，这里转回 int）
    return int(payload["sub"])
