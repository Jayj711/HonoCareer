"""答辩材料服务：上传、解析、编辑、确认、删除。"""
import secrets
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error import BizError, ErrorCode
from app.db.models import DefenseMaterials, SessionMaterials
from app.parsers import defense_material as material_parser
from app.schemas.common import PageResult
from app.schemas.defense_material import (
    DefenseMaterialContentPatchDTO,
    DefenseMaterialDTO,
    DefenseMaterialVO,
    ParseJobVO,
    ParseResultVO,
)

PAGE_SIZE = 20
MAX_FILE_SIZE = 10 * 1024 * 1024  # 单个材料最大 10MB

# 上传根目录：backend/uploads/defense_materials（相对 backend 根，避免受启动时 CWD 影响）
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = _BACKEND_ROOT / "uploads" / "defense_materials"
UPLOAD_DIR_REL = "uploads/defense_materials"


def _to_dto(m: DefenseMaterials) -> DefenseMaterialDTO:
    """把 ORM 模型转成返回给前端的材料 DTO。"""
    return DefenseMaterialDTO(
        materialId=str(m.id),
        fileName=m.file_name,
        mimeType=m.mime_type,
        size=m.size,
        status=m.status,
        createdAt=m.create_time,
    )


async def _get_owned_material(
    db: AsyncSession, user_id: int, material_id: int
) -> DefenseMaterials:
    """按 id 查材料，且必须是当前用户自己的；查不到统一抛「材料不存在」。"""
    result = await db.execute(
        select(DefenseMaterials).where(
            DefenseMaterials.id == material_id, DefenseMaterials.user_id == user_id
        )
    )
    material = result.scalar_one_or_none()
    if material is None:
        raise BizError(ErrorCode.NOT_FOUND, "材料不存在")
    return material


