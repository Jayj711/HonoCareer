"""异步会话管理。"""
from app.db import AsyncSessionFactory


async def get_db():
    """FastAPI 依赖：每个请求一个异步 Session，用完自动关闭。"""
    async with AsyncSessionFactory() as db:
        yield db
