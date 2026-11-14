"""评分报告接口：查询会话评分报告。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user_id
from app.db.session import get_db
from app.schemas.common import Result
from app.services import report as report_service

router = APIRouter(prefix="/api/v1/sessions", tags=["reports"])


@router.get("/{session_id}/report")
async def get_report(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询会话评分报告。"""
    vo = await report_service.get_report(db, user_id, session_id)
    return Result.success(data=vo)
