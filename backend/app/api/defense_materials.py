"""答辩材料接口：上传、列表、详情、删除、解析、编辑、确认。"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.schemas.defense_material import DefenseMaterialContentPatchDTO
from app.services import defense_material as material_service

router = APIRouter(prefix="/api/v1/defense-materials", tags=["defense-materials"])


@router.post("")
async def upload_material(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """上传答辩材料（multipart 文件）。"""
    content = await file.read()
    vo = await material_service.upload_material(
        db, user_id, file.filename or "", file.content_type or "", content
    )
    return Result.success(data=vo)


@router.get("")
async def list_materials(
    cursor: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """分页查询当前用户材料列表。"""
    page = await material_service.list_materials(db, user_id, cursor)
    return Result.success(data=page)


@router.get("/{material_id}")
async def get_material(
    material_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询单个材料详情。"""
    vo = await material_service.get_material(db, user_id, material_id)
    return Result.success(data=vo)


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除材料。"""
    await material_service.delete_material(db, user_id, material_id)
    return Result.success()


@router.post("/{material_id}/parse")
async def trigger_parse(
    material_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """触发材料解析（同步）。"""
    vo = await material_service.trigger_parse(db, user_id, material_id)
    return Result.success(data=vo)


@router.get("/{material_id}/parse")
async def get_parse_result(
    material_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询材料解析结果。"""
    vo = await material_service.get_parse_result(db, user_id, material_id)
    return Result.success(data=vo)


@router.patch("/{material_id}/parsed-content")
async def patch_parsed_content(
    material_id: int,
    dto: DefenseMaterialContentPatchDTO,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """编辑材料解析内容。"""
    await material_service.patch_parsed_content(db, user_id, material_id, dto)
    return Result.success()


@router.post("/{material_id}/confirm")
async def confirm_material(
    material_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """确认材料解析结果。"""
    await material_service.confirm_material(db, user_id, material_id)
    return Result.success()
