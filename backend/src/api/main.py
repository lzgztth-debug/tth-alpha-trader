"""FastAPI 主应用模块

创建 FastAPI 应用实例，配置中间件、路由、异常处理器和生命周期事件。
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from src.api.routes import (
    account_router,
    ai_router,
    config_router,
    logs_router,
    strategy_router,
    trading_router,
)
from src.api.auth import router as auth_router
from src.adapters.ai_models import ADAPTER_MAP
from src.adapters.ai_models.base import ModelConfig, ModelProvider
from src.database.connection import close_db, init_db
from src.utils.config import get_settings


# ---------------------------------------------------------------------------
# 生命周期管理
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理: 启动时初始化数据库，关闭时释放资源。"""
    # ---- 启动 ----
    logger.info("AI Trading Platform API 正在启动...")

    settings = get_settings()

    # 初始化数据库
    try:
        await init_db(settings.database.url)
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

    # 自动注册 AI 模型适配器
    try:
        from src.core.agent_engine import AIAgentEngine

        app.state.agent_engine = AIAgentEngine()

        # 加载 Prompt 模板
        app.state.agent_engine.prompt_manager.load_all_from_directory()

        # 遍历 ADAPTER_MAP，为已配置 API Key 的提供商注册模型
        ai_settings = settings.ai
        provider_settings_map = {
            "openai": ai_settings.openai,
            "claude": ai_settings.anthropic,
            "deepseek": None,
            "seed": ai_settings.seed,
            "minimax": ai_settings.minimax,
            "qwen": ai_settings.dashscope,
            "siliconflow": ai_settings.siliconflow,
            "zhipu": ai_settings.zhipu,
            "qianfan": ai_settings.qianfan,
            "moonshot": ai_settings.moonshot,
            "ollama": None,
        }

        for provider_name, adapter_cls in ADAPTER_MAP.items():
            provider_settings = provider_settings_map.get(provider_name)
            if provider_settings is None:
                continue

            api_key = getattr(provider_settings, "api_key", None)
            if not api_key:
                continue

            model_name = getattr(provider_settings, "model", "")
            base_url = getattr(provider_settings, "base_url", None)
            temperature = getattr(provider_settings, "temperature", 0.7)
            max_tokens = getattr(provider_settings, "max_tokens", 4096)
            timeout = getattr(provider_settings, "timeout", 60)

            try:
                model_config = ModelConfig(
                    provider=ModelProvider(provider_name),
                    model_name=model_name,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                adapter = adapter_cls(model_config)
                app.state.agent_engine.register_model(provider_name, adapter)
                logger.info(f"AI 模型已注册: {provider_name} ({model_name})")
            except Exception as e:
                logger.warning(f"注册 AI 模型失败: {provider_name}, 错误: {e}")

        registered = app.state.agent_engine.list_models()
        logger.info(f"AI 模型注册完成, 已注册: {[m['name'] for m in registered]}")

    except Exception as e:
        logger.warning(f"AI 模型自动注册失败: {e}")
        app.state.agent_engine = None

    logger.info(
        f"API 服务已启动: http://{settings.api.host}:{settings.api.port}"
    )

    yield

    # ---- 关闭 ----
    logger.info("AI Trading Platform API 正在关闭...")
    await close_db()
    logger.info("数据库连接已关闭")
    logger.info("API 服务已停止")


# ---------------------------------------------------------------------------
# 创建 FastAPI 应用
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    settings = get_settings()

    app = FastAPI(
        title="AI Trading Platform API",
        description="""
## AI 自动化交易平台 API

提供交易、策略、日志和账户管理的完整 RESTful API。

### 功能模块

- **交易模块**: 下单、撤单、查询订单和持仓
- **策略模块**: Prompt模板管理、策略配置、启停控制
- **日志模块**: 决策日志、交易日志查询与导出
- **账户模块**: 账户管理、模拟账户创建、交易模式切换
        """,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={
            "name": "AI Trading Platform",
            "version": settings.app_version,
        },
        license_info={
            "name": "MIT",
        },
    )

    # ------------------------------------------------------------------
    # CORS 中间件
    # ------------------------------------------------------------------
    if settings.debug:
        # 调试模式: 允许所有来源，方便本地开发
        cors_origins = ["*"]
    else:
        # 生产模式: 仅允许前端域名
        cors_origins = ["http://localhost:3000"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # 注册路由
    # ------------------------------------------------------------------
    app.include_router(auth_router)
    app.include_router(trading_router)
    app.include_router(strategy_router)
    app.include_router(logs_router)
    app.include_router(account_router)
    app.include_router(ai_router)
    app.include_router(config_router)

    # ------------------------------------------------------------------
    # 异常处理器
    # ------------------------------------------------------------------
    _register_exception_handlers(app)

    # ------------------------------------------------------------------
    # 健康检查端点
    # ------------------------------------------------------------------
    @app.get("/health", tags=["系统"], summary="健康检查")
    async def health_check() -> dict:
        """健康检查端点，用于监控服务状态。"""
        return {
            "status": "healthy",
            "app_name": settings.app_name,
            "version": settings.app_version,
        }

    @app.get("/", tags=["系统"], summary="API根路径")
    async def root() -> dict:
        """API根路径，返回基本信息。"""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "redoc": "/redoc",
        }

    return app


# ---------------------------------------------------------------------------
# 异常处理器注册
# ---------------------------------------------------------------------------

def _register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """处理请求参数验证错误。"""
        errors = exc.errors()
        logger.warning(f"请求参数验证失败: {request.url} - {errors}")

        # 格式化错误信息
        formatted_errors = []
        for error in errors:
            formatted_errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "请求参数验证失败",
                "detail": formatted_errors,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """处理HTTP异常。"""
        logger.warning(
            f"HTTP异常: {request.url} - "
            f"status={exc.status_code}, detail={exc.detail}"
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.detail,
                "status_code": exc.status_code,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """处理未捕获的异常。"""
        logger.error(
            f"未处理异常: {request.url} - {type(exc).__name__}: {exc}",
            exc_info=True,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "服务器内部错误",
                "detail": str(exc) if get_settings().debug else "请稍后重试",
            },
        )


# ---------------------------------------------------------------------------
# 应用实例 (模块级别)
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.debug,
        workers=settings.api.workers,
    )
