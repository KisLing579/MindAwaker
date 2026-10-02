from app.model.credential_request import CredentialRequest
"""
app/model/image_schema.py
==========================
定义图像生成请求与响应的数据结构。
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class ImageRequest(CredentialRequest):
    # pid:str=Field(...,description="项目ID")
    prompt: str = Field(..., description="图像生成提示词")
    image_api_key: str = Field("", description="Deprecated; credentials are read from server environment")
    image_model_name: str = Field("openai", description="使用的引擎，可选：openai / diffuser")
    size: Optional[str] = Field("1024*720", description="生成图像尺寸")
    n: Optional[int] = Field(1, description="生成图像数量")
    language: Optional[Literal["zh", "en"]] = Field(None, description="提示词语言")


class ImageResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    project: Optional[dict] = None
    image_paths: List[str] = Field(default_factory=list, description="生成的图像文件路径列表")
