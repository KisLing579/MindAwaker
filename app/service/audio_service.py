"""
app/service/audio_service.py
=============================
封装音频生成逻辑
"""

import os
from app.tts_engine.azure_tts import AzureTTS
from app.utils.language_utils import sanitize_tts_text
# from app.tts_engine.auralis_tts import AuralisTTS


class AudioGenerationService:
    def __init__(self):
        # self.engine = AzureTTS()
        # self.engine = AuralisTTS()
        pass
    def create_engine(self,audio_model_name:str,audio_api_key:str=""):
        if "auralis" in audio_model_name:
            self.engine =AuralisTTS()
            return True
        if "azure" in audio_model_name:
            self.engine = AzureTTS(key=audio_api_key)
            return True
        else:
            return False
    def release_engine(self):
        self.engine.release()

    def generate_audio(self, text: str,voice: str="", output_dir:str="", language: str = ""):
        cleaned_text = sanitize_tts_text(text, language=language)
        # output_path, duration = self.engine.synthesize(key=api_key, text=text,voice=voice)
        if output_dir=="":
            output_path, duration = self.engine.synthesize(text=cleaned_text,voice=voice, language=language)
        else:
            output_path, duration = self.engine.synthesize(text=cleaned_text,voice=voice,output_dir=output_dir, language=language)
        return True,output_path,duration