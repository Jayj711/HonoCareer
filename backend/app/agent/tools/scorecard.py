"""评分卡与建议生成：把会话上下文 + 转录交给 DeepSeek，结构化出维度评分/总结/行动项/弱项标签。

与简历/材料解析同构：chat(temperature=0) → 正则兜底取 JSON → 类型规整。
"""
import json
import re

from app.core.error import BizError, ErrorCode
from app.llm.deepseek import DeepSeekClient

# 封闭评分维度（dimension_key -> label）。报告维度与弱项 dimensionKey 共用同一套。
DIMENSIONS: dict[str, list[tuple[str, str]]] = {
    "interview": [
        ("communication", "沟通表达"),
        ("professional", "专业能力"),
        ("logic", "逻辑思维"),
        ("fit", "岗位匹配"),
        ("learning", "学习能力"),
    ],
    "defense": [
        ("topic_value", "选题价值"),
        ("research_depth", "研究深度"),
        ("expression", "答辩表达"),
        ("adaptability", "临场应变"),
    ],
}

_SYSTEM_PROMPT = """你是面试/答辩评分助手。根据给定的候选人上下文与对话转录，输出结构化评分。只输出一个 JSON 对象，不要输出任何解释、markdown 代码块或多余文字。

JSON 字段要求：
- overallScore: 整数，0-100 综合得分。
- summary: 字符串，一段总体评价。
- actionItems: 字符串数组，改进行动项。
- weakPointTags: 字符串数组，弱项标签（简短短语）。
- dimensions: 对象数组，每个元素：
  - key: 维度 key，只能从用户消息里给出的维度列表中选，不得自造。
  - score: 整数，0-100。
  - strengths: 字符串数组，亮点。
  - issues: 字符串数组，问题。
  - suggestions: 字符串数组，改进建议。
  - evidence: 字符串数组，支撑该评价的消息 id（从转录里的 [msg:xxx] 标记选，无则空数组）。"""


def dimensions_for(mode: str) -> list[tuple[str, str]]:
    """按模式返回维度列表，未知模式回退到面试维度。"""
    return DIMENSIONS.get(mode, DIMENSIONS["interview"])


def _parse_json(raw: str) -> dict:
    """容错解析 LLM 返回 JSON（容忍 markdown 代码块或前后多余文字）。"""
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BizError(ErrorCode.INTERNAL_ERROR, "评分报告生成失败：模型返回无法解析") from exc
    if not isinstance(data, dict):
        raise BizError(ErrorCode.INTERNAL_ERROR, "评分报告生成失败：模型返回结构异常")
    return data


def _normalize(parsed: dict, mode: str) -> dict:
    """把 LLM 返回规整成固定结构（key 规整到封闭枚举、类型安全）。"""
    dims = dimensions_for(mode)
    dims_map = dict(dims)
    allowed = set(dims_map)
    label_map = {label: key for key, label in dims}  # label -> key 反向，容错 LLM 返回中文名

    def _list_of_str(v):
        return [str(x) for x in v] if isinstance(v, list) else []

    def _clamp_score(v) -> int | None:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        return max(0, min(100, n))

    overall = _clamp_score(parsed.get("overallScore"))

    dimensions = []
    for d in parsed.get("dimensions") or []:
        if not isinstance(d, dict):
            continue
        raw_key = str(d.get("key", "")).strip()
        # key 可能是 label 或未知，规整到封闭 key；规整失败则跳过该维度
        key = raw_key if raw_key in allowed else label_map.get(raw_key)
        if key is None:
            continue
        score = _clamp_score(d.get("score"))
        dimensions.append({
            "key": key,
            "label": dims_map[key],
            "score": score if score is not None else 0,
            "strengths": _list_of_str(d.get("strengths")),
            "issues": _list_of_str(d.get("issues")),
            "suggestions": _list_of_str(d.get("suggestions")),
            "evidence": _list_of_str(d.get("evidence")),
        })

    return {
        "overall_score": overall,
        "summary": str(parsed.get("summary") or ""),
        "action_items": _list_of_str(parsed.get("actionItems")),
        "weak_point_tags": _list_of_str(parsed.get("weakPointTags")),
        "dimensions": dimensions,
    }


async def generate_scorecard(
    mode: str,
    scene: str,
    profile_snapshot: dict | None,
    resume_text: str,
    material_text: str,
    transcript: list[dict],
) -> dict:
    """用 DeepSeek 生成结构化评分卡。

    transcript: 消息转录列表，元素 {"id", "role", "content", "stage"}。
    """
    client = DeepSeekClient()
    if not client.configured:
        raise BizError(ErrorCode.INTERNAL_ERROR, "DeepSeek 未配置，无法生成评分报告")

    dims_desc = "\n".join(f"- {key}（{label}）" for key, label in dimensions_for(mode))

    context_parts = []
    if profile_snapshot:
        context_parts.append(f"候选人画像：{json.dumps(profile_snapshot, ensure_ascii=False)}")
    if resume_text:
        context_parts.append(f"候选人简历要点：\n{resume_text}")
    if material_text:
        context_parts.append(f"候选人答辩材料要点：\n{material_text}")
    context = "\n\n".join(context_parts) or "（无）"

    transcript_lines = [f"[msg:{m['id']}|{m['role']}] {m['content']}" for m in transcript]
    transcript_text = "\n".join(transcript_lines) or "（无）"

    user_prompt = (
        f"模式：{mode}\n"
        f"场景：{scene}\n"
        f"可用评分维度（key 只能从这里选）：\n{dims_desc}\n\n"
        f"候选人上下文：\n{context}\n\n"
        f"对话转录（引用消息时用 [msg:xxx] 里的 xxx 作为 evidence）：\n{transcript_text}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    raw = await client.chat(messages, temperature=0)
    return _normalize(_parse_json(raw), mode)