async def upload_material(
    db: AsyncSession, user_id: int, file_name: str, mime_type: str, content: bytes
) -> DefenseMaterialVO:
    """上传材料：校验类型与大小，落盘并建记录（初始状态 uploaded）。"""
    if not file_name.strip():
        raise BizError(ErrorCode.PARAM_ERROR, "文件名不能为空")

    ext = material_parser.ALLOWED_MIME_TYPES.get(mime_type)
    if ext is None:
        raise BizError(ErrorCode.PARAM_ERROR, "仅支持 PDF / Word / PPT 材料")

    if len(content) > MAX_FILE_SIZE:
        raise BizError(ErrorCode.PARAM_ERROR, "材料文件过大，最大 10MB")

    # 落盘：用随机文件名避免路径冲突 / 覆盖
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(content)

    material = DefenseMaterials(
        user_id=user_id,
        file_name=file_name,
        file_url=f"{UPLOAD_DIR_REL}/{stored_name}",
        mime_type=mime_type,
        size=len(content),
        status="uploaded",
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    return DefenseMaterialVO(
        materialId=str(material.id),
        fileName=material.file_name,
        mimeType=material.mime_type,
        status=material.status,
    )


async def list_materials(
    db: AsyncSession, user_id: int, cursor: str | None
) -> PageResult[DefenseMaterialDTO]:
    """分页查询当前用户材料列表（游标分页，按 id 倒序）。"""
    stmt = select(DefenseMaterials).where(DefenseMaterials.user_id == user_id)
    if cursor is not None:
        try:
            cursor_id = int(cursor)
        except ValueError:
            raise BizError(ErrorCode.PARAM_ERROR, "无效的分页游标")
        stmt = stmt.where(DefenseMaterials.id < cursor_id)
    stmt = stmt.order_by(DefenseMaterials.id.desc()).limit(PAGE_SIZE + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > PAGE_SIZE
    items = rows[:PAGE_SIZE]
    next_cursor = str(items[-1].id) if has_more and items else None

    return PageResult[DefenseMaterialDTO](
        items=[_to_dto(m) for m in items],
        nextCursor=next_cursor,
        hasMore=has_more,
    )


async def get_material(
    db: AsyncSession, user_id: int, material_id: int
) -> DefenseMaterialDTO:
    """查询单个材料详情。"""
    return _to_dto(await _get_owned_material(db, user_id, material_id))


async def delete_material(db: AsyncSession, user_id: int, material_id: int) -> None:
    """删除材料：删记录 + 删磁盘文件（尽力而为）。"""
    material = await _get_owned_material(db, user_id, material_id)
    try:
        (_BACKEND_ROOT / material.file_url).unlink(missing_ok=True)
    except OSError:
        pass  # 文件已不存在或不可删，不阻断删除记录
    # 先清掉会话-材料关联，避免外键约束阻断删除
    await db.execute(
        delete(SessionMaterials).where(SessionMaterials.material_id == material_id)
    )
    await db.delete(material)
    await db.commit()


async def trigger_parse(db: AsyncSession, user_id: int, material_id: int) -> ParseJobVO:
    """触发解析（同步）：抽文本 -> LLM 结构化 -> 落库，状态 review_required / failed。"""
    material = await _get_owned_material(db, user_id, material_id)
    job_id = secrets.token_urlsafe(16)
    material.parse_job_id = job_id

    try:
        content = (_BACKEND_ROOT / material.file_url).read_bytes()
        text = material_parser.extract_text(material.file_name, content)
        if not text.strip():
            material.status = "failed"
            await db.commit()
            return ParseJobVO(jobId=job_id, status="failed")

        parsed = await material_parser.structure_defense_material(text)
        material.parsed_topic = parsed["topic"]
        material.parsed_outline = parsed["outline"]
        material.parsed_key_points = parsed["key_points"]
        material.parsed_methods = parsed["methods"]
        material.parsed_results = parsed["results"]
        material.parsed_possible_questions = parsed["possible_questions"]
        material.parsed_warnings = parsed["warnings"]
        material.status = "review_required"
        await db.commit()
        return ParseJobVO(jobId=job_id, status="review_required")
    except BizError:
        raise
    except Exception:
        material.status = "failed"
        await db.commit()
        return ParseJobVO(jobId=job_id, status="failed")


async def get_parse_result(
    db: AsyncSession, user_id: int, material_id: int
) -> ParseResultVO:
    """查询材料解析结果。"""
    material = await _get_owned_material(db, user_id, material_id)
    if material.status == "uploaded":
        raise BizError(ErrorCode.PARAM_ERROR, "材料尚未解析")
    return ParseResultVO(
        status=material.status,
        topic=material.parsed_topic or "",
        outline=material.parsed_outline or [],
        keyPoints=material.parsed_key_points or [],
        methods=material.parsed_methods or [],
        results=material.parsed_results or [],
        possibleQuestions=material.parsed_possible_questions or [],
        warnings=material.parsed_warnings or [],
    )


async def patch_parsed_content(
    db: AsyncSession, user_id: int, material_id: int, dto: DefenseMaterialContentPatchDTO
) -> None:
    """编辑解析内容：只更新传入的字段。"""
    material = await _get_owned_material(db, user_id, material_id)
    if material.status == "uploaded":
        raise BizError(ErrorCode.PARAM_ERROR, "材料尚未解析")
    if dto.topic is not None:
        material.parsed_topic = dto.topic
    if dto.outline is not None:
        material.parsed_outline = dto.outline
    if dto.keyPoints is not None:
        material.parsed_key_points = dto.keyPoints
    if dto.methods is not None:
        material.parsed_methods = dto.methods
    if dto.results is not None:
        material.parsed_results = dto.results
    if dto.possibleQuestions is not None:
        material.parsed_possible_questions = dto.possibleQuestions
    await db.commit()


async def confirm_material(db: AsyncSession, user_id: int, material_id: int) -> None:
    """确认解析结果：review_required -> confirmed。"""
    material = await _get_owned_material(db, user_id, material_id)
    if material.status != "review_required":
        raise BizError(ErrorCode.PARAM_ERROR, "材料未处于待确认状态")
    material.status = "confirmed"
    await db.commit()
