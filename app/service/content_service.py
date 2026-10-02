"""
ContentGenerationService
统一内容生成服务入口
"""
from typing import Dict, Any, List, Optional
from enum import Enum

from app.configs.logging_config import get_logger
from app.service.story_pipeline import StoryPipeline, run_story_pipeline
from app.langchain_pipeline.text_generation_chain import LangChainTextGenerator

logger = get_logger(__name__)


class ContentType(str, Enum):
    """内容类型"""
    STORY = "story"           # 故事视频
    TEXT = "text"             # 纯文本生成


class ContentGenerationService:
    """
    统一内容生成服务

    根据 style 参数路由到对应 Pipeline：
    - story: StoryPipeline（背景+角色+分镜）
    - text: LangChainTextGenerator（纯文案）
    """

    def __init__(self):
        self._text_generator: Optional[LangChainTextGenerator] = None

    # ==================== 统一入口 ====================

    def generate(self, style: str, **kwargs) -> Dict[str, Any]:
        """
        统一生成入口

        Args:
            **kwargs: 根据类型不同传入不同参数

        Returns:
            标准化的生成结果
        """
        return self._generate_text(**kwargs)
    # ==================== 各类型实现 ====================

    def _generate_story(
        self,
        story: str,
        model_name: str,
        api_key: str,
        style_tokens: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成故事视频内容

        Args:
            model_name: 模型名称
            api_key: API密钥
            style_tokens: 视觉风格词

        Returns:
            包含 segments（分镜列表）的结果
        """
        logger.info(f"Generating story content with model: {model_name}")

        result = run_story_pipeline(
            story=story,
            model_name=model_name,
            api_key=api_key,
            style_tokens=style_tokens,
        )

        result["style"] = "story"

        return result


    def _generate_text(
        self,
        theme: str,
        model_name: str,
        api_key: str,
        style: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成纯文本内容

        Args:
            theme: 主题
            model_name: 模型名称
            api_key: API密钥
            style: 文案风格模板

        Returns:
            生成的文案文本
        """
        logger.info(f"Generating text content with model: {model_name}")

        if self._text_generator is None:
            self._text_generator = LangChainTextGenerator()

        self._text_generator.select_model(model_name, api_key)

        try:
            text = self._text_generator.generate(theme=theme, style=style, language=language)
            print("received text=====>", text)
            return {
                "style": "text",
                "theme": theme,
                "content": text,
                "model": model_name,
                "language": language,
            }
        finally:
            self._text_generator.unload_model()

    def polish_media_prompts(
        self,
        text: str,
        model_name: str,
        api_key: str,
        language: Optional[str] = None,
        media_model_name: str = "",
        media_prompt_style: Optional[str] = None,
        texts: Optional[str] = None,
    ) -> str:
        """
        打磨 media prompt（通用工具方法）

        Args:
            text: 原始文本
            model_name: 模型名称
            api_key: API密钥

        Returns:
            优化后的提示词
        """
        if self._text_generator is None:
            self._text_generator = LangChainTextGenerator()

        self._text_generator.select_model(model_name, api_key)

        try:
            return self._text_generator.polish_media_prompts(
                text,
                language=language,
                media_model_name=media_model_name,
                media_prompt_style=media_prompt_style,
                texts=texts,
            )
        finally:
            self._text_generator.unload_model()

    def polish_prompts(self, text: str, model_name: str, api_key: str, language: Optional[str] = None, image_model_name: str = "") -> str:
        return self.polish_media_prompts(
            text=text,
            model_name=model_name,
            api_key=api_key,
            language=language,
            media_model_name=image_model_name,
            media_prompt_style="image_default",
        )




# ==================== 便捷函数 ====================

def get_content_service() -> ContentGenerationService:
    """获取服务实例（单例）"""
    return ContentGenerationService()
