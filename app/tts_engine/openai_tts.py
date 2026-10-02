"""
app/tts_engine/openai_tts.py
============================
调用 OpenAI TTS API 生成音频并计算时长。
"""

import os
import time
from pathlib import Path
import openai
import wave
from app.configs.credentials import require_env

class OpenAITTS:
    def __init__(self, model="gpt-4o-mini-tts"):
        self.model = model

    def synthesize(self, text: str, voice: str, api_key: str):
        """
        调用 OpenAI TTS API 生成音频文件
        返回 (audio_path, duration)
        """
        openai.api_key = require_env("OPENAI_API_KEY")
        output_dir = Path("app/assets/temp/audio")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = output_dir / f"tts_{timestamp}.wav"

        # 调用 API
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text
        ) as response:
            response.stream_to_file(str(output_path))

        # 获取音频时长
        with wave.open(str(output_path), "rb") as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = round(frames / float(rate), 2)

        return str(output_path), duration
