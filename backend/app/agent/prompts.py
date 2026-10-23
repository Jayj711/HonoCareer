"""面试官、评委、评分 Prompt。"""
from app.agent.state_machine import InterviewState, Phase, SessionType


def build_system_prompt(state: InterviewState) -> str:
    """根据会话类型与当前阶段生成系统提示词。"""
    if state.session_type == SessionType.DEFENSE:
        base = "你是专业答辩评委，围绕候选人提交的答辩材料进行提问与评价。"
    else:
        base = "你是专业面试官，围绕候选人的目标岗位进行结构化面试。"

    phase_hint = {
        Phase.GREETING: "先简短自我介绍，并询问候选人的目标岗位或答辩主题。",
        Phase.INTERVIEWING: f"继续提问（这是第 {state.question_index + 1} 个问题），一次只问一个问题。",
        Phase.FOLLOWUP: "针对上一轮回答深入追问，追问要具体、有针对性。",
        Phase.SUMMARIZING: "面试结束，总结候选人表现，给出简短、具体的反馈与建议。",
        Phase.ENDED: "面试已结束，礼貌收尾。",
    }
    return f"{base}\n{phase_hint[state.phase]}"
