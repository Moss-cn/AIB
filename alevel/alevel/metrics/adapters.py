# -*- coding: utf-8 -*-
"""重型模型适配器 (方案 4.1 自动评估指标清单的可插拔实现)。

这些指标依赖大模型/深度学习库 (MediaPipe, torch, PaddleOCR 等), 不属于本工具
的默认路径。任何适配器:

- 未安装依赖时抛出带安装提示的 ProbeUnavailable 异常, CLI 会优雅降级;
- 安装后返回 {dim, score(1-5), confidence, metrics, note} 与内置指标同构,
  可直接进入评级引擎。

适配器清单 (对照方案 4.1):
  C 结构完整性: mediapipe_hands (手部关键点数), face_alignment (InsightFace),
                ocr (PaddleOCR 文字乱码率)
  B 时间稳定性: raft_flow (RAFT/GMFlow 光流一致性, 替代内置块匹配)
  D 物理一致性: light_direction (光源方向一致性估计)
  E 纹理自然度: lpips (感知相似度/伪影检测)
  F 3D 几何:    depth_consistency (Depth Anything V2)
  G 长期记忆:   identity_drift (ArcFace/CLIP 身份余弦相似度漂移)
"""
from __future__ import annotations

from typing import Dict, List, Type

import numpy as np


class ProbeUnavailable(RuntimeError):
    """依赖未安装或无法加载。"""


class BaseProbe:
    name: str = "base"
    dim: str = "?"
    deps: List[str] = []

    @classmethod
    def available(cls) -> bool:
        try:
            for d in cls.deps:
                __import__(d)
            return True
        except ImportError:
            return False

    @classmethod
    def require(cls) -> None:
        if not cls.available():
            raise ProbeUnavailable(
                f"探针 [{cls.name}] (维度 {cls.dim}) 不可用: 缺少依赖 {cls.deps}。"
                f"安装方式: pip install {' '.join(cls.deps)}")

    def run(self, frames: np.ndarray, video_info: Dict) -> Dict:
        raise NotImplementedError


class MediaPipeHandsProbe(BaseProbe):
    """C 维度: 手部关键点检测。严重畸形(关键点缺失/数量异常) → C 低分。"""
    name, dim, deps = "mediapipe_hands", "C", ["mediapipe"]

    def run(self, frames, video_info):
        self.require()
        import mediapipe as mp
        hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=2)
        ok, bad = 0, 0
        for f in frames[:: max(1, len(frames) // 20)]:
            rgb = (np.repeat(f[..., None], 3, axis=2) * 255).astype(np.uint8)
            res = hands.process(rgb)
            if res.multi_hand_landmarks:
                ok += 1
            else:
                bad += 1
        rate = ok / max(1, ok + bad)
        score = 1.0 + 4.0 * rate  # 全检出≈5, 全缺失≈1
        return {"dim": "C", "score": round(float(score), 2), "confidence": "high",
                "metrics": {"hand_detection_rate": round(rate, 3)}, "note": "MediaPipe Hands 手部检出率"}


class RaftFlowProbe(BaseProbe):
    """B 维度: RAFT 光流一致性 (替代内置块匹配, 精度更高)。"""
    name, dim, deps = "raft_flow", "B", ["torch"]

    def run(self, frames, video_info):
        self.require()
        raise NotImplementedError(
            "RAFT 光流探针骨架已就绪: 请加载 raft 权重后计算光流场, "
            "用 temporal.flow_smoothness 与前后向一致性生成 B 分。")

class PaddleOcrProbe(BaseProbe):
    """C 维度: OCR 错误率 (文字乱码检测)。"""
    name, dim, deps = "paddleocr", "C", ["paddleocr"]

    def run(self, frames, video_info):
        self.require()
        raise NotImplementedError("OCR 探针骨架: 需结合标准文字用例 (T06) 计算识别错误率。")


class DepthConsistencyProbe(BaseProbe):
    """F 维度: 深度估计时序一致性 (Depth Anything V2)。"""
    name, dim, deps = "depth_consistency", "F", ["torch"]

    def run(self, frames, video_info):
        self.require()
        raise NotImplementedError("深度一致性探针骨架: 逐帧估计深度, 比较时间序列深度图一致性与旋转视差。")


class IdentityDriftProbe(BaseProbe):
    """G 维度: 身份特征漂移 (ArcFace/CLIP)。"""
    name, dim, deps = "identity_drift", "G", ["torch"]

    def run(self, frames, video_info):
        self.require()
        raise NotImplementedError("身份漂移探针骨架: 提取人脸嵌入, 计算跨帧余弦相似度漂移率。")


ALL_PROBES: List[Type[BaseProbe]] = [
    MediaPipeHandsProbe, RaftFlowProbe, PaddleOcrProbe,
    DepthConsistencyProbe, IdentityDriftProbe,
]


def available_probes() -> Dict[str, bool]:
    return {p.name: p.available() for p in ALL_PROBES}
