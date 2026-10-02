from app.service.text_service import TextGenerationService
from app.service.audio_service import AudioGenerationService
from app.service.image_service import ImageGenerationService
from app.service.subtitle_service import SubtitleService
# from app.service.story_prompt_pipleline import StoryPromptPipeline

textGenerationService = TextGenerationService()
imageGenerationService = ImageGenerationService()
audioGenerationService = AudioGenerationService()
sub = SubtitleService()
# storyPromptPipeline= StoryPromptPipeline()

def get_text_service():
    return textGenerationService

def get_audio_service():
    return audioGenerationService

def get_image_service():
    return imageGenerationService

def get_subtitle_service():
    return sub

# def get_story_prompt_pipeline():
#     return storyPromptPipeline