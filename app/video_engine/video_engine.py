"""Jimeng 3.0 Pro first-frame video, with resumable remote task receipts."""
import base64
import hashlib
import io
import json
import math
import os
import shlex
import subprocess
import time
from pathlib import Path

import requests
from PIL import Image, ImageOps

REQ_KEY = "jimeng_i2v_first_v30"


def duration_plan(duration):
    duration = float(duration)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("配音时长必须为正数")
    parts = []
    while duration > 0.000001:
        # Keep the fixed 121-frame generation budget consistent with each part.
        seconds = min(5.0, duration)
        parts.append((seconds, 121))
        duration -= seconds
    return parts


def first_frame_bytes(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        width, height = image.size
        if max(width, height) / min(width, height) > 3:
            raise ValueError("即梦首帧图片长宽比不能超过 3:1")
        scale = min(1, 4096 / max(width, height))
        if min(width, height) * scale < 320:
            scale = 320 / min(width, height)
        image = image.resize((round(width * scale), round(height * scale)))
        for quality in (95, 85, 75):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            if buffer.tell() <= 4_700_000:
                return buffer.getvalue()
        raise ValueError("首帧图片压缩后仍超过 4.7 MB，请缩小图片")


def checked_data(response):
    if not isinstance(response, dict) or response.get("code") != 10000:
        response = response if isinstance(response, dict) else {}
        raise RuntimeError(f"即梦视频接口失败：{response.get('code')} {response.get('message', '无有效响应')} request_id={response.get('request_id', '')}")
    return response.get("data") or {}


class JimengVideo:
    def __init__(self, service=None):
        if service is None:
            from volcengine.visual.VisualService import VisualService
            from app.configs.credentials import volc_credentials
            service = VisualService()
            ak, sk = volc_credentials()
            service.set_ak(ak)
            service.set_sk(sk)
            service.set_connection_timeout(15)
            service.set_socket_timeout(60)
        self.service = service

    def generate(self, image_path, prompt, frames, cache_dir, cancelled=lambda: False, timeout=1800):
        if frames not in (121, 241):
            raise ValueError("即梦视频帧数仅支持 121 或 241")
        if not prompt.strip() or len(prompt) > 800:
            raise ValueError("视频提示词不能为空且不能超过 800 字")
        def check_cancel():
            if cancelled():
                raise InterruptedError("即梦视频生成已暂停，任务编号已保留，可继续查询")
        check_cancel()
        raw = first_frame_bytes(image_path)
        digest = hashlib.sha256(raw + json.dumps([REQ_KEY, prompt, frames]).encode()).hexdigest()
        directory = Path(cache_dir)
        directory.mkdir(parents=True, exist_ok=True)
        receipt = directory / f"{digest}.json"
        output = directory / f"{digest}.mp4"
        if output.is_file() and output.stat().st_size:
            return str(output)
        state = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
        if not state.get("task_id"):
            data = checked_data(self.service.cv_sync2async_submit_task({
                "req_key": REQ_KEY, "binary_data_base64": [base64.b64encode(raw).decode()],
                "prompt": prompt, "frames": frames, "seed": -1,
            }))
            if not data.get("task_id"):
                raise RuntimeError("即梦提交成功但未返回 task_id")
            state = dict(task_id=data["task_id"], req_key=REQ_KEY, frames=frames, prompt=prompt)
            receipt.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_cancel()
            data = checked_data(self.service.cv_sync2async_get_result({"req_key": REQ_KEY, "task_id": state["task_id"]}))
            status = data.get("status")
            if status == "done":
                url = data.get("video_url")
                if not url:
                    raise RuntimeError("即梦任务完成但未返回视频地址")
                temporary = output.with_suffix(".download")
                with requests.get(url, stream=True, timeout=(15, 60)) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as file:
                        for chunk in response.iter_content(1024 * 1024):
                            check_cancel()
                            file.write(chunk)
                if not temporary.stat().st_size:
                    raise RuntimeError("即梦返回空视频")
                temporary.replace(output)
                return str(output)
            if status in ("expired", "not_found"):
                state.pop("task_id", None)
                receipt.write_text(json.dumps(state), encoding="utf-8")
                raise RuntimeError("即梦任务已过期或不存在，请重试生成视频段")
            if status not in ("in_queue", "generating"):
                raise RuntimeError(f"即梦任务状态异常：{status}")
            for _ in range(5):
                check_cancel()
                time.sleep(1)
        raise TimeoutError("即梦视频等待超时，已保存任务编号；重试将继续查询")


LTX_REQ_KEY = "ltx_2_5_i2v"

LTX_DEFAULT_MODELS = {
    "transformer": "models/ltx-2.5/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
    "text_encoder": "models/ltx-2.5/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
    "video_vae": "models/ltx-2.5/vae/ltx-2.5-video-vae-bf16.safetensors",
    "audio_vae": "models/ltx-2.5/vae/ltx-2.5-audio-vae-bf16.safetensors",
    "spatial_upsampler": "models/ltx-2.5/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
}


class LTXVideo:
    """LTX-2.5 首帧视频生成，本地运行 ltx_pipelines.distilled 命令。

    workdir 为 LTX-Video 仓库根目录（含 pyproject.toml 与 ltx_pipelines 包），
    `uv run python -m ltx_pipelines.distilled` 在该目录下执行；模型路径默认相对于该目录，
    也可通过 models 字典或环境变量 LTX_WORKDIR 覆盖。
    """

    def __init__(self, workdir=None, models=None, seed=42):
        self.workdir = str(workdir or os.getenv("LTX_WORKDIR") or ".")
        self.models = dict(LTX_DEFAULT_MODELS)
        if models:
            self.models.update(models)
        self.seed = int(seed)

    def _build_command(self, image_path, prompt, frames, output_dir):
        models = self.models
        return [
            "uv", "run", "python", "-m", "ltx_pipelines.distilled",
            "--transformer-path", models["transformer"],
            "--text-encoder-path", models["text_encoder"],
            "--video-vae-path", models["video_vae"],
            "--audio-vae-path", models["audio_vae"],
            "--spatial-upsampler-path", models["spatial_upsampler"],
            "--num-frames", str(frames),
            "--seed", str(self.seed),
            "--output-path", str(output_dir),
            "--prompt", prompt,
            "--image", image_path, "0", "0.9",
        ]

    def _run_command(self, command, cancelled, timeout, log_path):
        deadline = time.monotonic() + max(float(timeout or 1800), 1.0)
        with log_path.open("wb") as log_file:
            print("command===============>",command)
            process = subprocess.Popen(command, cwd=self.workdir, stdout=log_file, stderr=subprocess.STDOUT)
            try:
                while process.poll() is None:
                    if cancelled():
                        process.kill()
                        process.wait()
                        raise InterruptedError("LTX 视频生成已停止")
                    if time.monotonic() >= deadline:
                        process.kill()
                        process.wait()
                        raise TimeoutError("LTX 视频生成超时，已保留日志，重试可继续")
                    time.sleep(1)
            except BaseException:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                raise
        if process.returncode != 0:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"LTX 视频生成失败（返回码 {process.returncode}）\n{tail}")

    def generate(self, image_path, prompt, frames, cache_dir, cancelled=lambda: False, timeout=1800):
        if not prompt.strip():
            raise ValueError("LTX 视频提示词不能为空")
        frames = int(frames)
        if frames <= 0:
            raise ValueError("LTX 视频帧数必须为正整数")
        image_path = str(Path(image_path).expanduser().resolve())
        if not Path(image_path).is_file():
            raise FileNotFoundError(f"LTX 首帧图片不存在：{image_path}")

        def check_cancel():
            if cancelled():
                raise InterruptedError("LTX 视频生成已停止")

        check_cancel()
        digest = hashlib.sha256(
            Path(image_path).read_bytes()
            + json.dumps([LTX_REQ_KEY, prompt, frames, self.seed], ensure_ascii=False).encode()
        ).hexdigest()
        # LTX runs with its own cwd; inputs and outputs belong to this process.
        directory = Path(cache_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        receipt = directory / f"{digest}.json"
        output = directory / f"{digest}.mp4"
        if output.is_file() and output.stat().st_size:
            return str(output)

        command = self._build_command(image_path, prompt, frames, output)
        
        receipt.write_text(json.dumps({
            "req_key": LTX_REQ_KEY, "prompt": prompt, "frames": frames, "seed": self.seed,
            "command": shlex.join(command),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        before = {path.resolve() for path in directory.rglob("*.mp4")}
        self._run_command(command, cancelled, timeout, directory / f"{digest}.log")
        check_cancel()

        produced = [path for path in directory.rglob("*.mp4") if path.resolve() not in before]
        if not produced and output.is_file():
            produced = [output]
        if not produced:
            raise RuntimeError("LTX 视频生成结束但未找到输出文件")
        newest = max(produced, key=lambda path: path.stat().st_mtime)
        if newest.resolve() != output.resolve():
            newest.replace(output)
        print("output=================>",str(output))
        return str(output)


def extract_continuation_frame(manager, video, seconds, output):
    """Seek within the actual video and require a valid continuation image."""
    import ffmpeg
    probe = ffmpeg.probe(str(video))
    video_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    actual_duration = float(video_stream.get("duration") or probe.get("format", {}).get("duration") or 0)
    if not math.isfinite(actual_duration) or actual_duration <= 0:
        raise RuntimeError(f"无法获取生成视频的有效时长：{video}")
    output = Path(output)
    temporary = output.with_name(output.stem + ".pending.jpg")
    # An old frame must not disguise an extraction that produces no image.
    temporary.unlink(missing_ok=True)
    seek = max(0, min(float(seconds), actual_duration) - 0.1)
    command = ffmpeg.output(ffmpeg.input(str(video), ss=seek).video,
                            str(temporary), vframes=1).overwrite_output()
    try:
        manager._run_ffmpeg_with_timeout(command, timeout=60)
        if not temporary.is_file() or not temporary.stat().st_size:
            raise RuntimeError(f"视频续接首帧抽取失败：{video}，视频时长 {actual_duration:.3f}s，抽帧位置 {seek:.3f}s")
        with Image.open(temporary) as frame:
            frame.verify()
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return str(output)


def render_clip_with_jimeng(manager, project_id, index, clip, output):
    print("================>run here")
    import ffmpeg
    from app.service.pipeline_manager import TASKS, update_progress
    task = TASKS[project_id]
    cancel = lambda: bool(task.get("stop_requested"))
    config = manager._normalize_config_for_save(manager.projects[project_id]["config"])
    prompt = (config.get("clip_video_prompt") or "保持首帧人物、物品和场景一致，主体自然运动，镜头平稳，动作连贯，不添加字幕。")
    segment = clip.get("prompt")
    if not config.get("clip_video_prompt") and isinstance(segment, dict):
        prompt += "\n" + str(segment.get("image_prompt") or segment.get("text") or "")[:600]
    directory = manager._artifact_section_dir(project_id, "jimeng_video").resolve()
    # engine = JimengVideo()
    engine = LTXVideo()
    first_frame = str(Path(clip["image_path"]).resolve())
    streams = []
    with Image.open(first_frame) as image:
        width, height = image.size
    width += width % 2
    height += height % 2
    plan = duration_plan(clip["duration"])
    for part, (seconds, frames) in enumerate(plan):
        if cancel():
            raise InterruptedError("视频段生成已停止")
        update_progress(project_id, 75, f"即梦视频段 {index + 1}，子段 {part + 1}/{len(plan)}，{frames} 帧")
        video = engine.generate(first_frame, prompt, frames, directory, cancel)
        stream = (ffmpeg.input(video).video.filter("scale", width, height)
                  .filter("setsar", 1).filter("fps", fps=30)
                  .filter("tpad", stop_mode="clone", stop_duration=seconds)
                  .filter("trim", duration=seconds).filter("setpts", "PTS-STARTPTS"))
        streams.append(stream)
        if part + 1 < len(plan):
            last = directory / f"{Path(video).stem}_last.jpg"
            first_frame = extract_continuation_frame(manager, video, seconds, last)
    if cancel():
        raise InterruptedError("视频段生成已停止")
    update_progress(project_id, 82, f"分镜 {index + 1}：{len(plan)} 个子段已生成，正在合成完整视频段并添加配音")
    video_stream = streams[0] if len(streams) == 1 else ffmpeg.concat(*streams, v=1, a=0)
    audio = ffmpeg.input(clip["audio_path"]).audio.filter("asetpts", "PTS-STARTPTS")
    temporary = Path(output).with_name(Path(output).stem + ".pending.mp4")
    command = ffmpeg.output(video_stream, audio, str(temporary), vcodec="libx264", pix_fmt="yuv420p",
                            acodec="aac", r=30, t=float(clip["duration"])).overwrite_output()
    manager._run_ffmpeg_with_timeout(command, timeout=max(120, int(float(clip["duration"]) * 12)))
    if not temporary.is_file() or not temporary.stat().st_size:
        raise RuntimeError(f"分镜 {index + 1} 子段已生成，但完整视频段合成失败：{temporary}")
    if cancel():
        raise InterruptedError("视频段生成已停止，保留原视频段")
    temporary.replace(output)
    update_progress(project_id, 84, f"分镜 {index + 1} 完整视频段已合成，正在更新分镜记录")
    return str(output).replace("\\", "/")
