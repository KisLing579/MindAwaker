from app.configs.credentials import volc_credentials
import base64
import os
import time
from pathlib import Path
# coding:utf-8

from volcengine import visual
from volcengine.visual.VisualService import VisualService


class VolcEngine:
    def __init__(self, image_api_key: str = ""):
        self.access_key, self.secret_key = volc_credentials()
        self.visual_service = VisualService()
        self.visual_service.set_ak(self.access_key)
        self.visual_service.set_sk(self.secret_key)

    def generate_images(
        self,
        prompt: str,
        n: int = 1,
        size: str = "512*512",
        output_dir: str = "app/assets/temp/images"
    ):
        
        timestamp = int(time.time() * 1000)
        output_path = Path(output_dir) / f"jimeng_img_{timestamp}_{0}.png"


        # call below method if you don't set ak and sk in $HOME/.volc/config
        
        # https://visual.volcengineapi.com/?Action=CVSync2AsyncSubmitTask&Version=2022-08-31
        # action = "CVSync2AsyncSubmitTask"
        # version = "2022-08-31"
        # self.visual_service.set_api_info(action, version)
        width,height = size.split("*")
        # 请求Body(查看接口文档请求参数-请求示例，将请求参数内容复制到此)
        print("width=",width,"height=",height)
        form = {
            "req_key": os.getenv("VOLC_REQ_KEY", "jimeng_t2i_v40"),
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
            "seed": 1000,
        }
        
        resp =self.visual_service.cv_process(form)

        img_base64 = resp["data"]["binary_data_base64"][0]

        # 解码
        img_bytes = base64.b64decode(img_base64)

        # 保存为文件
        with open(output_path, "wb") as f:
            f.write(img_bytes)

        print("保存成功：output.png")

        return [str(output_path)]
    
    # 保存图片到本地
    def release(self):
         if self.visual_service is not None:
            del self.visual_service

if __name__ == '__main__':
     engine = VolcEngine()
     engine.generate_images(prompt="一只小猫在沙发上", n=1, size="1024*720", output_dir="images")
