"""所有数据库模型。"""
import asyncio
from datetime import datetime

from sqlalchemy import DateTime, String, func, BIGINT, ForeignKey, JSON, Text, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, engine


class Users(Base):
    """用户表（登录用）。完整 11 张表按接口文档设计，随后补全。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT,primary_key=True, comment="用户id")
    account: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="登录账号")
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="用户名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    avatar_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="头像图片 URL")
    phone: Mapped[str] = mapped_column(String(11), unique=True, nullable=True, comment="手机号")
    email: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="邮箱")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="修改时间")

class RefreshTokens(Base):
    """刷新令牌表。"""
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(BIGINT,primary_key=True, comment="刷新令牌id")
    user_id: Mapped[int] = mapped_column(BIGINT,ForeignKey("users.id"),nullable=False,comment="用户id")
    token: Mapped[str] = mapped_column(String(255), nullable=False, comment="刷新令牌")
    client_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="客户端类型")
    expires_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="过期时间")
    revoked_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="登出时置信，实现logout失效")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class Profiles(Base):
    """用户画像表。"""
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(BIGINT,primary_key=True, comment="用户画像id")
    user_id: Mapped[int] = mapped_column(BIGINT,ForeignKey("users.id"),nullable=False,comment="用户id")
    type: Mapped[str] = mapped_column(String(16), nullable=False, comment="用户类型,答辩or面试")
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="显示名称")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="名称")
    school: Mapped[str] = mapped_column(String(64), nullable=False, comment="学校")
    department: Mapped[str] = mapped_column(String(64), nullable=False, comment="院系")
    major: Mapped[str] = mapped_column(String(64), nullable=False, comment="专业")
    degree: Mapped[str] = mapped_column(String(64), nullable=False, comment="学位")
    grade: Mapped[str] = mapped_column(String(64), nullable=False, comment="年级")
    enrollment_year: Mapped[int] = mapped_column(BIGINT, nullable=True, comment="入学年份")
    expected_graduation_year: Mapped[int] = mapped_column(BIGINT, nullable=True, comment="预计毕业年份")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, comment="画像明细(JSON结构)")
    completion_status: Mapped[str] = mapped_column(String(16), nullable=False, comment="完成状态")
    version: Mapped[int] = mapped_column(BIGINT, nullable=False, comment="版本号")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(),comment="修改时间")






class DefenseMaterials(Base):
    """答辩材料表。"""
    __tablename__ = "defense_materials"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="材料id")
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.id"), nullable=False, comment="用户id")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="文件名")
    file_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="文件存储路径")
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="文件类型")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="材料状态")
    parse_job_id: Mapped[str] = mapped_column(String(64), nullable=True, comment="解析任务id")
    parsed_topic: Mapped[str] = mapped_column(String(512), nullable=True, comment="解析主题")
    parsed_outline: Mapped[list] = mapped_column(JSON, nullable=True, comment="解析大纲")
    parsed_key_points: Mapped[list] = mapped_column(JSON, nullable=True, comment="解析关键点")
    parsed_methods: Mapped[list] = mapped_column(JSON, nullable=True, comment="解析方法")
    parsed_results: Mapped[list] = mapped_column(JSON, nullable=True, comment="解析结果")
    parsed_possible_questions: Mapped[list] = mapped_column(JSON, nullable=True, comment="可能被问到的问题")
    parsed_warnings: Mapped[list] = mapped_column(JSON, nullable=True, comment="解析警示")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="修改时间")

class Sessions(Base):
    """会话表。"""
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="会话id")
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.id"), nullable=False, comment="用户id")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, comment="模式(答辩)")
    scene: Mapped[str] = mapped_column(String(16), nullable=False, comment="场景")
    scene_config: Mapped[dict] = mapped_column(JSON, nullable=True, comment="场景配置")
    profile_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("profiles.id"), nullable=False, comment="画像id")
    profile_snapshot: Mapped[dict] = mapped_column(JSON, nullable=True, comment="画像快照")
    profile_snapshot_version: Mapped[int] = mapped_column(BIGINT, nullable=True, comment="画像快照版本")
    modality: Mapped[str] = mapped_column(String(16), nullable=False, comment="交互形态")
    title: Mapped[str] = mapped_column(String(128), nullable=True, comment="会话标题")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="会话状态")
    stage: Mapped[str] = mapped_column(String(32), nullable=True, comment="当前阶段")
    client_session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="客户端会话id,幂等")
    first_prompt: Mapped[str] = mapped_column(Text, nullable=True, comment="开场白")
    overall_score: Mapped[int] = mapped_column(BIGINT, nullable=True, comment="综合得分")
    report_status: Mapped[str] = mapped_column(String(16), nullable=True, comment="报告状态")
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="开始时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="结束时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="修改时间")

class SessionMaterials(Base):
    """会话-材料关联表。"""
    __tablename__ = "session_materials"
    __table_args__ = (UniqueConstraint("session_id", "material_id", name="uq_session_material"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="关联id")
    session_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("sessions.id"), nullable=False, comment="会话id")
    material_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("defense_materials.id"), nullable=False, comment="材料id")

class Messages(Base):
    """消息表。"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="消息id")
    session_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("sessions.id"), nullable=False, comment="会话id")
    seq: Mapped[int] = mapped_column(BIGINT, nullable=False, comment="会话内消息序号")
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="角色")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="消息类型")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    input_mode: Mapped[str] = mapped_column(String(16), nullable=False, comment="输入形态")
    audio_id: Mapped[str] = mapped_column(String(64), nullable=True, comment="音频id")
    asr_confidence: Mapped[float] = mapped_column(Float, nullable=True, comment="语音识别置信度")
    stage: Mapped[str] = mapped_column(String(32), nullable=True, comment="所处阶段")
    client_message_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="客户端消息id,幂等")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class Responses(Base):
    """AI响应表。"""
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="响应id")
    session_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("sessions.id"), nullable=False, comment="会话id")
    user_message_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("messages.id"), nullable=False, comment="触发的用户消息id")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="响应状态")
    completed_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="完成时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class ResponseEvents(Base):
    """SSE流式事件表。"""
    __tablename__ = "response_events"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="事件id")
    response_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("responses.id"), nullable=False, comment="响应id")
    type: Mapped[str] = mapped_column(String(32), nullable=False, comment="事件类型")
    data: Mapped[dict] = mapped_column(JSON, nullable=True, comment="事件负载")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class Reports(Base):
    """评分报告表。"""
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="报告id")
    session_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("sessions.id"), unique=True, nullable=False, comment="会话id")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="报告状态")
    overall_score: Mapped[int] = mapped_column(BIGINT, nullable=True, comment="综合得分")
    dimensions: Mapped[list] = mapped_column(JSON, nullable=True, comment="维度评分数组")
    summary: Mapped[str] = mapped_column(Text, nullable=True, comment="总结")
    action_items: Mapped[list] = mapped_column(JSON, nullable=True, comment="行动项")
    weak_point_tags: Mapped[list] = mapped_column(JSON, nullable=True, comment="弱项标签")
    generated_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="生成时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class WeakPoints(Base):
    """弱项标记表。"""
    __tablename__ = "weak_points"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="弱项id")
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.id"), nullable=False, comment="用户id")
    session_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("sessions.id"), nullable=True, comment="来源会话id")
    dimension_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="维度key")
    message_ids: Mapped[list] = mapped_column(JSON, nullable=True, comment="支撑消息id数组")
    note: Mapped[str] = mapped_column(String(512), nullable=True, comment="备注")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class MemorySettings(Base):
    """长期记忆设置表。"""
    __tablename__ = "memory_settings"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="设置id")
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.id"), unique=True, nullable=False, comment="用户id")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否开启")
    retention_policy: Mapped[str] = mapped_column(String(32), nullable=True, comment="保留策略")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="修改时间")

class Memories(Base):
    """长期记忆摘要表。"""
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="记忆id")
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.id"), nullable=False, comment="用户id")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆摘要")
    source_session_id: Mapped[str] = mapped_column(String(64), nullable=True, comment="来源会话id")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

class Audios(Base):
    """音频表(语音阶段使用)。"""
    __tablename__ = "audios"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, comment="音频id")
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.id"), nullable=False, comment="用户id")
    audio_url: Mapped[str] = mapped_column(String(512), nullable=True, comment="音频地址")
    text: Mapped[str] = mapped_column(Text, nullable=True, comment="ASR结果或TTS原文")
    confidence: Mapped[float] = mapped_column(Float, nullable=True, comment="置信度")
    duration_ms: Mapped[int] = mapped_column(BIGINT, nullable=True, comment="时长(毫秒)")
    expires_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="过期时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")


#-------------------------------------------------------------------------------------------
async def create_tables():
    """建表：只创建缺失的表，不修改已有表结构（改结构要用 Alembic）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(create_tables())
    print("建表完成")
