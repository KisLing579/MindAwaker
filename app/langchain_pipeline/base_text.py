from app.configs.credentials import text_api_key
"""
LangChain 文本生成基类
提供统一的模型选择、资源管理和生成接口
"""
import gc
from typing import Optional
from abc import ABC, abstractmethod


# DeepSeek 使用 OpenAI 兼容接口
try:
    from langchain_deepseek import ChatDeepSeek
except ImportError:
    from langchain_openai import ChatOpenAI as ChatDeepSeek
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from app.text_engine.deepseek_model import DeepseekModel


class BaseTextGenerator(ABC):
    """
    文本生成器基类
    子类需要实现 generate() 方法
    """

    def __init__(self):
        self.model = None

    def select_model(self, model_name: str, api_key: str):
        """
        选择并初始化模型
        支持：gpt-*, deepseek-*, claude-*, gemini-*
        """
        api_key = text_api_key(model_name)
        name = model_name.lower()

        if "gpt" in name:
            self.model = ChatOpenAI(
                api_key=api_key,
                model=model_name,
                temperature=0.7
            )
        elif "deepseek" in name:
            self.model = DeepseekModel(text_api_key=api_key)
        elif "claude" in name:
            self.model = ChatAnthropic(api_key=api_key, model=model_name)
        elif "gemini" in name:
            self.model = ChatGoogleGenerativeAI(api_key=api_key, model=model_name)
        else:
            raise ValueError(f"暂不支持的模型名称：{model_name}")

    def unload_model(self, model=None, tokenizer=None):
        """
        卸载模型并释放资源
        """
        if hasattr(self, 'model') and self.model is not None:
            try:
                # 先尝试把模型挪回 CPU（对 accelerate/device_map 特别有用）
                self.model.cpu()
            except Exception:
                pass

            del self.model
            self.model = None

        if tokenizer is not None:
            del tokenizer

        gc.collect()
        # torch.cuda.empty_cache()

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        生成文本
        子类必须实现此方法
        """
        pass

    def _invoke_model(self, prompt: str) -> dict:
        """
        内部方法：调用模型
        返回统一格式的响应字典
        """
        if self.model is None:
            raise RuntimeError("模型未初始化，请先调用 select_model()")
        return self.model.invoke(prompt)
