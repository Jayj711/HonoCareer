"""数据库、DeepSeek、JWT 等配置。"""
import logging
import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量或 .env 文件读取。"""

    # 数据库
    database_url: str = (
        "mysql+asyncmy://root:CHANGE_ME@127.0.0.1:3306/Honocareer?charset=utf8mb4"
    )

    # JWT
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 1440

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


# ---------------------------------------------------------------------------
# 日志脱敏：自动打码敏感字段，防止 key / token 泄露到日志
# ---------------------------------------------------------------------------
_SENSITIVE_RE = re.compile(
    r'(?i)(\b(?:api[_-]?key|secret|token|password|authorization)\b)'
    r'(\s*[=:]\s*)'
    r'(?:"[^"]*"|\'[^\']*\'|[^\s,;]+)'
)

_BEARER_RE = re.compile(r'(?i)(\bAuthorization\b\s*[=:]\s*)Bearer\s+\S+')


def mask_secrets(text: str) -> str:
    """将文本中的敏感字段值替换为 ***。"""
    if not isinstance(text, str):
        return text
    text = _BEARER_RE.sub(r"\1Bearer ***", text)
    text = _SENSITIVE_RE.sub(r"\1\2***", text)
    return text


class MaskSensitiveDataFilter(logging.Filter):
    """日志过滤器：对 msg 与 args 做脱敏。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_secrets(record.msg)
        if record.args:
            record.args = tuple(
                mask_secrets(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """初始化日志并挂载脱敏过滤器。"""
    logging.basicConfig(level=level)
    mask_filter = MaskSensitiveDataFilter()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "app"):
        logging.getLogger(name).addFilter(mask_filter)
