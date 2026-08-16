# -*- coding: utf-8 -*-
"""合成测试视频生成 (ffmpeg lavfi / numpy 写入), 用于端到端验证与演示。

生成的视频具有已知性质, 可检验指标是否敏感:
  gradient  平滑渐变 → 高频能量低, 时间稳定
  noise     纯噪声   → 高频能量高, 时间不稳定 (闪烁)
  testsrc2  运动测试图 → 中高频, 平滑运动
  mandelbrot 高细节运动 → 高频, 平滑运动
  flicker   亮度交替闪烁 (numpy 合成) → B 维度应显著偏低
  static    静止画面 → 时间极稳定
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict

import numpy as np


def _lavfi(out_path: str, src: str, dur: float = 2.0) -> str:
    """lavfi 源直接生成 (源表达式需自带 size/rate 等选项)。"""
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src,
           "-t", str(dur), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _lavfi_vf(out_path: str, src_expr: str, vf_expr: str, size: str = "256x256",
              dur: float = 2.0, fps: float = 10.0) -> str:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", f"{src_expr}=s={size}:d={dur}:r={fps}",
           "-vf", vf_expr, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _flicker_video(out_path: str, size: int = 128, dur_s: float = 2.0,
                   fps: float = 10.0) -> str:
    """numpy 合成亮度交替闪烁视频 (占空比 50%, 亮度 0.2 ↔ 0.8)。"""
    n = int(dur_s * fps)
    fr = np.empty((n, size, size), dtype=np.uint8)
    for t in range(n):
        fr[t] = 204 if t % 2 == 0 else 51
    raw = fr.tobytes()
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray",
           "-s", f"{size}x{size}", "-r", str(fps), "-i", "pipe:0",
           "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out_path]
    subprocess.run(cmd, input=raw, check=True, capture_output=True)
    return out_path


def make_synthetic_videos(outdir: str) -> Dict[str, str]:
    os.makedirs(outdir, exist_ok=True)
    vids = {
        "gradient":   _lavfi(os.path.join(outdir, "gradient.mp4"), "gradients=size=256x256:rate=10"),
        # noise 是滤镜而非源: 用 nullsrc 做底, geq 生成时间/空间随机噪声
        "noise":      _lavfi_vf(os.path.join(outdir, "noise.mp4"), "nullsrc",
                                "geq=random(1)*255:128:128"),
        "testsrc2":   _lavfi(os.path.join(outdir, "testsrc2.mp4"), "testsrc2=size=256x256:rate=10"),
        "mandelbrot": _lavfi(os.path.join(outdir, "mandelbrot.mp4"), "mandelbrot=size=256x256:rate=10"),
        "static":     _lavfi(os.path.join(outdir, "static.mp4"), "color=c=gray:s=256x256:r=10"),
        "flicker":    _flicker_video(os.path.join(outdir, "flicker.mp4")),
    }
    return vids
