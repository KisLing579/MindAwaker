
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HOME"] = "/root/autodl-tmp/data/hf_cache"
os.environ["HF_HUB_CACHE"] = "/root/autodl-tmp/data/hf_cache"
os.environ["HUGGINGFACE_HUB_CACHE"] = "/root/autodl-tmp/data/hf_cache"
os.environ["TRANSFORMERS_CACHE"] = "/root/autodl-tmp/data/hf_cache"
import time
import wave
from pathlib import Path
from auralis import TTS, TTSRequest,AudioPreprocessingConfig
import gc
import torch
from app.tts_engine.base_tts import BaseTTS
from app.utils.config_loader import get_voice_path

class AuralisTTS(BaseTTS):
    def __init__(self):
        self.tts = TTS().from_pretrained("AstraMindAI/xttsv2", gpt_model='AstraMindAI/xtts2-gpt')

    def release(self):
        self.tts.engine = None
        del self.tts
        gc.collect()
        torch.cuda.empty_cache()


    def synthesize(self,text:str,voice:str,output_dir: str = "app/assets/temp/audio", language: str = ""):

        voice_path=get_voice_path(voice)
        print("voice_path:",voice_path)
        # Generate speech
        request = TTSRequest(
            text=text,
            # speaker_files=['reference.mp3','reference2.mp3','reference3.mp3'],
            speaker_files=[voice_path],
            enhance_speech=True,
            audio_config=AudioPreprocessingConfig(
                normalize=False,
                trim_silence=False,
                enhance_speech=True,
                enhance_amount=1.5
            )
            # speaker_files=['me2.mp3']
        )
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = Path(output_dir) / f"auralis_tts_{timestamp}.wav"
        output = self.tts.generate_speech(request)
        output.save(output_path)


        # 计算音频时长
        with wave.open(str(output_path), "rb") as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = round(frames / float(rate), 2)
        return str(output_path), duration
      