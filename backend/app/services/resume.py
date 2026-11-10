"""简历服务：上传、解析、编辑、确认、删除。"""
import secrets
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error import BizError, ErrorCode
from app.db.models import Resumes
from app.parsers import resume as resume_parser
from app.schemas.common import PageResult
from app.schemas.resume import (
    ParseJobVO,
    ParseResultVO,
    ResumeContentPatchDTO,
    ResumeDTO,
    ResumeVO,
)

PAGE_SIZE = 20
MAX_FILE_SIZE = 10 * 1024 * 1024  # 单个简历最大 10MB

# 上传根目录：backend/uploads/resumes（相对 backend 根，避免受启动时 CWD 影响）
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "resumes"
UPLOAD_DIR_REL = "uploads/resumes"


def _to_dto(r: Resumes) -> ResumeDTO:
    """把 ORM 模型转成返回给前端的简历 VO。"""
    return ResumeDTO(
        resumeId=str(r.id),
        fileName=r.file_name,
        mimeType=r.mime_type,
        size=r.size,
        status=r.status,
        createdAt=r.create_time,
    )


async def _get_owned_resume(db: AsyncSession, user_id: int, resume_id: int) -> Resumes:
    """按 id 查简历，且必须是当前用户自己的；查不到统一抛「简历不存在」。"""
    result = await db.execute(
        select(Resumes).where(Resumes.id == resume_id, Resumes.user_id == user_id)
    )
    resume = result.scalar_one_or_none()
    if resume is None:
        raise BizError(ErrorCode.NOT_FOUND, "简历不存在")
    return resume


async def upload_resume(
    db: AsyncSession, user_id: int, file_name: str, mime_type: str, content: bytes
) -> ResumeVO:
    """上传简历：校验类型与大小，落盘并建记录（初始状态 uploaded）。"""
    if not file_name.strip():
        raise BizError(ErrorCode.PARAM_ERROR, "文件名不能为空")

    ext = resume_parser.ALLOWED_MIME_TYPES.get(mime_type)
    if ext is None:
        raise BizError(ErrorCode.PARAM_ERROR, "仅支持 PDF / Word 简历")

    if len(content) > MAX_FILE_SIZE:
        raise BizError(ErrorCode.PARAM_ERROR, "简历文件过大，最大 10MB")

    # 落盘：用随机文件名避免路径冲突 / 覆盖
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(content)

    resume = Resumes(
        user_id=user_id,
        file_name=file_name,
        file_url=f"{UPLOAD_DIR_REL}/{stored_name}",
        mime_type=mime_type,
        size=len(content),
        status="uploaded",
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    return ResumeVO(
        resumeId=str(resume.id),
        fileName=resume.file_name,
        mimeType=resume.mime_type,
        status=resume.status,
    )


async def list_resumes(
    db: AsyncSession, user_id: int, cursor: str | None
) -> PageResult[ResumeDTO]:
    """分页查询当前用户简历列表（游标分页，按 id 倒序）。"""
    stmt = select(Resumes).where(Resumes.user_id == user_id)
    if cursor is not None:
        try:
            cursor_id = int(cursor)
        except ValueError:
            raise BizError(ErrorCode.PARAM_ERROR, "无效的分页游标")
        stmt = stmt.where(Resumes.id < cursor_id)
    stmt = stmt.order_by(Resumes.id.desc()).limit(PAGE_SIZE + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > PAGE_SIZE
    items = rows[:PAGE_SIZE]
    next_cursor = str(items[-1].id) if has_more and items else None

    return PageResult[ResumeDTO](
        items=[_to_dto(r) for r in items],
        nextCursor=next_cursor,
        hasMore=has_more,
    )


async def get_resume(db: AsyncSession, user_id: int, resume_id: int) -> ResumeDTO:
    """查询单个简历详情。"""
    return _to_dto(await _get_owned_resume(db, user_id, resume_id))


async def delete_resume(db: AsyncSession, user_id: int, resume_id: int) -> None:
    """删除简历：删记录 + 删磁盘文件（尽力而为）。"""
    resume = await _get_owned_resume(db, user_id, resume_id)
    try:
        (_BACKEND_ROOT / resume.file_url).unlink(missing_ok=True)
    except OSError:
        pass  # 文件已不存在或不可删，不阻断删除记录
    await db.delete(resume)
    await db.commit()


async def trigger_parse(db: AsyncSession, user_id: int, resume_id: int) -> ParseJobVO:
    """触发解析（同步）：抽文本 -> LLM 结构化 -> 落库，状态 review_required / failed。"""
    resume = await _get_owned_resume(db, user_id, resume_id)
    job_id = secrets.token_urlsafe(16)
    resume.parse_job_id = job_id

    try:
        content = (_BACKEND_ROOT / resume.file_url).read_bytes()
        text = resume_parser.extract_text(resume.file_name, content)
        if not text.strip():
            resume.status = "failed"
            await db.commit()
            return ParseJobVO(jobId=job_id, status="failed")

        parsed = await resume_parser.structure_resume(text)
        resume.parsed_education = parsed["education"]
        resume.parsed_projects = parsed["projects"]
        resume.parsed_skills = parsed["skills"]
        resume.parsed_certificates = parsed["certificates"]
        resume.parsed_warnings = parsed["warnings"]
        resume.status = "review_required"
        await db.commit()
        return ParseJobVO(jobId=job_id, status="review_required")
    except BizError:
        raise
    except Exception:
        resume.status = "failed"
        await db.commit()
        return ParseJobVO(jobId=job_id, status="failed")


async def get_parse_result(
    db: AsyncSession, user_id: int, resume_id: int
) -> ParseResultVO:
    """查询简历解析结果。"""
    resume = await _get_owned_resume(db, user_id, resume_id)
    if resume.status == "uploaded":
        raise BizError(ErrorCode.PARAM_ERROR, "简历尚未解析")
    return ParseResultVO(
        status=resume.status,
        education=resume.parsed_education or [],
        projects=resume.parsed_projects or [],
        skills=resume.parsed_skills or [],
        certificates=resume.parsed_certificates or [],
        warnings=resume.parsed_warnings or [],
    )


async def patch_parsed_content(
    db: AsyncSession, user_id: int, resume_id: int, dto: ResumeContentPatchDTO
) -> None:
    """编辑解析内容：只更新传入的字段。"""
    resume = await _get_owned_resume(db, user_id, resume_id)
    if resume.status == "uploaded":
        raise BizError(ErrorCode.PARAM_ERROR, "简历尚未解析")
    if dto.education is not None:
        resume.parsed_education = dto.education
    if dto.projects is not None:
        resume.parsed_projects = dto.projects
    if dto.skills is not None:
        resume.parsed_skills = dto.skills
    if dto.certificates is not None:
        resume.parsed_certificates = dto.certificates
    await db.commit()


async def confirm_resume(db: AsyncSession, user_id: int, resume_id: int) -> None:
    """确认解析结果：review_required -> confirmed。"""
    resume = await _get_owned_resume(db, user_id, resume_id)
    if resume.status != "review_required":
        raise BizError(ErrorCode.PARAM_ERROR, "简历未处于待确认状态")
    resume.status = "confirmed"
    await db.commit()
