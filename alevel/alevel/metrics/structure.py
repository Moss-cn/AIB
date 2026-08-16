# -*- coding: utf-8 -*-
"""C 维度 (结构完整性) 自动指标。

核心 (纯 numpy, 所有环境可用):
  morphing: 运动补偿后的结构残余变化。用块匹配光流把 t+1 帧对齐回 t 帧,
            比较"光流解释不了的"边缘结构差异 —— 人脸形变/结构崩坏会留下高残余,
            平滑运动 (真实相机/主体) 残余低。

增强 (cv2 可用时自动启用, CLI 端):
  face:     Haar 级联人脸检测 (CascadeClassifier), 输出检出率 / 边框抖动 / 数量一致性。
            浏览器端 (Pyodide) 未加载 opencv 时自动回退为 morphing-only。

注意: 人脸相关指标对"无人场景"返回中性分, 不误伤风景/物体类视频。
"""
from __future__ import annotations

import os
from typing import Dict, Optional

import numpy as np

from .. import spec
from . import temporal, util

try:
    _DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
except NameError:
    _DATA = ""   # 浏览器 (Pyodide) exec 环境无 __file__; 级联文件缺失时人脸增强自动跳过


def _lin(metric: str, value: float) -> float:
    c = spec.CALIBRATION[metric]
    (s0, m0), (s1, m1) = c["low"], c["high"]
    t = (value - m0) / (m1 - m0)
    return float(np.clip(s0 + (s1 - s0) * t, 1.0, 5.0))


def morphing_index(frames: np.ndarray) -> float:
    """运动补偿结构残余: 光流对齐后, 边缘区域无法解释的差异 (0..1)。

    流程: 块匹配光流 → 块级 warp t+1 → 与 t 的块均值比较 (仅在强边缘块上加权)。
    """
    n = len(frames)
    if n < 3:
        return 0.0
    f2 = util.resize(frames, 96) if frames.shape[1] > 96 else frames
    flow = temporal.block_flow(f2, block=16, search=4, step=16)   # (N-1, ny, nx, 2)
    if flow.shape[0] == 0:
        return 0.0
    # 像素级运动补偿: 用块级光流 (像素单位) 逐像素 warp t+1 帧, 再比较边缘结构
    h, w = f2.shape[1], f2.shape[2]
    ny, nx = flow.shape[1], flow.shape[2]
    yy, xx = np.mgrid[0:h, 0:w]
    by = np.clip(yy // 16, 0, ny - 1)
    bx = np.clip(xx // 16, 0, nx - 1)
    residuals = []
    for t in range(n - 1):
        f0, f1 = f2[t], f2[t + 1]
        dy_map = flow[t][by, bx, 0]
        dx_map = flow[t][by, bx, 1]
        sy = np.clip(yy + dy_map, 0, h - 1).astype(int)
        sx = np.clip(xx + dx_map, 0, w - 1).astype(int)
        warped = f1[sy, sx]
        # 边缘显著性权重 (f0 的梯度强度)
        edge = (np.abs(np.diff(f0, axis=1, append=f0[:, -1:]))
                + np.abs(np.diff(f0, axis=0, append=f0[-1:, :])))
        edge_w = edge / (edge.mean() + 1e-6)
        residuals.append(float((np.abs(f0 - warped) * edge_w).mean()))
    return float(np.mean(residuals)) if residuals else 0.0


def _cv2_face_metrics(frames: np.ndarray) -> Optional[Dict]:
    """Haar 人脸检测: 检出率 / 边框中心抖动 / 数量一致性。不可用时返回 None。"""
    try:
        import cv2
    except ImportError:
        return None
    cascade_path = None
    try:
        p = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if os.path.exists(p):
            cascade_path = p
    except Exception:
        pass
    if cascade_path is None:
        p = os.path.join(_DATA, "haarcascade_frontalface_default.xml")
        if os.path.exists(p):
            cascade_path = p
    if cascade_path is None:
        return None
    try:
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            return None
    except Exception:
        return None
    dets = []          # (center_x, center_y, w, h)
    for f in frames[:: max(1, len(frames) // 24)]:
        img = (f * 255).astype(np.uint8)
        faces = cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20))
        if len(faces):
            x, y, w, h = faces[0]
            dets.append((x + w / 2, y + h / 2, w, h))
    if not dets:
        return None     # 无人脸 → 中性 (调用方处理)
    rate = len(dets) / max(1, len(frames[:: max(1, len(frames) // 24)]))
    # 边框中心抖动 (归一化到帧宽)
    centers = np.array([(c[0], c[1]) for c in dets], dtype=np.float32)
    jitter = float(np.abs(np.diff(centers, axis=0)).mean()) / max(1, frames.shape[2])
    return {"detection_rate": round(rate, 3), "center_jitter": round(jitter, 4),
            "faces_seen": len(dets)}


def evaluate(frames: np.ndarray) -> Dict:
    """综合 C 维度自动得分 (1-5)。"""
    morph = morphing_index(frames)
    s_morph = _lin("morphing", morph)
    face = _cv2_face_metrics(frames)
    if face and face["detection_rate"] >= 0.3:
        s_rate = _lin("face_rate", face["detection_rate"])
        s_jit = _lin("face_jitter", face["center_jitter"])
        score = float(np.clip(0.35 * s_morph + 0.30 * s_rate + 0.35 * s_jit, 1.0, 5.0))
        note = "morphing(运动补偿结构残余) + Haar 人脸检出/抖动"
        conf = "medium"
    else:
        score = float(np.clip(s_morph, 1.0, 5.0))
        note = "morphing(运动补偿结构残余); 未启用/未检测到人脸增强 (无人场景按中性处理)"
        conf = "low" if face is None else "medium"
    return {"dim": "C", "score": round(score, 2), "confidence": conf,
            "metrics": {"morphing": round(morph, 5), "face": face},
            "note": note}
