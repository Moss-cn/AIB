# -*- coding: utf-8 -*-
"""共享数值工具 (纯 numpy)。"""
from __future__ import annotations

import numpy as np


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    """归一化互相关 (1=完全一致)。数值稳定实现, 避免对近平稳信号除零。

    压缩微噪声可能让原帧 std≈1e-7 而降采样恢复后 std≈0 (相差几个量级),
    np.corrcoef 此时会产生 NaN; 此处对零方差信号显式处理。
    """
    a = a.astype(np.float32).ravel()
    b = b.astype(np.float32).ravel()
    da = a - a.mean()
    db = b - b.mean()
    va = float((da * da).sum())
    vb = float((db * db).sum())
    if va < 1e-12 and vb < 1e-12:
        return 1.0 if np.allclose(a, b) else 0.0
    if va < 1e-12 or vb < 1e-12:
        return 0.0
    c = float((da * db).sum()) / float(np.sqrt(va * vb))
    return float(np.clip(c, -1.0, 1.0))


def resize(frames: np.ndarray, width: int) -> np.ndarray:
    """面积平均降采样到指定宽度 (保持宽高比)。"""
    n, h, w = frames.shape
    if w <= width:
        return frames
    f = float(w) / width
    h2 = max(1, int(h / f))
    w2 = width
    out = np.empty((n, h2, w2), dtype=np.float32)
    for i in range(n):
        out[i] = _downscale_arbitrary(frames[i], h2, w2)
    return out


def _downscale_arbitrary(f: np.ndarray, h2: int, w2: int) -> np.ndarray:
    h, w = f.shape
    ys = (np.linspace(0, h, h2 + 1)).astype(int)
    xs = (np.linspace(0, w, w2 + 1)).astype(int)
    out = np.empty((h2, w2), dtype=np.float32)
    for i in range(h2):
        for j in range(w2):
            out[i, j] = f[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].mean()
    return out


def conv2d(f: np.ndarray, k: np.ndarray) -> np.ndarray:
    """2D 相关卷积 (valid 模式, 步长1), 用于小卷积核。"""
    kh, kw = k.shape
    h, w = f.shape
    out = np.zeros((h - kh + 1, w - kw + 1), dtype=np.float32)
    for i in range(kh):
        for j in range(kw):
            out += k[i, j] * f[i:i + h - kh + 1, j:j + w - kw + 1]
    return out
