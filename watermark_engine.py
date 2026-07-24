from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"
}


def find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(
        f"未找到 {name}。请先安装 FFmpeg，或确认它已加入 PATH。"
    )


def probe_duration(video_path: str, ffprobe_path: str | None = None) -> float:
    ffprobe_path = ffprobe_path or find_binary("ffprobe")
    result = subprocess.run(
        [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def _escape_filter_value(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def _position_expression(position: str, margin: int) -> tuple[str, str]:
    positions = {
        "左上": (str(margin), str(margin)),
        "顶部居中": ("(W-w)/2", str(margin)),
        "右上": (f"W-w-{margin}", str(margin)),
        "左侧居中": (str(margin), "(H-h)/2"),
        "正中": ("(W-w)/2", "(H-h)/2"),
        "右侧居中": (f"W-w-{margin}", "(H-h)/2"),
        "左下": (str(margin), f"H-h-{margin}"),
        "底部居中": ("(W-w)/2", f"H-h-{margin}"),
        "右下": (f"W-w-{margin}", f"H-h-{margin}"),
    }
    return positions.get(position, positions["右下"])


def _text_position_expression(position: str, margin: int) -> tuple[str, str]:
    x, y = _position_expression(position, margin)
    return x.replace("W", "w").replace("-w", "-text_w"), (
        y.replace("H", "h").replace("-h", "-text_h")
    )


def default_font_path() -> str:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return ""


@dataclass
class WatermarkOptions:
    mode: str = "图片水印"
    image_path: str = ""
    text: str = ""
    position: str = "右下"
    opacity: float = 0.75
    size_percent: float = 16.0
    margin: int = 24
    font_path: str = ""
    font_color: str = "white"
    motion_style: str = "斜向流动"
    speed: float = 60.0
    density: int = 5
    crf: int = 18
    preset: str = "medium"


def _drawtext_base(options: WatermarkOptions) -> str:
    font_path = options.font_path or default_font_path()
    font_part = (
        f"fontfile='{_escape_filter_value(font_path)}':"
        if font_path else ""
    )
    opacity = max(0.0, min(options.opacity, 1.0))
    fontsize_ratio = max(0.01, min(options.size_percent / 100.0, 0.5))
    text = _escape_filter_value(options.text)
    color = _escape_filter_value(options.font_color or "white")
    return (
        f"drawtext={font_part}text='{text}':"
        f"expansion=none:"
        f"fontcolor={color}@{opacity:.3f}:"
        f"fontsize=h*{fontsize_ratio:.5f}:"
        f"borderw=1:bordercolor=black@{min(opacity * 0.55, 0.35):.3f}:"
    )


def _dynamic_text_filter(options: WatermarkOptions) -> str:
    density = max(1, min(int(options.density), 10))
    columns = 2 + round(density * 0.6)
    rows = 1 + round(density * 0.4)
    speed = max(1.0, min(float(options.speed), 500.0))
    base = _drawtext_base(options)
    filters: list[str] = []

    for row in range(rows):
        for column in range(columns):
            x_offset = f"{(column + 0.25) / columns:.6f}*w"
            y_offset = f"{(row + 0.35) / rows:.6f}*h"

            if options.motion_style == "向左流动":
                x = (
                    f"mod({x_offset}-t*{speed:.3f}+w+text_w"
                    r"\,w+text_w)-text_w"
                )
                y = f"{y_offset}-text_h/2"
            elif options.motion_style == "向右流动":
                x = (
                    f"mod({x_offset}+t*{speed:.3f}"
                    r"\,w+text_w)-text_w"
                )
                y = f"{y_offset}-text_h/2"
            elif options.motion_style == "向上流动":
                x = f"{x_offset}-text_w/2"
                y = (
                    f"mod({y_offset}-t*{speed:.3f}+h+text_h"
                    r"\,h+text_h)-text_h"
                )
            elif options.motion_style == "向下流动":
                x = f"{x_offset}-text_w/2"
                y = (
                    f"mod({y_offset}+t*{speed:.3f}"
                    r"\,h+text_h)-text_h"
                )
            else:
                diagonal_speed = speed * 0.58
                x = (
                    f"mod({x_offset}-t*{speed:.3f}+w+text_w"
                    r"\,w+text_w)-text_w"
                )
                y = (
                    f"mod({y_offset}+t*{diagonal_speed:.3f}"
                    r"\,h+text_h)-text_h"
                )

            filters.append(f"{base}x='{x}':y='{y}'")

    return ",".join(filters)


def build_command(
    input_path: str,
    output_path: str,
    options: WatermarkOptions,
    ffmpeg_path: str | None = None,
) -> list[str]:
    ffmpeg_path = ffmpeg_path or find_binary("ffmpeg")
    common = [
        ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
    ]

    if options.mode == "图片水印":
        if not options.image_path or not Path(options.image_path).is_file():
            raise ValueError("请选择有效的 PNG/JPG 水印图片。")
        x, y = _position_expression(options.position, options.margin)
        ratio = max(0.01, min(options.size_percent / 100.0, 1.0))
        opacity = max(0.0, min(options.opacity, 1.0))
        filter_graph = (
            f"[1:v]format=rgba,colorchannelmixer=aa={opacity:.3f}[wm0];"
            f"[wm0][0:v]scale2ref=w=main_w*{ratio:.5f}:h=ow/mdar[wm][base];"
            f"[base][wm]overlay=x={x}:y={y}:format=auto[vout]"
        )
        command = common + [
            "-i", options.image_path,
            "-filter_complex", filter_graph,
            "-map", "[vout]",
            "-map", "0:a?",
        ]
    elif options.mode == "文字水印":
        if not options.text.strip():
            raise ValueError("请输入水印文字。")
        x, y = _text_position_expression(options.position, options.margin)
        drawtext = (
            f"{_drawtext_base(options)}"
            f"x={x}:y={y}"
        )
        command = common + [
            "-vf", drawtext,
            "-map", "0:v:0",
            "-map", "0:a?",
        ]
    else:
        if not options.text.strip():
            raise ValueError("请输入动态水印文字。")
        command = common + [
            "-vf", _dynamic_text_filter(options),
            "-map", "0:v:0",
            "-map", "0:a?",
        ]

    command += [
        "-c:v", "libx264",
        "-preset", options.preset,
        "-crf", str(options.crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        output_path,
    ]
    return command


def make_output_path(input_path: str, output_dir: str) -> str:
    source = Path(input_path)
    destination = Path(output_dir) / f"{source.stem}_watermarked.mp4"
    counter = 2
    while destination.exists():
        destination = Path(output_dir) / f"{source.stem}_watermarked_{counter}.mp4"
        counter += 1
    return str(destination)


def render_video(
    input_path: str,
    output_path: str,
    options: WatermarkOptions,
    progress_callback: Callable[[float], None] | None = None,
    process_callback: Callable[[subprocess.Popen], None] | None = None,
) -> None:
    duration = max(probe_duration(input_path), 0.001)
    command = build_command(input_path, output_path, options)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process_callback:
        process_callback(process)

    assert process.stdout is not None
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key in {"out_time_us", "out_time_ms"}:
            try:
                seconds = int(value) / 1_000_000
                if progress_callback:
                    progress_callback(min(seconds / duration, 1.0))
            except ValueError:
                pass

    stderr = process.stderr.read() if process.stderr else ""
    return_code = process.wait()
    if return_code != 0:
        if Path(output_path).exists():
            Path(output_path).unlink()
        raise RuntimeError(stderr.strip() or f"FFmpeg 处理失败（代码 {return_code}）")
    if progress_callback:
        progress_callback(1.0)
