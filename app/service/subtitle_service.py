import os
from datetime import timedelta
import ffmpeg
import re
import unicodedata
from pathlib import Path

class SubtitleService:
    def __init__(self):
       pass

    def _format_time(self, seconds: float) -> str:
        """将秒数格式化为 SRT 时间戳格式 00:00:00,000"""
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        ms = int((td.total_seconds() - total_seconds) * 1000)
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    def generate_srt(self, segments,output_dir:str, filename="subtitles.srt", video_path=None):
        """
        根据 [ {text, duration}, ... ] 生成字幕文件
        """
        width, height = self._dimensions(video_path) if video_path else (1024, 1024)
        font_size = max(12, round(min(width, height) * 0.035))
        capacity = max(4, int(width * 0.84 / (font_size * 1.15)))
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        srt_path = os.path.join(output_dir, filename)
        with open(srt_path, "w", encoding="utf-8") as f:
            current_time = 0.0
            index = 1
            for seg in segments:
                duration = float(seg["duration"])
                # Normalize both real line breaks and literal escaped newlines
                # before automatic subtitle wrapping; never alter narration data.
                text = re.sub(r"\\r\\n|\\[rn]", " ", str(seg["text"]))
                text = re.sub(r"\s+", " ", text).strip()
                rows, row, used = [], "", 0
                for char in text:
                    cost = 1 if unicodedata.east_asian_width(char) in "WF" else 0.6
                    if row and used + cost > capacity:
                        rows.append(row)
                        row, used = "", 0
                    row += char
                    used += cost
                if row:
                    rows.append(row)
                pages = ["\n".join(rows[i:i + 2]) for i in range(0, len(rows), 2)]
                weights = [len(page.replace("\n", "")) for page in pages]
                elapsed = 0
                for page, weight in zip(pages, weights):
                    start = self._format_time(current_time + duration * elapsed / sum(weights))
                    elapsed += weight
                    end = self._format_time(current_time + duration * elapsed / sum(weights))
                    f.write(f"{index}\n{start} --> {end}\n{page}\n\n")
                    index += 1
                current_time += duration
        print(f"✅ 字幕文件已生成：{srt_path}")
        return srt_path

    def _dimensions(self, video_path):
        stream = next(s for s in ffmpeg.probe(str(video_path))["streams"] if s["codec_type"] == "video")
        return int(stream["width"]), int(stream["height"])

    def burn_subtitles(self, video_path: str, srt_path: str, output_path=None, font="SimHei", fontsize=28):
        """
        将字幕烧录进视频 (生成新视频)
        """
        if output_path is None:
            base, ext = os.path.splitext(video_path)
            output_path = f"{base}_subtitled{ext}"

        width, height = self._dimensions(video_path)
        fontsize = max(12, round(min(width, height) * 0.035))
        margin_x, margin_y = round(width * 0.08), round(height * 0.06)
        ass_path = Path(srt_path).with_suffix(".ass")
        header = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
                  "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
                  f"Style: Default,{font},{fontsize},&H00FFFFFF,&H00000000,1,2,0,2,{margin_x},{margin_x},{margin_y}\n"
                  "[Events]\nFormat: Layer, Start, End, Style, Text\n")
        events = []
        pattern = r"\d+\n(\d+:\d+:\d+,\d+) --> (\d+:\d+:\d+,\d+)\n(.*?)(?=\n\n|\Z)"
        for start, end, text in re.findall(pattern, Path(srt_path).read_text(encoding="utf-8"), re.S):
            escaped = text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", r"\N")
            events.append(f"Dialogue: 0,{start.replace(',', '.')[:-1]},{end.replace(',', '.')[:-1]},Default,{escaped}\n")
        ass_path.write_text(header + "".join(events), encoding="utf-8-sig")
        source = ffmpeg.input(str(video_path))
        ffmpeg.output(source.video.filter("ass", ass_path.as_posix()), source.audio, str(output_path),
                      vcodec="libx264", preset="ultrafast", crf=20, acodec="copy", threads=4).run(overwrite_output=True)
        print(f"🎬 已为视频添加字幕：{output_path}")
        return output_path
