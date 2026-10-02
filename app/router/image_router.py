"""
app/router/image_router.py
===========================
图像生成路由接口
"""

from fastapi import APIRouter, HTTPException

from app.configs.logging_config import get_logger
from app.model.image_schema import ImageRequest, ImageResponse
from app.service.pipeline_manager import getPipelineManager

router = APIRouter()
logger = get_logger(__name__)

@router.post("/generate", response_model=ImageResponse)
@router.post("/generate-from-text", response_model=ImageResponse)
def generate_image(request: ImageRequest,project_id:str="",index:int=-1):
    """
    输入提示词，生成图像。
    """
    try:
        manager=getPipelineManager()
        if project_id=="":
            pid=manager.create_project("test","image")
        else:
            pid=project_id
        if index == -1: #是生成过程
            manager.update_config(project_id=pid,config=request)
        logger.debug(f"图像生成请求: index={index}, project_id={pid}")
        image_result = manager.gen_image(
            pid,
            text=request.prompt,
            model_name=request.image_model_name,
            api_key=request.image_api_key,
            n=request.n or 1,
            size=request.size or "",
            language=request.language or "",
            index=index,
        )
        if not image_result["success"]:
            manager.save_project(pid)
        logger.info(f"图像生成完成: success={image_result['success']}, 路径: {image_result['image_paths']}")
        response = ImageResponse(
            success=image_result["success"],
            error=image_result.get("error"),
            image_paths=image_result["image_paths"],
            project=manager.get_project_snapshot(pid) if index >= 0 and image_result["success"] else None,
        )
        return response

    except Exception as e:
        logger.exception("图像生成失败: project_id=%s index=%s", project_id, index)
        raise HTTPException(status_code=500, detail=str(e))
