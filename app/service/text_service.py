"""
app/service/text_service.py
===========================
文本生成服务（兼容层）

【注意】：建议使用新的 ContentGenerationService
from app.service.content_service import ContentGenerationService

此类保留用于向后兼容，内部已迁移到新的 Pipeline 架构
"""
from app.service.content_service import ContentGenerationService


class TextGenerationService:
    """
    文本生成服务（兼容层）
    内部委托给 ContentGenerationService
    """

    def __init__(self):
        self._service = ContentGenerationService()
        self._current_model = None

    def use_model(self, model_name: str, api_key: str):
        """选择模型"""
        self._current_model = (model_name, api_key)
        return self

    def use_polish_model(self, model_name: str, api_key: str):
        """选择打磨模型（同 use_model）"""
        return self.use_model(model_name, api_key)

    def release_model(self):
        """释放模型资源"""
        self._current_model = None

    def generate_text(self, theme: str, style: str = None, language: str = None) -> str:
        """
        生成文案
        """
        if self._current_model is None:
            raise RuntimeError("请先调用 use_model() 选择模型")

        model_name, api_key = self._current_model
        result = self._service.generate(
            theme=theme,
            model_name=model_name,
            api_key=api_key,
            style=style,
            language=language,
        )
        return result["content"]

    def polish_media_prompts(self, text: str, language: str = None, media_model_name: str = "", media_prompt_style: str = None, texts: str = None) -> str:
        """
        打磨 media prompt
        """
        if self._current_model is None:
            raise RuntimeError("请先调用 use_model() 选择模型")

        model_name, api_key = self._current_model
        return self._service.polish_media_prompts(
            text,
            model_name,
            api_key,
            language=language,
            media_model_name=media_model_name,
            media_prompt_style=media_prompt_style,
            texts=texts,
        )

    def polish_prompts(self, text: str, language: str = None, image_model_name: str = "") -> str:
        return self.polish_media_prompts(
            text=text,
            language=language,
            media_model_name=image_model_name,
            media_prompt_style="image_default",
        )


def split_text(text: str):
    """按行分割文本"""
    return text.split("\n")
