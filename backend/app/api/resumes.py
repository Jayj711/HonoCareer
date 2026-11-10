"""简历接口：上传、列表、详情、删除、解析、编辑、确认。"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.resume import ResumeContentPatchDTO
from app.services import resume as resume_service

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])


@router.post("")
async def upload_resume(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """上传简历（multipart 文件）。"""
    content = await file.read()
    vo = await resume_service.upload_resume(
        db, user_id, file.filename or "", file.content_type or "", content
    )
    return Result.success(data=vo)


@router.get("")
async def list_resumes(
    cursor: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """分页查询当前用户简历列表。"""
    page = await resume_service.list_resumes(db, user_id, cursor)
    return Result.success(data=page)


@router.get("/{resume_id}")
async def get_resume(
    resume_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询单个简历详情。"""
    vo = await resume_service.get_resume(db, user_id, resume_id)
    return Result.success(data=vo)


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除简历。"""
    await resume_service.delete_resume(db, user_id, resume_id)
    return Result.success()


@router.post("/{resume_id}/parse")
async def trigger_parse(
    resume_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """触发简历解析（同步）。"""
    vo = await resume_service.trigger_parse(db, user_id, resume_id)
    return Result.success(data=vo)


@router.get("/{resume_id}/parse")
async def get_parse_result(
    resume_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询简历解析结果。"""
    vo = await resume_service.get_parse_result(db, user_id, resume_id)
    return Result.success(data=vo)


@router.patch("/{resume_id}/parsed-content")
async def patch_parsed_content(
    resume_id: int,
    dto: ResumeContentPatchDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """编辑简历解析内容。"""
    await resume_service.patch_parsed_content(db, user_id, resume_id, dto)
    return Result.success()


@router.post("/{resume_id}/confirm")
async def confirm_resume(
    resume_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """确认简历解析结果。"""
    await resume_service.confirm_resume(db, user_id, resume_id)
    return Result.success()
