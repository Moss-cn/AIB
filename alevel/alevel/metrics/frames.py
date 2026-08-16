# -*- coding: utf-8 -*-
"""视频取帧: 通过 ffmpeg 管道直接输出原始灰度帧, 零第三方视觉库依赖。

依赖: ffmpeg/ffprobe 可执行文件 (系统已装)。numpy 用于承载帧数组。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Dict, List, Optional

import numpy as np


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("未找到 ffmpeg, 请先安装 (brew install ffmpeg)")


def probe_video(path: str) -> Dict:
    """用 ffprobe 读取视频基本信息。"""
    if shutil.which("ffprobe") is None:
        raise RuntimeError("未找到 ffprobe, 请先安装 ffmpeg")
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_streams", "-show_format", path]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("未找到视频流")
    info = {
        "path": path,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": float(eval_fps(video.get("avg_frame_rate", "0/1")) or 0),
        "nb_frames": int(video.get("nb_frames") or 0),
        "duration_s": float(data.get("format", {}).get("duration") or 0),
        "codec": video.get("codec_name"),
    }
    if info["nb_frames"] == 0 and info["duration_s"] and info["fps"]:
        info["nb_frames"] = int(info["duration_s"] * info["fps"])
    return info


def eval_fps(rate: str) -> Optional[float]:
    if not rate or "/" not in rate:
        return None
    try:
        n, d = rate.split("/")
        return int(n) / int(d) if int(d) else None
    except ValueError:
        return None


def sample_frames(path: str, target_fps: float = 10.0, max_frames: int = 120,
                  scale: int = 256, gray: bool = True,
                  src_dims: Optional[Dict] = None) -> np.ndarray:
    """抽取帧序列, 返回 float32 数组。

    gray=True  -> shape (N, H, W), 值域 [0,1]
    gray=False -> shape (N, H, W, 3)
    通过 ffmpeg 管道 (rawvideo) 读取, 内存友好 (120 x 256 x 256 ≈ 7.8MB)。
    输出尺寸: 宽=scale, 高=按源宽高比取偶数。src_dims 可复用 probe_video 结果。
    """
    require_ffmpeg()
    if src_dims is None:
        src_dims = probe_video(path)
    w = int(scale)
    aspect = src_dims["height"] / max(1, src_dims["width"])
    h = max(2, int(round(w * aspect)) & ~1)  # 偶数
    pix_fmt = "gray" if gray else "rgb24"
    n_chan = 1 if gray else 3
    vf = f"fps={target_fps},scale={w}:{h}"
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf", vf,
           "-frames:v", str(max_frames), "-f", "rawvideo", "-pix_fmt", pix_fmt, "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 取帧失败: {proc.stderr.decode(errors='replace')[:500]}")
    raw = np.frombuffer(proc.stdout, dtype=np.uint8)
    per = w * h * n_chan
    n = raw.size // per
    if n == 0:
        raise RuntimeError("ffmpeg 未返回任何帧")
    raw = raw[: n * per]
    if gray:
        arr = raw.reshape(n, h, w).astype(np.float32) / 255.0
    else:
        arr = raw.reshape(n, h, w, 3).astype(np.float32) / 255.0
    return arr
