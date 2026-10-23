"""FastAPI 启动入口，注册所有接口。"""
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import Orchestrator
from app.config import settings, setup_logging
from app.llm.deepseek import DeepSeekClient
from app.schemas.chat import ChatRequest
from app.schemas.common import Result

setup_logging()

app = FastAPI(title="HonoCareer 后端", version="0.1.0")

@app.get("/health")
async def health():
    return Result.success(data={"status": "ok", "message": "Hello World"})


