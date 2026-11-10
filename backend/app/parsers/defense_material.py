"""PDF/Word/PPT 答辩材料解析：抽取纯文本 + 用 DeepSeek 结构化。"""
import io
import json
import re

from docx import Document
from pptx import Presentation
from pypdf import PdfReader

from app.core.error import BizError, ErrorCode
from app.llm.deepseek import DeepSeekClient

# 允许的 MIME 类型 -> 落盘扩展名
ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}

_SYSTEM_PROMPT = """你是答辩材料信息抽取助手。请从用户给出的答辩材料（论文/PPT/报告等）文本中抽取结构化信息，只输出一个 JSON 对象，不要输出任何解释、markdown 代码块或多余文字。

JSON 字段要求：
- topic: 答辩主题字符串，如论文题目或项目名称。
- outline: 内容大纲字符串数组，按顺序列出章节/小节标题。
- keyPoints: 关键要点字符串数组。
- methods: 研究方法/技术方案字符串数组。
- results: 研究成果/结论字符串数组。
- possibleQuestions: 可能被问到的问题字符串数组。
- warnings: 解析警示字符串数组，指出材料中缺失或无法识别的重要信息。

某项没有内容时返回空数组 []，topic 没有则返回空字符串 ""。"""


def extract_text(file_name: str, content: bytes) -> str:
    """按文件类型抽取纯文本。"""
    if file_name.lower().endswith(".pdf") or content.startswith(b"%PDF"):
        return _extract_pdf(content)
    if file_name.lower().endswith(".docx"):
        return _extract_docx(content)
    if file_name.lower().endswith(".pptx"):
        return _extract_pptx(content)
    raise BizError(ErrorCode.PARAM_ERROR, "不支持的文件类型，仅支持 PDF / Word / PPT")


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells if cell.text.strip())
    return "\n".join(parts)


def _extract_pptx(content: bytes) -> str:
    prs = Presentation(io.BytesIO(content))
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                text = "".join(run.text for run in para.runs)
                if text.strip():
                    parts.append(text)
    return "\n".join(parts)


async def structure_defense_material(text: str) -> dict:
    """用 DeepSeek 把答辩材料纯文本结构化成 topic/outline/keyPoints/methods/results/possibleQuestions/warnings。"""
    client = DeepSeekClient()
    if not client.configured:
        raise BizError(ErrorCode.INTERNAL_ERROR, "DeepSeek 未配置，无法解析答辩材料")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    raw = await client.chat(messages, temperature=0)
    parsed = _parse_json(raw)
    return _normalize(parsed)


def _parse_json(raw: str) -> dict:
    """容错地把 LLM 返回文本解析成 dict（容忍 markdown 代码块包裹或前后多余文字）。"""
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BizError(ErrorCode.INTERNAL_ERROR, "答辩材料解析失败：模型返回无法解析") from exc
    if not isinstance(data, dict):
        raise BizError(ErrorCode.INTERNAL_ERROR, "答辩材料解析失败：模型返回结构异常")
    return data


def _normalize(parsed: dict) -> dict:
    """把 LLM 返回字段规整成固定结构（内部键与 DB 列名对齐），保证类型安全。"""

    def _list_of_str(v):
        return [str(x) for x in v] if isinstance(v, list) else []

    topic = parsed.get("topic")
    return {
        "topic": str(topic).strip() if topic else "",
        "outline": _list_of_str(parsed.get("outline")),
        "key_points": _list_of_str(parsed.get("keyPoints")),
        "methods": _list_of_str(parsed.get("methods")),
        "results": _list_of_str(parsed.get("results")),
        "possible_questions": _list_of_str(parsed.get("possibleQuestions")),
        "warnings": _list_of_str(parsed.get("warnings")),
    }
