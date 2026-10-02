from app.configs.credentials import require_env
import time, os
from pathlib import Path
import requests


class FluxEngine:
    def __init__(self, image_api_key: str = ""):
        self.api_key = os.getenv("FLUX_API_KEY", "").strip() or require_env("IMAGE_MODEL_PASSWORD")

    def generate_images(
        self,
        prompt: str,
        n: int = 1,
        size: str = "512*512",
        output_dir: str = "app/assets/temp/images"
    ):
        timestamp = int(time.time() * 1000)
        output_path = Path(output_dir) / f"flux_img_{timestamp}_{0}.png"

        header = {"X-API-Key": self.api_key}
        payload = {
            "model": "Qubico/flux1-dev",
            "task_type": "txt2img",
            "input": {
                "prompt": "a little cat",
                "width": 1024, 
                "height": 1024
            } 
        }       
        resp = requests.post("https://api.piapi.ai/api/v1/task", json=payload,headers=header).json()
        # print(resp)

        task_id = resp["data"]["task_id"]
        status ="pending"
        while status != "completed":
            # print(resp)
            time.sleep(3)
            resp=requests.get(f"https://api.piapi.ai/api/v1/task/{task_id}",headers=header).json()
            status=resp["data"]["status"]
        # print(resp)

        image_url = resp["data"]["output"]["image_url"]  # 图片网址
        # save_path = "image.png"  # 本地保存路径

        response = requests.get(image_url)

        # 以二进制写入文件
        with open(output_path, "wb") as f:
            f.write(response.content)

        print("保存成功:", output_path)

        return [str(output_path)]

    def release(self):
        pass


if __name__ == "__main__":
    flux=FluxEngine()
    flux.generate_images("a cat in sofa")
