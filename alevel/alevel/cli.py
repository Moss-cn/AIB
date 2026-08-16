# -*- coding: utf-8 -*-
"""A-Level 评估工具 CLI。

用法示例:
  # 纯人工评分 → 等级 (对应方案附录 A 的人工评分表)
  python -m alevel.cli grade --scores '{"A":4,"B":4,"C":5,"D":4,"E":4}'

  # 视频自动评估 (A/B/E 自动指标 + 人工补充 C/D)
  python -m alevel.cli evaluate demo/videos/t02_noise.mp4 --manual '{"C":2,"D":3}' --out report.json

  # 全流程演示: 生成合成测试视频并评估
  python -m alevel.cli demo --outdir demo

  # 查看可用的重型探针
  python -m alevel.cli probes
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

from . import engine, report, spec
from .metrics import adapters, frames, physics, spatial, structure, temporal, texture


def _load_manual(raw: Optional[str]) -> Dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"manual 参数不是合法 JSON: {raw}")
    bad = [k for k in data if k not in spec.ALL_DIMS]
    if bad:
        raise SystemExit(f"未知维度: {bad}, 合法维度: {spec.ALL_DIMS}")
    for k, v in data.items():
        if not (1.0 <= float(v) <= 5.0):
            raise SystemExit(f"维度 {k} 得分 {v} 超出 1-5")
    return {k: float(v) for k, v in data.items()}


def cmd_grade(args) -> None:
    manual = _load_manual(args.scores)
    missing = [d for d in spec.CORE_DIMS if d not in manual]
    if missing:
        raise SystemExit(f"grade 模式需提供全部核心维度, 缺少: {missing}")
    adv = {k: v for k, v in manual.items() if k in spec.ADV_DIMS}
    flags = json.loads(args.flags) if args.flags else {}
    g = engine.assign_grade(manual, adv=adv or None, flags=flags, scale=args.scale)
    if args.json:
        print(report.to_json({"grade": g, "manual_scores": manual, "scores": {}, "metric_details": [], "video": None}))
        return
    print(f"综合得分: {g['composite']:.2f} ({g['scale']}分制)  →  等级: {g['level']} {g['public']}")
    if g["capped"]:
        print(f"⚠️  一票否决: {g['cap_reason']} (上限 {g['level']}, 原判定 {g['capped_from']})")
    for r in g["requirements"]:
        mark = "✅" if r["met"] else "  "
        detail = "、".join(r["missing"]) if r["missing"] else "全部满足"
        print(f"  {mark} {r['level']}: {detail}")


def cmd_evaluate(args) -> None:
    manual = _load_manual(args.manual)
    video = frames.probe_video(args.video)
    print(f"[1/4] 视频信息: {video['width']}x{video['height']} @ {video['fps']:.2f}fps, "
          f"{video.get('duration_s', 0):.1f}s ({video.get('codec')})")
    print(f"[2/4] 抽取帧样本: fps={args.fps}, max={args.max_frames}, scale={args.scale_px}")
    fr = frames.sample_frames(args.video, target_fps=args.fps, max_frames=args.max_frames,
                              scale=args.scale_px, gray=True)
    print(f"      实际帧数: {fr.shape[0]} (每帧 {fr.shape[1]}x{fr.shape[2]})")

    # 内置自动指标: A / B / C / D / E (全自动)
    print("[3/4] 运行自动指标 (A: FFT+分辨率保留, B: 闪烁+光流, C: 结构残余+人脸, D: 光照+亮度, E: 块效应)...")
    results: List[Dict] = [spatial.evaluate(fr), temporal.evaluate(fr), structure.evaluate(fr),
                           physics.evaluate(fr), texture.evaluate(fr)]
    for r in results:
        print(f"      维度 {r['dim']}: {r['score']:.2f} (conf={r.get('confidence')})  {r['metrics']}")

    # 重型探针 (可选)
    probes = [p.strip() for p in (args.probes or "").split(",") if p.strip()]
    for name in probes:
        probe_cls = next((p for p in adapters.ALL_PROBES if p.name == name), None)
        if probe_cls is None:
            print(f"      ⚠️ 未知探针 {name}, 可用: {[p.name for p in adapters.ALL_PROBES]}")
            continue
        try:
            pr = probe_cls().run(fr, video)
            results.append(pr)
            print(f"      探针 [{name}] → 维度 {pr['dim']}: {pr['score']:.2f}")
        except (adapters.ProbeUnavailable, NotImplementedError) as e:
            print(f"      ⚠️ 探针 [{name}] 跳过: {e}")

    # 合并人工分 (人工优先): 人工分以伪结果条目进入 dim_results, 报告可见
    for d, v in manual.items():
        if not any(r["dim"] == d for r in results):
            results.append({"dim": d, "score": v, "confidence": "manual",
                            "metrics": {}, "note": "人工评分"})
    final_scores: Dict[str, float] = {}
    for r in results:
        if r["dim"] not in final_scores:
            final_scores[r["dim"]] = r["score"]
    for d, v in manual.items():
        final_scores[d] = v
    adv = {d: v for d, v in final_scores.items() if d in spec.ADV_DIMS}
    flags = json.loads(args.flags) if args.flags else {}

    print("[4/4] 判定等级...")
    g = engine.assign_grade(final_scores, adv=adv or None, flags=flags, scale=args.scale)
    print(f"      综合得分 {g['composite']:.2f} ({g['scale']}分制)  →  等级 {g['level']} {g['public']} "
          f"(等效 {g['equiv']})")
    if g["capped"]:
        print(f"      ⚠️  一票否决: {g['cap_reason']} (上限 {g['level']})")

    rep = report.build_report(video, results, g, manual)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report.to_json(rep))
        print(f"报告已写入: {args.out}")
    if args.format in ("md", "both"):
        md = report.to_markdown(rep)
        md_path = args.out.replace(".json", ".md") if args.out else None
        if md_path:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"Markdown 报告: {md_path}")
        else:
            print(md)


def cmd_probes(args) -> None:
    print("重型探针可用性 (需自行安装依赖):")
    for name, ok in adapters.available_probes().items():
        print(f"  {'✅' if ok else '❌'} {name}")


def cmd_demo(args) -> None:
    """生成合成测试视频并跑通全流程 (用于验证工具与展示)。"""
    import os
    from . import demo
    vids = demo.make_synthetic_videos(args.outdir)
    print("合成测试视频:")
    for name, path in vids.items():
        print(f"  {name}: {path}")
    print()
    rows = []
    for name, path in vids.items():
        print(f"=== 评估 {name} ===")
        video = frames.probe_video(path)
        fr = frames.sample_frames(path, target_fps=args.fps, max_frames=args.max_frames,
                                  scale=args.scale_px, gray=True)
        results = [spatial.evaluate(fr), temporal.evaluate(fr), structure.evaluate(fr),
                   physics.evaluate(fr), texture.evaluate(fr)]
        final = {r["dim"]: r["score"] for r in results}
        g = engine.assign_grade(final, scale=args.scale)
        rows.append((name, g, final, {}))
        print(f"  A={final['A']:.2f} B={final['B']:.2f} C={final['C']:.2f} D={final['D']:.2f} E={final['E']:.2f} "
              f"综合={g['composite']:.2f} → {g['level']} {g['public']}")
        print()
    print("对比总结 (全自动 5 维度):")
    print(f"  {'视频':<28}{'A':>6}{'B':>6}{'C':>6}{'D':>6}{'E':>6}{'综合':>8}  等级")
    for name, g, final, _assumed in rows:
        print(f"  {name:<28}{final['A']:>6.2f}{final['B']:>6.2f}{final['C']:>6.2f}"
              f"{final['D']:>6.2f}{final['E']:>6.2f}{g['composite']:>8.2f}  {g['level']}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="alevel", description="A-Level AI 视频画质评估工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    pg = sub.add_parser("grade", help="纯人工评分 → 等级判定")
    pg.add_argument("--scores", required=True, help='JSON: {"A":4,"B":4,"C":5,"D":4,"E":4}')
    pg.add_argument("--scale", default=spec.DEFAULT_SCALE, choices=list(spec.SCALES))
    pg.add_argument("--flags", default=None, help='JSON: {"c_severe":true}')
    pg.add_argument("--json", action="store_true")
    pg.set_defaults(fn=cmd_grade)

    pe = sub.add_parser("evaluate", help="视频自动+人工混合评估")
    pe.add_argument("video")
    pe.add_argument("--manual", default=None, help='人工分 JSON (覆盖对应自动分)')
    pe.add_argument("--probes", default="", help="重型探针, 逗号分隔: mediapipe_hands,raft_flow,...")
    pe.add_argument("--fps", type=float, default=10.0, help="采样帧率 (默认10)")
    pe.add_argument("--max-frames", type=int, default=120, help="最大采样帧数 (默认120)")
    pe.add_argument("--scale-px", type=int, default=256, help="分析尺寸 (默认256)")
    pe.add_argument("--scale", default=spec.DEFAULT_SCALE, choices=list(spec.SCALES))
    pe.add_argument("--flags", default=None)
    pe.add_argument("--out", default=None, help="JSON 报告输出路径")
    pe.add_argument("--format", choices=["json", "md", "both"], default="both")
    pe.set_defaults(fn=cmd_evaluate)

    pp = sub.add_parser("probes", help="列出重型探针可用性")
    pp.set_defaults(fn=cmd_probes)

    pd = sub.add_parser("demo", help="生成合成视频并跑通全流程")
    pd.add_argument("--outdir", default="demo")
    pd.add_argument("--fps", type=float, default=10.0)
    pd.add_argument("--max-frames", type=int, default=120)
    pd.add_argument("--scale-px", type=int, default=256)
    pd.add_argument("--scale", default=spec.DEFAULT_SCALE, choices=list(spec.SCALES))
    pd.set_defaults(fn=cmd_demo)

    args = p.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
