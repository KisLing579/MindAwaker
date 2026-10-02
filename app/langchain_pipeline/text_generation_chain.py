"""
LangChain 文案生成链（适配新版LangChain）
"""
from typing import Optional

from langchain_core.prompts import PromptTemplate

from app.langchain_pipeline.base_text import BaseTextGenerator
from app.utils.config_loader import get_default_language, get_media_prompt_template_path, get_template_path
from app.utils.language_utils import get_default_media_prompt_language, resolve_language


def _read_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _normalize_template(template: str) -> str:
    return (
        template
        .replace("{{ THEME }}", "{theme}")
        .replace("{{THEME}}", "{theme}")
        .replace("{THEME}", "{theme}")
        .replace("{{ theme }}", "{theme}")
        .replace("{{theme}}", "{theme}")
        .replace("{{ style }}", "{style}")
        .replace("{{style}}", "{style}")
        .replace("{{ input }}", "{input}")
        .replace("{{input}}", "{input}")
        .replace("{{ text }}", "{text}")
        .replace("{{text}}", "{text}")
        .replace("{{ texts }}", "{texts}")
        .replace("{{texts}}", "{texts}")
        .replace("{{ contexts }}", "{contexts}")
        .replace("{{contexts}}", "{contexts}")
    )


def _load_prompt_template(path: str) -> PromptTemplate:
    #临时添加
    print("prompt path===>",path)
    normalized_template = _normalize_template(_read_template(path))
    variables = []
    for variable in ("theme", "style", "input", "text", "texts", "contexts"):
        if f"{{{variable}}}" in normalized_template:
            variables.append(variable)
    return PromptTemplate(template=normalized_template, input_variables=variables)


def _render_media_prompt(
    generator: "LangChainTextGenerator",
    text: str,
    prompt_style: Optional[str],
    target_language: str,
    texts: Optional[str] = None,
) -> str:
    prompt_path = get_media_prompt_template_path(prompt_style, target_language)
    #临时添加
    print("media prompt path====>",prompt_path)
    prompt_template = _load_prompt_template(prompt_path)
    context_value = texts or text
    prompt_payload = {
        "input": text,
        "contexts": context_value,
        "text": text,
        "texts": context_value,
        "style": prompt_style or "",
    }
    response_text = generator._invoke_model(prompt_template.format(**prompt_payload))
    return response_text["content"].strip()



class LangChainTextGenerator(BaseTextGenerator):
    """文案生成器"""

    def generate(self, theme: str, style: Optional[str] = None, language: Optional[str] = None) -> str:
        """生成文案"""
        resolved_language = resolve_language(theme, requested_language=language, default_language=get_default_language())
        template_path = get_template_path(style, resolved_language)
        #临时添加
        print("template path=====>",template_path)

        prompt = _load_prompt_template(template_path)
        rendered = prompt.format(theme=theme, style=style or "")
        response_text = self._invoke_model(rendered)
        return response_text["content"].strip()

    def polish_media_prompts(
        self,
        text: str,
        language: Optional[str] = None,
        media_model_name: str = "",
        media_prompt_style: Optional[str] = None,
        texts: Optional[str] = None,
    ) -> str:
        """打磨 media prompt"""
        source_language = resolve_language(text, requested_language=language, default_language=get_default_language())
        target_language = get_default_media_prompt_language(media_model_name, requested_language=language)
        if source_language == target_language:
            return _render_media_prompt(self, text, media_prompt_style, target_language, texts=texts)
        return _render_media_prompt(self, text, media_prompt_style, target_language, texts=texts)

    def polish_prompts(
        self,
        text: str,
        language: Optional[str] = None,
        image_model_name: str = "",
    ) -> str:
        return self.polish_media_prompts(
            text=text,
            language=language,
            media_model_name=image_model_name,
            media_prompt_style="image_default",
        )
