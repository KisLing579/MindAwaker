from app.configs.credentials import require_env
import os
import requests


class DeepseekModel:
    def __init__(self, text_api_key: str = ""):
        self.api_key = require_env("DEEPSEEK_API_KEY")

    def invoke(self, text: str = ""):
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": f"{text}"}],
                "temperature": 0.3,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",  # 避免某些链路对 gzip+chunked 搞事
                "Connection": "close",  # 规避复用连接的偶发问题（代价是慢一点）
            },
            timeout=180,  # 连接超时+读取超时，防止永久挂起
        ).json()
        print(resp)
        return resp["choices"][0]["message"]
