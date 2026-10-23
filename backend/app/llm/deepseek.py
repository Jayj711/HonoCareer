"""DeepSeek API 实现（OpenAI 兼容接口）。"""
import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.llm.base import LLMClient


class DeepSeekClient(LLMClient):
    """通过 OpenAI 兼容的 /chat/completions 接口调用 DeepSeek。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True, **kwargs}
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", self._endpoint(), json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if content:
                        yield content

    async def chat(self, messages: list[dict], **kwargs) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False, **kwargs}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._endpoint(), json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
