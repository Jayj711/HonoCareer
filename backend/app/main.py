"""FastAPI 启动入口，注册所有接口。"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse

from app.api import (
    auth,
    defense_materials,
    memories,
    messages,
    profiles,
    reports,
    resumes,
    sessions,
    speech,
    users,
    weak_points,
)
from app.config import setup_logging
from app.core.error import BizError, ErrorCode
from app.schemas.common import Result

setup_logging()

# Swagger UI / ReDoc 的资源默认从 cdn.jsdelivr.net 加载，国内被墙打不开。
# FastAPI 0.99+ 的构造器已不支持改 CDN 地址，这里关掉默认 docs，
# 改用 get_swagger_ui_html / get_redoc_html 手动挂载，并换成 jsdelivr 的 fastly 镜像。
app = FastAPI(
    title="HonoCareer 后端",
    version="0.1.0",
    docs_url=None,   # 关闭默认 /docs（其 CDN 被墙）
    redoc_url=None,  # 关闭默认 /redoc
)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """自定义 Swagger UI，资源走国内可达的 fastly 镜像。"""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="HonoCareer 后端 - API 文档",
        swagger_js_url="https://fastly.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://fastly.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    """自定义 ReDoc，资源走 fastly 镜像，并关闭被墙的 Google Fonts。"""
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="HonoCareer 后端 - API 文档",
        redoc_js_url="https://fastly.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js",
        with_google_fonts=False,
    )


# 全局业务异常处理器：把 service 层抛出的 BizError 统一转成
# {code, message, data, requestId} 结构，HTTP 状态码固定 200（错误用 body 里的 code 区分）
@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    return JSONResponse(
        status_code=200,
        content=Result.fail(exc.code, exc.message).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """参数校验失败（FastAPI 默认 422）统一转成 code=40001 的 Result 结构。"""
    # 取第一条错误的字段路径（如 body.password / query.type）拼进 message，方便定位
    errors = exc.errors()
    loc = ".".join(str(x) for x in errors[0].get("loc", [])) if errors else ""
    message = f"参数错误: {loc}" if loc else "参数错误"
    return JSONResponse(
        status_code=200,
        content=Result.fail(ErrorCode.PARAM_ERROR, message).model_dump(),
    )


# 挂载鉴权与用户路由
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(profiles.router)
app.include_router(resumes.router)
app.include_router(defense_materials.router)
app.include_router(sessions.router)
app.include_router(messages.router)
app.include_router(reports.router)
app.include_router(weak_points.router)
app.include_router(memories.router)
app.include_router(speech.router)


@app.get("/health")
async def health():
    """健康检查：验证服务能起、统一响应结构正常。"""
    return Result.success(data={"status": "ok", "message": "Hello World"})
