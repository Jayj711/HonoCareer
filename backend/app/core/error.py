class ErrorCode:
    """统一错误码：0 成功，其余分段。"""
    SUCCESS = 0
    PARAM_ERROR = 40001        # 参数错误
    UNAUTHORIZED = 40101       # 未登录 / token 缺失
    TOKEN_EXPIRED = 40102      # token 过期或无效
    FORBIDDEN = 40301          # 无权限
    NOT_FOUND = 40401          # 资源不存在
    CONFLICT = 40901           # 冲突（如账号已存在）
    INTERNAL_ERROR = 50001     # 服务器内部错误

class BizError(Exception):
    """业务异常：service层抛出，全局handler统一转成Result.fail"""
    def __init__(self,code:int,message:str):
        self.code = code
        self.message = message
        super().__init__(message)