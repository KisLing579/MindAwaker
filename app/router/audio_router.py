"""
app/router/audio_router.py
===========================
音频生成路由
- 接收文本与声音参数
- 调用 audio_service 生成音频文件
- 返回路径与时长（duration）
"""

"""
app/router/audio_router.py
===========================
音频生成路由
- 接收文本与声音参数
- 调用 audio_service 生成音频文件
- 返回路径与时长（duration）
"""

from fastapi import APIRouter, HTTPException

from app.configs.logging_config import get_logger
from app.model.audio_schema import AudioRequest, AudioResponse
from app.service.pipeline_manager import getPipelineManager

router = APIRouter()
logger = get_logger(__name__)

@router.post("/generate", response_model=AudioResponse)
def generate_audio(request: AudioRequest,project_id:str="",index:int=-1):
    """
    输入文本，生成语音文件并返回时长。
    """
    try:
        logger.debug(f"音频生成请求: index={index}, project_id={project_id}")
        manager = getPipelineManager()
        if project_id == "":
            pid = manager.create_project("test", "audio")
        else:
            pid = project_id
        if index == -1:  # 是生成过程
            manager.update_config(project_id=pid, config=request)
        audio_result = manager.gen_audio(
            pid,
            text=request.text,
            model_name=request.audio_model_name,
            api_key=request.audio_api_key,
            voice=request.voice or "",
            language=request.language or "",
            index=index,
        )
        if not audio_result["success"]:
            manager.save_project(pid)
        response = AudioResponse(
            success=audio_result["success"],
            error=audio_result.get("error"),
            audio_path=audio_result["audio_path"],
            duration=audio_result["duration"],
        )
        logger.info(f"音频生成完成: success={audio_result['success']}, path={audio_result['audio_path']}")
        return response
    except Exception as e:
        logger.error(f"音频生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
