"""对话消息的请求/响应模型。"""
from pydantic import BaseModel, Field

from app.agent.state_machine import SessionType


class ChatRequest(BaseModel):
    """一次对话请求。session_id 为空则新建会话。"""

    session_id: str | None = None
    message: str = Field(..., min_length=1)
    session_type: SessionType = SessionType.INTERVIEW
