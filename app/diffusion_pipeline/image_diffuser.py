"""
app/image_engine/diffuser_image.py
===================================
使用 Diffusers (Stable Diffusion) 本地推理生成图像。
支持：
- SD 1.5 / SDXL 等模型
- 自定义 prompt、分辨率、张数
"""

import os

# os.environ.update({
#     "HF_ENDPOINT": "https://hf-mirror.com",   # 国内镜像
#     "HF_HUB_ENABLE_HF_TRANSFER": "1",         # 开启多线程
#     "HF_HOME": "/root/autodl-tmp/data/hf_cache",
#     "HF_HUB_CACHE": "/root/autodl-tmp/data/hf_cache",
#     "HUGGINGFACE_HUB_CACHE": "/root/autodl-tmp/data/hf_cache",
#     "TRANSFORMERS_CACHE": "/root/autodl-tmp/data/hf_cache"
# })
# os.environ.update({
#     "HF_ENDPOINT": "https://hf-mirror.com",   # 国内镜像
#     "HF_HUB_ENABLE_HF_TRANSFER": "0",         # 开启多线程
#     "HF_HOME": "/root/autodl-tmp/data/hf_cache",
#     "HF_HUB_CACHE": "/root/autodl-tmp/data/hf_cache",
#     "HUGGINGFACE_HUB_CACHE": "/root/autodl-tmp/data/hf_cache",
#     "TRANSFORMERS_CACHE": "/root/autodl-tmp/data/hf_cache"
# })

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HOME"] = "/root/autodl-tmp/data/hf_cache"
os.environ["HF_HUB_CACHE"] = "/root/autodl-tmp/data/hf_cache"
os.environ["HUGGINGFACE_HUB_CACHE"] = "/root/autodl-tmp/data/hf_cache"
os.environ["TRANSFORMERS_CACHE"] = "/root/autodl-tmp/data/hf_cache"

import time
from pathlib import Path
import torch
from diffusers import StableDiffusionXLPipeline,StableDiffusionPipeline, DPMSolverMultistepScheduler
# 加载模型（例如 stable-diffusion-1.5）model_id = "runwayml/stable-diffusion-v1-5"/stabilityai/stable-diffusion-xl-base-1.0
import huggingface_hub
from compel import Compel
from compel.embeddings_provider import ReturnedEmbeddingsType
import gc
print("HF 缓存路径:", huggingface_hub.constants.HF_HUB_CACHE)

