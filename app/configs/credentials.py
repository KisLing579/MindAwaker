"""Server-only model credentials. Never persist these values in project data."""
import os


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"请在后端环境变量中设置 {name}")
    return value


def text_api_key(model_name: str) -> str:
    name = model_name.lower()
    for token, variable in (
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("gpt", "OPENAI_API_KEY"),
        ("claude", "ANTHROPIC_API_KEY"),
        ("gemini", "GOOGLE_API_KEY"),
    ):
        if token in name:
            return require_env(variable)
    raise ValueError(f"暂不支持的模型名称：{model_name}")


def volc_credentials():
    """Prefer separate AK/SK; support the former image password field as AK**SK."""
    access_key = os.getenv("VOLC_ACCESS_KEY", "").strip()
    secret_key = os.getenv("VOLC_SECRET_KEY", "").strip()
    if access_key and secret_key:
        return access_key, secret_key
    password = os.getenv("IMAGE_MODEL_PASSWORD", "").strip()
    if password:
        parts = password.split("**")
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError("火山引擎 IMAGE_MODEL_PASSWORD 格式应为 AccessKey**SecretKey，或分别设置 VOLC_ACCESS_KEY 和 VOLC_SECRET_KEY")
        return access_key or parts[0].strip(), secret_key or parts[1].strip()
    return require_env("VOLC_ACCESS_KEY"), require_env("VOLC_SECRET_KEY")


def clear_legacy_credentials(value):
    """Keep empty compatibility fields while discarding old saved credentials."""
    if isinstance(value, dict):
        return {
            key: "" if key in {
                "text_api_key", "audio_api_key", "image_api_key",
                "default_text_api_key", "default_audio_api_key", "default_image_api_key",
            } else clear_legacy_credentials(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [clear_legacy_credentials(item) for item in value]
    return value
