"""
app/main.py
=============
项目启动入口：
- 创建 FastAPI 实例
- 挂载各路由模块（text / image / audio / video）
- 配置跨域访问（CORS）
- 配置日志系统和全局异常处理
- 提供健康检查接口
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入日志配置
from app.configs.logging_config import setup_logging, get_logger
from app.configs.exceptions import setup_exception_handlers

# 导入路由
from app.router.text_router import router as text_router
from app.router.image_router import router as image_router
from app.router.audio_router import router as audio_router
from app.router.video_router import router as video_router
from app.router.projects_router import router as project_router
from app.router.settings_router import router as setting_router
from app.router.story_router import router as story_router

# 设置日志
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 Mindawaker 服务启动中...")
    logger.info(f"版本: {app.version}")
    logger.info(f"文档地址: http://127.0.0.1:8000/docs")
    from app.service.task_manager import get_task_manager
    get_task_manager().recover_interrupted_tasks()
    yield
    logger.info("👋 Mindawaker 服务关闭")


# 创建 FastAPI 实例
app = FastAPI(
    title="Mindawaker",
    description="AI 视频生成系统 - 支持文本、图像、音频、视频合成",
    version="0.2.0",
    lifespan=lifespan,
)

# 配置全局异常处理
setup_exception_handlers(app)


# -------------------------------
# 🌐 CORS 跨域配置
# -------------------------------
def get_cors_origins():
    """从环境变量读取允许的域名"""
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# -------------------------------
# 📦 注册路由
# -------------------------------
app.include_router(text_router, prefix="/text", tags=["文本生成"])
app.include_router(image_router, prefix="/image", tags=["图像生成"])
app.include_router(audio_router, prefix="/audio", tags=["音频生成"])
app.include_router(video_router, prefix="/video", tags=["视频合成"])
app.include_router(project_router, prefix="/project", tags=["项目管理"])
app.include_router(setting_router, prefix="/setting", tags=["系统设置"])
app.include_router(story_router, prefix="/story", tags=["故事审阅"])
app.mount("/files", StaticFiles(directory="app/assets"), name="files")


# -------------------------------
# 🧠 健康检查 & 欢迎页
# -------------------------------
@app.get("/")
async def root():
    return {
        "message": "🚀 Mindawaker 后端服务运行中",
        "version": "0.2.0",
        "routes": {
            "text": "/text",
            "image": "/image",
            "audio": "/audio",
            "video": "/video",
            "project": "/project",
            "settings": "/setting",
            "docs": "/docs",
        },
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "service": "mindawaker",
        "version": "0.2.0"
    }


# -------------------------------
# 🧩 主入口（仅开发调试时）
# -------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
