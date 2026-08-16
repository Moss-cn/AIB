# -*- coding: utf-8 -*-
"""D 维度 (物理一致性) 自动指标 — 纯 numpy。

1. light_consistency: 主光照方向一致性。对每帧计算加权梯度方向的圆均值,
   跨帧圆方差小 = 光照/阴影关系稳定。AI 视频常见的光影矛盾/光源漂移会拉低此值。
2. luminance_stability: 全局亮度时间稳定性 (均值亮度序列的时域高频能量)。
   亮度突变 (光照跳变/白平衡漂移) → 不稳定。

两者同为弱代理 (真实物理一致性还包含反射/碰撞等), 置信度标注为 low。
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


def light_direction_consistency(frames: np.ndarray) -> float:
    """主梯度方向圆一致性 (0..1, 1=完全一致)。"""
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
    vectors = []
    for f in frames:
        gx = util.conv2d(f, kx)
        gy = util.conv2d(f, ky)
        mag = np.hypot(gx, gy)
        # 平坦/低对比画面: 梯度主要是噪声, 方向无意义 → 跳过该帧 (不参与判定)
        if np.percentile(mag, 85) < 0.02:
            continue
        thr = np.percentile(mag, 85)                    # 只取强梯度
        sel = mag >= thr
        if sel.sum() < 10:
            continue
        vx = float((gx[sel] / (mag[sel] + 1e-6)).mean())   # 归一化方向均值
        vy = float((gy[sel] / (mag[sel] + 1e-6)).mean())
        vectors.append((vx, vy))
    if len(vectors) < 3:
        return 1.0
    vx = np.array([v[0] for v in vectors])
    vy = np.array([v[1] for v in vectors])
    R = float(np.hypot(vx.mean(), vy.mean()))           # 平均合成向量长度 (0..1)
    return float(np.clip(R, 0.0, 1.0))


def luminance_flux(frames: np.ndarray) -> float:
    """全局亮度时域通量: 亮度序列的波动幅度 (0..1 帧域)。"""
    series = frames.mean(axis=(1, 2))                   # (N,)
    if len(series) < 3:
        return 0.0
    return float(np.abs(np.diff(series, axis=0)).mean())


def evaluate(frames: np.ndarray) -> Dict:
    """综合 D 维度自动得分 (1-5)。"""
    light = light_direction_consistency(frames)
    flux = luminance_flux(frames)
    s_light = _lin("light_consistency", light)
    s_flux = _lin("luminance_flux", flux)
    score = float(np.clip(0.55 * s_light + 0.45 * s_flux, 1.0, 5.0))
    return {
        "dim": "D", "score": round(score, 2), "confidence": "low",
        "metrics": {"light_consistency": round(light, 4), "luminance_flux": round(flux, 5)},
        "note": "弱代理: 主梯度方向圆一致性 + 亮度时间稳定性; 反射/碰撞等真实物理一致性需人工或研究性探针",
    }
