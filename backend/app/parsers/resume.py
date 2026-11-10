"""PDF/Word 简历解析：抽取纯文本 + 用 DeepSeek 结构化。"""
import io
import json
import re

from docx import Document
from pypdf import PdfReader

from app.core.error import BizError, ErrorCode
from app.llm.deepseek import DeepSeekClient

# 允许的 MIME 类型 -> 落盘扩展名
ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

_SYSTEM_PROMPT = """你是简历信息抽取助手。请从用户给出的简历文本中抽取结构化信息，只输出一个 JSON 对象，不要输出任何解释、markdown 代码块或多余文字。

JSON 字段要求：
- education: 教育经历数组，每项为对象，字段可含 school(学校)、major(专业)、degree(学历)、startDate(起)、endDate(止) 等，缺失的字段不要写。
- projects: 项目/实习/工作经历数组，每项为对象，字段可含 name(名称)、role(角色)、description(描述)、startDate、endDate 等，缺失的字段不要写。
- skills: 技能字符串数组，如 ["Python", "MySQL"]。
- certificates: 证书字符串数组，如 ["CET-6"]。
- warnings: 解析警示字符串数组，指出简历中缺失或无法识别的重要信息（如无联系方式、学历不清等）。

某项没有内容时返回空数组 []。"""


def extract_text(file_name: str, content: bytes) -> str:
    """按文件类型抽取纯文本。"""
    if file_name.lower().endswith(".pdf") or content.startswith(b"%PDF"):
        return _extract_pdf(content)
    if file_name.lower().endswith(".docx"):
        return _extract_docx(content)
    raise BizError(ErrorCode.PARAM_ERROR, "不支持的文件类型，仅支持 PDF / Word")


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


async def structure_resume(text: str) -> dict:
    """用 DeepSeek 把简历纯文本结构化成 education/projects/skills/certificates/warnings。"""
    client = DeepSeekClient()
    if not client.configured:
        raise BizError(ErrorCode.INTERNAL_ERROR, "DeepSeek 未配置，无法解析简历")

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
        raise BizError(ErrorCode.INTERNAL_ERROR, "简历解析失败：模型返回无法解析") from exc
    if not isinstance(data, dict):
        raise BizError(ErrorCode.INTERNAL_ERROR, "简历解析失败：模型返回结构异常")
    return data


def _normalize(parsed: dict) -> dict:
    """把 LLM 返回字段规整成固定结构，保证类型安全。"""

    def _list_of_dict(v):
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

    def _list_of_str(v):
        return [str(x) for x in v] if isinstance(v, list) else []

    return {
        "education": _list_of_dict(parsed.get("education")),
        "projects": _list_of_dict(parsed.get("projects")),
        "skills": _list_of_str(parsed.get("skills")),
        "certificates": _list_of_str(parsed.get("certificates")),
        "warnings": _list_of_str(parsed.get("warnings")),
    }
