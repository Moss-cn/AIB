# -*- coding: utf-8 -*-
"""E 维度 (纹理自然度) 自动指标 — 纯 numpy 实现。

1. blocking: 块效应强度 (8x8 分块边界处的边缘不连续度)。压缩/AI 伪影通常
             在块边界产生异常梯度。
2. 噪声/细节诊断: Laplacian 响应 MAD, 区分"过度平滑的塑料感"与"颗粒噪点"。
E 维度与主观审美高度相关, 自动指标只能作弱代理; 建议配合人工评分。
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


def blocking_artifact(frames: np.ndarray, block: int = 8) -> float:
    """块效应: 块边界两侧梯度 与 块内梯度 的比值偏离 1 的程度。"""
    vals = []
    for f in frames:
        g = np.abs(np.diff(f, axis=1))  # 水平梯度 (H, W-1)
        h, w = g.shape
        boundary_idx = np.arange(block - 1, w, block)
        inside_idx = np.setdiff1d(np.arange(w), boundary_idx)
        gb = g[:, boundary_idx].mean() if boundary_idx.size else 0.0
        gi = g[:, inside_idx].mean() if inside_idx.size else 0.0
        if gi > 1e-6:
            vals.append(abs(gb / gi - 1.0))
    return float(np.mean(vals)) if vals else 0.0


def detail_stats(frames: np.ndarray) -> Dict:
    """细节/噪声诊断信息 (不直接打分, 供人工参考)。"""
    laps = []
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    for f in frames[:: max(1, len(frames) // 10)]:
        lap = util.conv2d(f, k)
        laps.append(lap)
    all_lap = np.stack(laps)
    return {
        "laplacian_mad": float(np.median(np.abs(all_lap - np.median(all_lap)))),
        "laplacian_std": float(all_lap.std()),
        "mean_luminance": float(frames.mean()),
    }


def evaluate(frames: np.ndarray) -> Dict:
    """综合 E 维度自动得分 (1-5)。"""
    blk = blocking_artifact(frames)
    s = _lin("blocking", blk)
    score = float(np.clip(s, 1.0, 5.0))
    return {
        "dim": "E", "score": round(score, 2), "confidence": "low",
        "metrics": {"blocking": round(blk, 5), **detail_stats(frames)},
        "note": "E 为弱代理指标: 纹理质感高度主观, 强烈建议人工复核",
    }
