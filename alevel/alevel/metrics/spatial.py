# -*- coding: utf-8 -*-
"""A 维度 (有效空间分辨率) 自动指标 — 纯 numpy 实现。

1. hf_ratio:      频域高频能量占比 (FFT 径向谱), 高 = 细节丰富。
2. res_retention: 降采样-恢复保真度: 把帧缩小再放大回原尺寸, 与原帧比较。
                  真实细节在缩放后能较好保留; AI "假细节" (纹理涂抹/过度锐化)
                  在缩放往返中漂移更大。用 NCC 衡量保留度。
二者综合映射到 1-5 分。标定参数见 spec.CALIBRATION, 均需在真实语料上重新标定。
"""
from __future__ import annotations

from typing import Dict

import numpy as np

from .. import spec
from . import util


def _lin(metric: str, value: float) -> float:
    c = spec.CALIBRATION[metric]
    (s0, m0), (s1, m1) = c["low"], c["high"]
    t = (value - m0) / (m1 - m0)
    return float(np.clip(s0 + (s1 - s0) * t, 1.0, 5.0))


def hf_ratio(frames: np.ndarray, r_cutoff: float = 0.25) -> float:
    """FFT 高频能量占比: 半径 > r_cutoff*max_freq 的环形带能量 / 总能量。"""
    ratios = []
    for f in frames:
        fft = np.fft.fftshift(np.fft.fft2(f))
        power = np.abs(fft) ** 2
        h, w = power.shape
        yy, xx = np.mgrid[-h // 2:h // 2, -w // 2:w // 2]
        r = np.sqrt(xx.astype(float) ** 2 + yy.astype(float) ** 2)
        rmax = np.sqrt((h / 2) ** 2 + (w / 2) ** 2)
        total = power.sum()
        if total <= 0:
            ratios.append(0.0)
            continue
        hi = power[r > r_cutoff * rmax].sum()
        ratios.append(float(hi / total))
    return float(np.mean(ratios)) if ratios else 0.0


def _downscale(f: np.ndarray, factor: int = 2) -> np.ndarray:
    """面积平均降采样 (2x2 block mean)。"""
    h, w = f.shape[:2]
    h2, w2 = h // factor, w // factor
    return f[:h2 * factor, :w2 * factor].reshape(h2, factor, w2, factor).mean(axis=(1, 3))


def _bilinear_upscale(f: np.ndarray, shape) -> np.ndarray:
    """双线性放大回目标尺寸。"""
    h, w = shape
    sh, sw = f.shape[:2]
    ys = np.linspace(0, sh - 1, h)
    xs = np.linspace(0, sw - 1, w)
    y0 = np.floor(ys).astype(int).clip(0, sh - 2)
    x0 = np.floor(xs).astype(int).clip(0, sw - 2)
    dy = (ys - y0)[:, None]
    dx = (xs - x0)[None, :]
    out = (f[y0][:, x0] * (1 - dy) * (1 - dx)
           + f[y0][:, x0 + 1] * (1 - dy) * dx
           + f[y0 + 1][:, x0] * dy * (1 - dx)
           + f[y0 + 1][:, x0 + 1] * dy * dx)
    return out


def res_retention(frames: np.ndarray, factor: int = 2) -> float:
    """降采样-恢复保真度 (NCC)。1 = 完美保留。"""
    nccs = []
    for f in frames:
        small = _downscale(f, factor)
        back = _bilinear_upscale(small, f.shape)
        nccs.append(util.ncc(f, back))
    return float(np.mean(nccs)) if nccs else 0.0


def evaluate(frames: np.ndarray) -> Dict:
    """综合 A 维度自动得分 (1-5)。"""
    hr = hf_ratio(frames)
    ret = res_retention(frames)
    s_hr = _lin("hf_ratio", hr)
    s_ret = _lin("res_retention", ret)
    score = float(np.clip(0.35 * s_hr + 0.65 * s_ret, 1.0, 5.0))
    return {
        "dim": "A", "score": round(score, 2), "confidence": "medium",
        "metrics": {"hf_ratio": round(hr, 4), "res_retention": round(ret, 4)},
        "note": "A 为「有效分辨率」: 高分辨率不等于高画质, 此得分衡量可保留的真实细节量",
    }
