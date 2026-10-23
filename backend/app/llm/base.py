"""统一的大模型调用接口。"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMClient(ABC):
    """大模型客户端统一接口，便于替换不同 provider。"""

    @abstractmethod
    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """流式对话，逐段产出文本增量。"""

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """非流式对话，返回完整回复。"""
