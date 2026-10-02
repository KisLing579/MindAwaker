"""
app/tts_engine/deepseek_tts.py
==============================
基于 DeepSeek 平台的 TTS（语音合成）模块。
特点：
- 兼容 OpenAI 格式 API（base_url 不同）
- 自动保存音频文件
- 计算音频 duration
- 返回 (path, duration)
"""

import os
import time
import wave
from pathlib import Path
from openai import OpenAI
from app.configs.credentials import require_env


class DeepSeekTTS:
    def __init__(self, model: str = "deepseek-tts"):
        """
        DeepSeek TTS 初始化
        model: 默认 "deepseek-tts"（兼容 OpenAI 格式）
        voice: 声音名称，可选值根据 DeepSeek 平台更新
        """
        self.model = model
        # DeepSeek 的 OpenAI 兼容 API base
        self.base_url = "https://api.deepseek.com/v1"

    def synthesize(self, text: str, api_key:str, voice: str = "alloy", output_dir: str = "app/assets/temp/audio") -> tuple[str, float]:
        """
        生成音频文件
        返回 (audio_path, duration)
        """
        # 初始化客户端
        client = OpenAI(api_key=require_env("DEEPSEEK_API_KEY"), base_url=self.base_url)

        # 输出路径准备
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = Path(output_dir) / f"deepseek_tts_{timestamp}.wav"

        try:
            # 调用 DeepSeek 的 TTS 接口
            with client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=voice,
                input=text
            ) as response:
                response.stream_to_file(str(output_path))

            # 计算音频时长
            with wave.open(str(output_path), "rb") as f:
                frames = f.getnframes()
                rate = f.getframerate()
                duration = round(frames / float(rate), 2)

            return str(output_path), duration

        except Exception as e:
            print(f"⚠️ DeepSeek TTS 生成失败: {str(e)}")
            return "", 0.0
