from app.model.credential_request import CredentialRequest
"""
app/model/video_schema.py
========================
定义视频生成的输入与输出数据结构
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal


class VideoRequest(CredentialRequest):
    # pid:str=Field(...,description="项目ID")
    theme: Optional[str] = Field(
        None, description="视频主题或关键词，当style为story且提供article时可为空"
    )
    style: Optional[str] = Field(None, description="可选文案风格（如 温柔 / 励志 / 科普）")
    text_model_name: str = Field(..., description="使用的大模型名称（如 gpt-4-turbo）")
    text_api_key: str = Field("", description="Deprecated; credentials are read from server environment")
    audio_model_name: str = Field(..., description="使用的大模型名称（如 gpt-4-turbo）")
    audio_api_key: str = Field("", description="Deprecated; credentials are read from server environment")
    image_model_name: str = Field(..., description="使用的大模型名称（如 gpt-4-turbo）")
    image_api_key: str = Field("", description="Deprecated; credentials are read from server environment")
    article: Optional[str] = Field(None, description="上传的文章内容，当style为story时使用")
    voice: Optional[str] = Field("alloy", description="语音类型（如 alloy, verse, nova）")
    size: Optional[str] = Field("1024*720", description="生成图像尺寸")
    n: Optional[int] = Field(1, description="生成图像数量")
    clip_mode: Literal["static", "jimeng"] = "static"
    clip_video_prompt: str = Field("", max_length=800)
    language: Optional[Literal["zh", "en"]] = Field(None, description="内容语言")
    with_media_prompts: bool = Field(True, description="是否生成 media prompt")
    media_prompt_style: Optional[str] = Field(None, description="media prompt 风格")


class VideoResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    video_path: str = ""


class VideoTaskResponse(BaseModel):
    """视频任务创建响应"""

    task_id: str
    project_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""

    task_id: str
    project_id: str
    type: str
    status: str
    progress: int
    stage: str
    message: str
    created_at: str
    updated_at: str
    result: Optional[dict] = None
    error: Optional[str] = None
    done: bool
