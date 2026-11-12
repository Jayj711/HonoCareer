"""阶段推进状态机（纯函数，落库由 service 负责）。

阶段 6 起，会话阶段从内存态改为入库：当前阶段存在 ``sessions.stage``，
历史在 ``messages``，提问数从 assistant 的 question 消息计数推导。
因此这里只保留「纯函数」的推进规则，不再持有内存历史。
"""
from app.schemas.message import DefenseStage, InterviewStage, MessageKind

# 每轮提问上限：questioning 阶段问满即进入总结
MAX_QUESTIONS = 3


def decide_turn(
    mode: str, current_stage: str, question_count: int, max_questions: int = MAX_QUESTIONS
) -> tuple[str, str, str]:
    """根据当前阶段与已提问数，决定本轮 (阶段, assistant 消息 kind, 下一阶段)。

    返回三元组：
    - 本轮所处阶段（用于生成 Prompt 与落 assistant 消息的 stage）
    - 本轮 assistant 消息的 kind（question / feedback）
    - 本轮结束后的下一阶段（写回 sessions.stage）
    """
    if mode == "interview":
        if current_stage == InterviewStage.opening.value:
            return (
                InterviewStage.opening.value,
                MessageKind.question.value,
                InterviewStage.questioning.value,
            )
        if current_stage == InterviewStage.questioning.value:
            if question_count >= max_questions:
                return (
                    InterviewStage.summary.value,
                    MessageKind.feedback.value,
                    InterviewStage.ended.value,
                )
            return (
                InterviewStage.questioning.value,
                MessageKind.question.value,
                InterviewStage.questioning.value,
            )
        if current_stage == InterviewStage.summary.value:
            return (
                InterviewStage.summary.value,
                MessageKind.feedback.value,
                InterviewStage.ended.value,
            )
        return (
            InterviewStage.ended.value,
            MessageKind.feedback.value,
            InterviewStage.ended.value,
        )

    # defense
    if current_stage == DefenseStage.opening.value:
        return (
            DefenseStage.opening.value,
            MessageKind.question.value,
            DefenseStage.presentation.value,
        )
    if current_stage == DefenseStage.presentation.value:
        return (
            DefenseStage.presentation.value,
            MessageKind.question.value,
            DefenseStage.questioning.value,
        )
    if current_stage == DefenseStage.questioning.value:
        if question_count >= max_questions:
            return (
                DefenseStage.summary.value,
                MessageKind.feedback.value,
                DefenseStage.ended.value,
            )
        return (
            DefenseStage.questioning.value,
            MessageKind.question.value,
            DefenseStage.questioning.value,
        )
    if current_stage == DefenseStage.summary.value:
        return (
            DefenseStage.summary.value,
            MessageKind.feedback.value,
            DefenseStage.ended.value,
        )
    return (
        DefenseStage.ended.value,
        MessageKind.feedback.value,
        DefenseStage.ended.value,
    )


def is_ended(stage: str) -> bool:
    """判断阶段是否已结束。"""
    return stage in (InterviewStage.ended.value, DefenseStage.ended.value)
