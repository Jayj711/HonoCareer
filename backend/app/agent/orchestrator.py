"""Agent 总调度器：把状态机与大模型串起来处理一轮对话。"""
import uuid
from collections.abc import AsyncIterator

from app.agent.prompts import build_system_prompt
from app.agent.state_machine import (
    InterviewState,
    InterviewStateMachine,
    SessionType,
)
from app.llm.base import LLMClient


class Orchestrator:
    """会话内存态管理 + 单轮对话编排。"""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.sessions: dict[str, InterviewStateMachine] = {}

    def get_or_create(
        self, session_id: str | None, session_type: SessionType
    ) -> InterviewStateMachine:
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]
        sid = session_id or uuid.uuid4().hex
        machine = InterviewStateMachine(
            InterviewState(session_id=sid, session_type=session_type)
        )
        self.sessions[sid] = machine
        return machine

    async def handle_turn(
        self,
        session_id: str | None,
        message: str,
        session_type: SessionType = SessionType.INTERVIEW,
    ) -> AsyncIterator[dict]:
        """处理一轮用户输入，产出 SSE 事件 dict。

        事件：{"event": "phase"|"delta"|"done", "data": {...}}
        """
        machine = self.get_or_create(session_id, session_type)
        machine.record_user(message)

        system = build_system_prompt(machine.state)
        messages = [{"role": "system", "content": system}, *machine.state.history]

        yield {
            "event": "phase",
            "data": {
                "session_id": machine.state.session_id,
                "phase": machine.state.phase.value,
            },
        }

        buffer: list[str] = []
        async for delta in self.llm.stream_chat(messages):
            buffer.append(delta)
            yield {"event": "delta", "data": {"content": delta}}

        full = "".join(buffer)
        if full:
            machine.record_assistant(full)

        machine.advance()

        yield {"event": "done", "data": machine.state.to_dict()}
