"""面试/答辩阶段状态机。

状态对象用 Pydantic 建模并提供 to_dict / from_dict，当前只做内存态，
后续接数据库时只需追加 save / load，不必重写状态机。
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SessionType(str, Enum):
    INTERVIEW = "interview"  # 面试
    DEFENSE = "defense"  # 答辩


class Phase(str, Enum):
    GREETING = "greeting"  # 开场寒暄、确认目标
    INTERVIEWING = "interviewing"  # 提问
    FOLLOWUP = "followup"  # 追问
    SUMMARIZING = "summarizing"  # 总结反馈
    ENDED = "ended"  # 结束


class InterviewState(BaseModel):
    """会话状态，可序列化，便于后续落库。"""

    session_id: str
    session_type: SessionType = SessionType.INTERVIEW
    phase: Phase = Phase.GREETING
    question_index: int = 0
    max_questions: int = 3
    history: list[dict[str, str]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容的 dict。"""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InterviewState":
        """从 dict 反序列化。"""
        return cls.model_validate(data)


class InterviewStateMachine:
    """驱动状态在阶段间流转。"""

    def __init__(self, state: InterviewState) -> None:
        self.state = state

    @property
    def phase(self) -> Phase:
        return self.state.phase

    def record_user(self, content: str) -> None:
        self.state.history.append({"role": "user", "content": content})

    def record_assistant(self, content: str) -> None:
        self.state.history.append({"role": "assistant", "content": content})
        if self.state.phase == Phase.INTERVIEWING:
            self.state.question_index += 1

    def advance(self) -> Phase:
        """根据当前阶段推进到下一阶段（INTERVIEWING 阶段问满才收尾）。"""
        phase = self.state.phase
        if phase == Phase.GREETING:
            self.state.phase = Phase.INTERVIEWING
        elif phase == Phase.INTERVIEWING:
            if self.state.question_index >= self.state.max_questions:
                self.state.phase = Phase.SUMMARIZING
        elif phase == Phase.FOLLOWUP:
            self.state.phase = Phase.INTERVIEWING
        elif phase == Phase.SUMMARIZING:
            self.state.phase = Phase.ENDED
        # ENDED 保持不变
        return self.state.phase

    def go_followup(self) -> None:
        """进入追问阶段（当前由外部判断触发）。"""
        self.state.phase = Phase.FOLLOWUP
