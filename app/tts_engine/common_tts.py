# 以 Coqui TTS 为例 —— 延迟初始化，避免 import 时加载模型
import os
from TTS.api import TTS


_tts_instance = None


def get_tts(model_name: str = None):
    global _tts_instance
    if _tts_instance is None:
        model = model_name or os.getenv("COQUI_TTS_MODEL", "tts_models/en/vctk/vits")
        _tts_instance = TTS(model_name=model)
    return _tts_instance


def release_tts():
    global _tts_instance
    _tts_instance = None


if __name__ == "__main__":
    tts = get_tts()
    speaker = tts.speakers[0] if tts.speakers else None
    tts.tts_to_file(text="你好，这是一个测试配音。", speaker=speaker, file_path="output.wav")