class DiffuserImage:
    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype: torch.dtype = torch.float16,
        device: str = "cuda"
    ):
        # """
        # 初始化 Diffusers pipeline。
        # model_id: Hugging Face 上的模型名或本地路径。
        # """
        # self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # print(f"💡 Using device: {self.device}")
        # print(f"加载：{model_id}")
        # try:
        #     self.pipe = StableDiffusionXLPipeline.from_pretrained(
        #         model_id,
        #         torch_dtype=torch_dtype,
        #         safety_checker=None
        #     )
        # except Exception as e:
        #     print(f"出错了->{e}")
        # print("after load model")
        # self.pipe.scheduler = DPMSolverMultistepScheduler.from_config(self.pipe.scheduler.config)
        # print("after set scheduler")
        # self.pipe = self.pipe.to(self.device)
        # print("finish init Diffuser Image")
        # print("Pipe device:", self.pipe.device)

        # print("Text encoder device:", next(self.pipe.text_encoder.parameters()).device)
        # print("UNet device:", next(self.pipe.unet.parameters()).device)
        # print("VAE device:", next(self.pipe.vae.parameters()).device)

        # 1. 加载基础 SDXL 模型
        base_model = "/root/autodl-tmp/data/sdxl"  # 或 "stabilityai/stable-diffusion-xl-base-1.0"
        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            base_model,
            torch_dtype=torch.float16,
            use_safetensors=True,
        ).to("cuda")
        # lora_path = "/root/AIStoryComposer/Lora/last.safetensors"  
        # self.pipe.load_lora_weights(
        #     lora_path,
        #     weight=0.9    # LoRA 强度，可以试 0.6~1.0 之间调
        # )

    def release(self):
        del self.pipe
        gc.collect()
        torch.cuda.empty_cache()

    def generate_images(
        self,
        prompt: str,
        n: int = 1,
        size: str = "512*512",
        output_dir: str = "app/assets/temp/images",
        guidance_scale: float = 7.5,
        num_inference_steps: int = 25
    ):
        """
        根据提示词生成图像。
        """
        print("before make the output path")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        print("make the output path")
        width, height = [int(x) for x in size.split("*")]
        
        results = []
        for i in range(n):
            timestamp = int(time.time() * 1000)
            output_path = Path(output_dir) / f"diffuser_img_{timestamp}_{i}.png"

            # print("before create image")
            # print(f"pipe type:{type(self.pipe)}")
            # print(self.pipe.tokenizer)
            # print(self.pipe.tokenizer_2)

            # try:
            #     with torch.inference_mode():
            #         images = self.pipe(
            #             prompt=prompt,
            #             width=width,
            #             height=height,
            #             num_inference_steps=num_inference_steps,
            #             guidance_scale=guidance_scale
            #         )
            # except Exception as e:
            #     print(f"生成图像时出错：{e}")


            # tokenizer = self.pipe.tokenizer
            # max_len = tokenizer.model_max_length  # 一般为 77
            # # tokens = tokenizer(prompt, truncation=False, return_tensors="pt")["input_ids"].to(self.device)
            # # chunks = [tokens[:, i:i + max_len] for i in range(0, tokens.shape[1], max_len)]
            # embeds=[]
            # pooled_embeds=[]
            # text_encoder = self.pipe.text_encoder
            
            # for chunk in chunks:
            #     res=text_encoder(chunk)
            #     embeds.append(res[0])
            #     pooled_embeds.append(res.pooler_output)

            # max_len_words=min(30,int(max_len/2))
            # words = prompt.split()
            # chunks = [" ".join(words[i:i + max_len_words]) for i in range(0, len(words), max_len_words)]
            # for chunk in chunks:
            #     res = self.pipe.encode_prompt([chunk])
            #     embeds.append(res[0])
            #     pooled_embeds.append(res[2])
                            

            # final_embeds = torch.cat(embeds, dim=1)
            # # final_pooled_embeds= torch.mean(torch.stack(pooled_embeds), dim=0)
            # final_pooled_embeds= torch.cat(pooled_embeds, dim=1)
            # with torch.inference_mode():
            #     images = self.pipe(
            #         prompt_embeds=final_embeds,
            #         pooled_prompt_embeds=final_pooled_embeds,
            #         num_inference_steps=num_inference_steps,
            #         guidance_scale=guidance_scale,
            #         width=width,
            #         height=height
            #     )
            # tokenizer1 = self.pipe.tokenizer
            # tokenizer2 = self.pipe.tokenizer_2
            # text_encoder1 = self.pipe.text_encoder
            # text_encoder2 = self.pipe.text_encoder_2

            # max_len = tokenizer1.model_max_length  # 77

            # # 第1个tokenizer分块
            # tokens1 = tokenizer1(prompt, truncation=False, return_tensors="pt")["input_ids"].to(self.device)
            # chunks1 = [tokens1[:, i:i + max_len] for i in range(0, tokens1.shape[1], max_len)]

            # # 第2个tokenizer分块
            # tokens2 = tokenizer2(prompt, truncation=False, return_tensors="pt")["input_ids"].to(self.device)
            # chunks2 = [tokens2[:, i:i + max_len] for i in range(0, tokens2.shape[1], max_len)]

            # # 逐块编码
            # embeds1, pooled1 = [], []
            # embeds2, pooled2 = [], []

            # for c1, c2 in zip(chunks1, chunks2):
            #     r1 = text_encoder1(c1)
            #     r2 = text_encoder2(c2)
            #     embeds1.append(r1[0])
            #     embeds2.append(r2[0])
            #     pooled1.append(r1.pooler_output)
            #     if hasattr(r2, "text_embeds"):
            #         pooled2.append(r2.text_embeds)
            #     else:
            #         pooled2.append(r2[1])  # 有些版本返回 (last_hidden_state, text_embeds)


            # # 拼接每个encoder的结果
            # final_embeds1 = torch.cat(embeds1, dim=1)
            # final_embeds2 = torch.cat(embeds2, dim=1)
            # final_pooled1 = torch.mean(torch.stack(pooled1), dim=0)
            # final_pooled2 = torch.mean(torch.stack(pooled2), dim=0)

            # with torch.inference_mode():
            #     images = self.pipe(
            #         prompt_embeds=final_embeds1,
            #         prompt_embeds_2=final_embeds2,
            #         pooled_prompt_embeds=final_pooled1,
            #         pooled_prompt_embeds_2=final_pooled2,
            #         num_inference_steps=num_inference_steps,
            #         guidance_scale=guidance_scale,
            #         width=width,
            #         height=height
            #     ).images


            #初始化 Compel（支持 SDXL 的两套 encoder）
            compel = Compel(
                tokenizer=[self.pipe.tokenizer, self.pipe.tokenizer_2],
                text_encoder=[self.pipe.text_encoder,self.pipe.text_encoder_2],
                returned_embeddings_type=ReturnedEmbeddingsType.PENULTIMATE_HIDDEN_STATES_NON_NORMALIZED,
                requires_pooled=[False,True]  # SDXL 需要 pooled embedding
            )

            # prompt = "(a futuristic city:1.5), ultra detailed, cinematic lighting, 8K render"

            # 生成 embeddings
            prompt_embeds, pooled_prompt_embeds = compel(prompt)

            # 用 SDXL 生成图像
            image = self.pipe(
                prompt_embeds=prompt_embeds,
                pooled_prompt_embeds=pooled_prompt_embeds,
                width=1024,
                height=1024,
                num_inference_steps=30
            ).images[0]
            # negative_prompt = "low quality, bad anatomy, blurry, distorted"
            # image = self.pipe(
            #     prompt=prompt,
            #     negative_prompt=negative_prompt,
            #     num_inference_steps=30,
            #     guidance_scale=7.0,
            # ).images[0]
            # image=images[0]
            print(f"after create image ")
            print(f"before save image in path :{output_path}")
            try:
                image.save(output_path)
            except Exception as e:
                print(f"保存图像时出错：{e}")
            print(f"after save image in path :{output_path}")
            results.append(str(output_path))

        return results
