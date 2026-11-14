"""评分报告服务：finish 后异步生成评分卡（后台任务）+ 查询报告。"""
import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import _load_context
from app.agent.tools.scorecard import generate_scorecard
from app.core.error import BizError, ErrorCode
from app.db import AsyncSessionFactory
from app.db.models import Messages, Reports, Sessions
from app.schemas.report import ReportDimensionVO, ReportVO
from app.schemas.session import ReportStatus, SessionStatus
from app.services.memory import sync_memories_from_session

# 后台报告生成任务引用，防止被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def schedule_report(session_id: int, report_id: int) -> None:
    """触发后台报告生成任务，持有引用避免被 GC。"""
    task = asyncio.create_task(run_report(session_id, report_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _to_vo(report: Reports, session: Sessions) -> ReportVO:
    dimensions = []
    for d in report.dimensions or []:
        if not isinstance(d, dict):
            continue
        dimensions.append(
            ReportDimensionVO(
                key=str(d.get("key", "")),
                label=str(d.get("label", "")),
                score=int(d.get("score") or 0),
                evidence=[str(x) for x in d.get("evidence") or []],
                strengths=[str(x) for x in d.get("strengths") or []],
                issues=[str(x) for x in d.get("issues") or []],
                suggestions=[str(x) for x in d.get("suggestions") or []],
            )
        )
    return ReportVO(
        reportId=str(report.id),
        sessionId=str(report.session_id),
        mode=session.mode,
        status=ReportStatus(report.status),
        overallScore=report.overall_score,
        dimensions=dimensions,
        summary=report.summary,
        actionItems=report.action_items or [],
        weakPointTags=report.weak_point_tags or [],
        generatedAt=report.generated_time,
    )


async def _load_transcript(db: AsyncSession, session_id: int) -> list[dict]:
    """加载会话全部消息转录（带消息 id，供评分卡 evidence 引用）。"""
    rows = list(
        (
            await db.execute(
                select(Messages)
                .where(Messages.session_id == session_id)
                .order_by(Messages.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {"id": str(m.id), "role": m.role, "content": m.content, "stage": m.stage}
        for m in rows
    ]


async def run_report(session_id: int, report_id: int) -> None:
    """后台任务：生成评分卡并落库。独立 session，异常写 failed，不上抛。"""
    try:
        async with AsyncSessionFactory() as db:
            session = (
                await db.execute(select(Sessions).where(Sessions.id == session_id))
            ).scalar_one_or_none()
            report = (
                await db.execute(select(Reports).where(Reports.id == report_id))
            ).scalar_one_or_none()
            if session is None or report is None:
                return

            resume_text, material_text = await _load_context(db, session)
            transcript = await _load_transcript(db, session_id)
            result = await generate_scorecard(
                mode=session.mode,
                scene=session.scene,
                profile_snapshot=session.profile_snapshot,
                resume_text=resume_text,
                material_text=material_text,
                transcript=transcript,
            )

            report.overall_score = result["overall_score"]
            report.dimensions = result["dimensions"]
            report.summary = result["summary"]
            report.action_items = result["action_items"]
            report.weak_point_tags = result["weak_point_tags"]
            report.status = ReportStatus.ready.value
            report.generated_time = datetime.now()

            session.overall_score = result["overall_score"]
            session.report_status = ReportStatus.ready.value
            session.status = SessionStatus.completed.value
            await sync_memories_from_session(db, session, transcript)
            await db.commit()
    except Exception:  # noqa: BLE001 —— 后台任务必须兜底，不能让异常静默
        try:
            async with AsyncSessionFactory() as db:
                report = (
                    await db.execute(select(Reports).where(Reports.id == report_id))
                ).scalar_one_or_none()
                if report is not None:
                    report.status = ReportStatus.failed.value
                session = (
                    await db.execute(select(Sessions).where(Sessions.id == session_id))
                ).scalar_one_or_none()
                if session is not None:
                    session.report_status = ReportStatus.failed.value
                    session.status = SessionStatus.completed.value
                await db.commit()
        except Exception:  # noqa: BLE001 —— 兜底自身也不该再抛
            pass


async def get_report(db: AsyncSession, user_id: int, session_id: int) -> ReportVO:
    """查询会话评分报告。归属校验 + 无报告 40401。"""
    session = (
        await db.execute(
            select(Sessions).where(Sessions.id == session_id, Sessions.user_id == user_id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise BizError(ErrorCode.NOT_FOUND, "会话不存在")
    report = (
        await db.execute(select(Reports).where(Reports.session_id == session_id))
    ).scalar_one_or_none()
    if report is None:
        raise BizError(ErrorCode.NOT_FOUND, "报告不存在")
    return _to_vo(report, session)
