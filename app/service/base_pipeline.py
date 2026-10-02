"""
Pipeline 基类
提供通用的模型管理、LLM调用、模板渲染能力
"""
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.langchain_pipeline.base_text import BaseTextGenerator


class BasePipeline(ABC):
    """
    内容生成 Pipeline 基类

    子类需要实现：
    - parse(): 解析输入文本为结构化数据
    - generate(): 执行完整生成流程
    """

    def __init__(self, generator_class: type[BaseTextGenerator]):
        """
        Args:
            generator_class: 使用的生成器类（如 LangChainTextGenerator）
        """
        self.generator = generator_class()

    def use_model(self, model_name: str, api_key: str):
        """选择并初始化模型"""
        return self.generator.select_model(model_name, api_key)

    def release_model(self):
        """释放模型资源"""
        self.generator.unload_model()

    def _render_template(self, template: str, **kwargs) -> str:
        """
        渲染模板，替换 {{key}} 占位符
        """
        text = template
        for key, value in kwargs.items():
            placeholder = "{{" + key + "}}"
            if isinstance(value, str):
                text = text.replace(placeholder, value)
            else:
                text = text.replace(placeholder, json.dumps(value, ensure_ascii=False))
        return text

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 生成文本"""
        return self.generator.generate(prompt)

    @abstractmethod
    def parse(self, text: str) -> Any:
        """
        解析输入文本为结构化数据
        子类必须实现
        """
        pass

    @abstractmethod
    def generate(self, *args, **kwargs) -> Dict[str, Any]:
        """
        执行完整生成流程
        子类必须实现
        """
        pass
