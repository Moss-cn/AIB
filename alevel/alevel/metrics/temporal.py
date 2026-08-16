# -*- coding: utf-8 -*-
"""B 维度 (时间稳定性) 自动指标 — 纯 numpy 实现。

1. flicker:      时间二阶差分 (帧差的时间导数) 的均值, 衡量闪烁/抖动。
                 恒定画面=0; 匀速运动=低; 闪烁/抽帧=高。
2. flow_smooth:  块匹配光流运动场的光滑度 (均值绝对散度)。真实运动场平滑,
                 AI 抖动/形变会在流场上产生尖刺。
综合映射到 1-5 分。
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


def flicker_index(frames: np.ndarray) -> float:
    """闪烁指数: 时间域高频能量占比 (0..1)。

    对每像素做时间轴 FFT: 纯交替闪烁 (0.8/0.2/0.8...) 的能量集中在奈奎斯特
    频率附近 → 比值≈1; 匀速运动能量集中在低频 → 比值小; 静止画面无能量 → 0。
    附赠 accel (时间二阶差分均值) 作为不规则抖动的辅助诊断。
    """
    n = len(frames)
    if n < 4:
        return 0.0
    # 先减去时间均值 (DC), 否则平均亮度会淹没交替/高频能量
    centered = frames - frames.mean(axis=0, keepdims=True)
    power = np.abs(np.fft.fft(centered, axis=0)) ** 2        # (N, H, W)
    k = np.arange(n)                                        # 时间频域 bin 索引
    high = (k > 0.35 * n / 2) & (k < n - 0.35 * n / 2)
    total = power.sum(axis=0)
    hi = power[high].sum(axis=0)
    valid = total > 1e-6
    ratios = np.where(valid, hi / np.maximum(total, 1e-12), 0.0)
    accel = 0.0
    if n >= 3:
        diffs = np.abs(np.diff(frames, axis=0))
        accel = float(np.abs(np.diff(diffs, axis=0)).mean())
    return float(ratios.mean())


def block_flow(frames: np.ndarray, block: int = 16, search: int = 8,
               step: int = 8) -> np.ndarray:
    """朴素块匹配光流 (纯 numpy), 返回 flow (N-1, ny, nx, 2)。

    在 128px 左右的小图上运行以保证速度; 仅用于运动场光滑度统计。
    """
    fr = frames
    if fr.shape[1] > 160:
        fr = util.resize(fr, 160)
    n, h, w = fr.shape
    flows = []
    yy, xx = np.mgrid[0:h - block + 1:step, 0:w - block + 1:step]
    anchors = np.stack([yy.ravel(), xx.ravel()], axis=1)
    ny, nx = yy.shape
    for t in range(n - 1):
        f0, f1 = fr[t], fr[t + 1]
        flow = np.zeros((ny * nx, 2), dtype=np.float32)
        for k, (ay, ax) in enumerate(anchors):
            blk = f0[ay:ay + block, ax:ax + block]
            best, best_sad = (0, 0), np.inf
            for dy in range(-search, search + 1):
                for dx in range(-search, search + 1):
                    y1, x1 = ay + dy, ax + dx
                    if y1 < 0 or x1 < 0 or y1 + block > h or x1 + block > w:
                        continue
                    sad = np.abs(blk - f1[y1:y1 + block, x1:x1 + block]).mean()
                    if sad < best_sad:
                        best_sad, best = sad, (dy, dx)
            flow[k] = best
        flows.append(flow.reshape(ny, nx, 2))
    return np.stack(flows) if flows else np.zeros((0, ny, nx, 2))


def flow_smoothness(flow: np.ndarray) -> float:
    """运动场光滑度: 均值绝对散度 (0 = 完全平滑)。"""
    if flow.shape[0] == 0:
        return 0.0
    du_dx = np.abs(np.diff(flow[..., 0], axis=2))
    dv_dy = np.abs(np.diff(flow[..., 1], axis=1))
    return float(np.mean(np.concatenate([du_dx.ravel(), dv_dy.ravel()])))


def evaluate(frames: np.ndarray, lite: bool = False) -> Dict:
    """综合 B 维度自动得分 (1-5)。

    lite=True 用于浏览器 (Pyodide) 端: 缩小搜索窗与网格, 控制计算量。
    """
    fl = flicker_index(frames)
    if lite:
        f2 = util.resize(frames, 96) if frames.shape[1] > 96 else frames
        flow = block_flow(f2, block=16, search=3, step=16)
    else:
        flow = block_flow(frames)
    fs = flow_smoothness(flow)
    s_fl = _lin("flicker", fl)
    s_fs = _lin("flow_smooth", fs)
    score = float(np.clip(0.6 * s_fl + 0.4 * s_fs, 1.0, 5.0))
    return {
        "dim": "B", "score": round(score, 2), "confidence": "medium",
        "metrics": {"flicker": round(fl, 5), "flow_smoothness": round(fs, 5)},
        "note": "B 权重最高(0.30), 是 AI 视频最大痛点; 闪烁/抽帧会显著拉低等级",
    }
