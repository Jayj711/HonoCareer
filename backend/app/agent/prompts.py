"""面试官 / 评委 Prompt 与上下文拼接。"""
import json


def _dump(obj) -> str:
    """把 JSON 结构安全转成可读文本（空值返回空串）。"""
    if obj in (None, "", [], {}):
        return ""
    return json.dumps(obj, ensure_ascii=False)


def build_system_prompt(
    mode: str,
    scene: str,
    stage: str,
    scene_config: dict | None,
    profile_snapshot: dict | None,
    resume_text: str,
    material_text: str,
) -> str:
    """根据会话类型、当前阶段与注入的上下文生成 system prompt。"""
    if mode == "defense":
        role = "你是专业的答辩评委，围绕候选人提交的课题/答辩材料进行提问与评价。"
    else:
        role = "你是专业的面试官，围绕候选人的目标岗位进行结构化面试。"

    stage_hint = {
        "opening": "先简短开场，然后提出第一个问题，引导候选人开始。",
        "presentation": "请候选人陈述其课题/研究内容，并认真倾听。",
        "questioning": "继续提问，一次只问一个具体问题，问题要有针对性。",
        "summary": "总结候选人表现，给出简短、具体的反馈与改进建议。",
        "ended": "面试/答辩已结束，礼貌收尾。",
    }.get(stage, "继续对话。")

    parts = [role, f"当前阶段：{stage}", f"本阶段指引：{stage_hint}"]

    if scene_config:
        parts.append(f"场景配置：{_dump(scene_config)}")
    if profile_snapshot:
        parts.append(f"候选人画像：{_dump(profile_snapshot)}")
    if resume_text:
        parts.append(f"候选人简历要点：\n{resume_text}")
    if material_text:
        parts.append(f"候选人答辩材料要点：\n{material_text}")

    return "\n\n".join(parts)
