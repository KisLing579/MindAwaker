"""
app/router/text_router.py
=========================
路由模块：文案生成
- 接收主题、模型名称、API key 等输入
- 同步返回生成的文案
"""

from fastapi import APIRouter, HTTPException

from app.configs.logging_config import get_logger
from app.model.text_schema import TextRequest, TextResponse
from app.service.pipeline_manager import getPipelineManager

router = APIRouter()
logger = get_logger(__name__)


@router.post("/generate", response_model=TextResponse)
def generate_text(request: TextRequest):
    """同步生成文本内容。"""
    logger.info(f"生成文本请求: with_media_prompts={request.with_media_prompts}, media_prompt_style={request.media_prompt_style}")
    try:
        manager = getPipelineManager()
        project_id = manager.create_project("text_test", "text")
        manager.update_config(project_id=project_id, config=request.model_dump())
        text_result = manager.gen_texts(
            project_id,
            with_media_prompts=request.with_media_prompts,
            media_prompt_style=request.media_prompt_style or "image_default",
            language=request.language or "",
        )
        if not text_result["success"]:
            manager.save_project(project_id)
        return TextResponse(
            theme=request.theme,
            model_name=request.text_model_name,
            content=text_result["content"],
            success=text_result["success"],
            error=text_result.get("error"),
            prompts=text_result["prompts"],
        )
    except Exception as e:
        logger.error(f"文本生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress")
def get_progress(project_id: str):
    raise HTTPException(status_code=410, detail="文本进度接口已下线，请直接调用 /text/generate")
