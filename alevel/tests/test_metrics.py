# -*- coding: utf-8 -*-
"""指标单元测试: 用已知性质的合成信号检验指标敏感性。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from alevel.metrics import spatial, temporal, texture, frames


def make_gradient(n=20, h=128, w=128):
    x = np.linspace(0, 1, w, dtype=np.float32)
    return np.tile(x, (n, h, 1))


def make_noise(n=20, h=128, w=128, seed=0):
    rng = np.random.default_rng(seed)
    return rng.random((n, h, w), dtype=np.float32)


def make_static(n=20, h=128, w=128):
    return np.full((n, h, w), 0.5, dtype=np.float32)


def make_flicker(n=20, h=128, w=128):
    out = np.empty((n, h, w), dtype=np.float32)
    for t in range(n):
        out[t] = 0.8 if t % 2 == 0 else 0.2
    return out


def make_motion(n=20, h=128, w=128):
    """匀速平移的条带 (平滑运动, 无闪烁)。"""
    out = np.empty((n, h, w), dtype=np.float32)
    for t in range(n):
        out[t] = (np.arange(w, dtype=np.float32) + t * 2) % w / w
    return out


def test_hf_ratio_gradient_low_noise_high():
    assert spatial.hf_ratio(make_gradient()) < 0.10
    assert spatial.hf_ratio(make_noise()) > 0.15
    assert spatial.hf_ratio(make_noise()) > spatial.hf_ratio(make_gradient())


def test_res_retention_gradient_high():
    assert spatial.res_retention(make_gradient()) > 0.90
    assert spatial.res_retention(make_noise()) < spatial.res_retention(make_gradient())


def test_flicker_static_zero_flicker_high():
    assert temporal.flicker_index(make_static()) < 1e-6
    assert temporal.flicker_index(make_flicker()) > 0.01
    assert temporal.flicker_index(make_flicker()) > temporal.flicker_index(make_motion())


def test_flow_smooth_motion_low():
    flow = temporal.block_flow(make_motion())
    assert temporal.flow_smoothness(flow) < 0.05
    assert temporal.flow_smoothness(flow) < temporal.flow_smoothness(temporal.block_flow(make_noise()))


def test_blocking_artifact():
    # 无块结构 → 块效应≈0
    assert texture.blocking_artifact(make_static()) < 0.05


def test_evaluate_pipeline_shapes():
    for fn in (spatial.evaluate, temporal.evaluate, texture.evaluate):
        r = fn(make_gradient())
        assert r["dim"] in "ABE" and 1.0 <= r["score"] <= 5.0
        assert "metrics" in r and "confidence" in r


def test_sample_frames_real_video(tmp="/tmp/alevel_test.mp4"):
    """端到端: 生成真实 mp4 再取帧。"""
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=s=128x128:d=1:r=10",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", tmp],
                   check=True, capture_output=True)
    info = frames.probe_video(tmp)
    assert info["width"] == 128 and info["height"] == 128
    arr = frames.sample_frames(tmp, target_fps=10, max_frames=10, scale=128)
    assert arr.shape[0] == 10 and arr.dtype == np.float32
    assert 0.0 <= arr.min() and arr.max() <= 1.0
