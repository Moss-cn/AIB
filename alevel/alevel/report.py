# -*- coding: utf-8 -*-
"""报告生成: JSON (机器可读) + Markdown (人可读, 中文)。"""
from __future__ import annotations

import json
from typing import Dict, List

from . import spec


def build_report(video_info, dim_results: List[Dict], grade: Dict,
                 manual: Dict, model_level: Dict = None) -> Dict:
    """组装统一报告字典。"""
    scores = {d["dim"]: d["score"] for d in dim_results if d.get("dim") in spec.CORE_DIMS}
    return {
        "schema_version": "1.0",
        "video": video_info,
        "scores": {d: {"value": s, "source": "auto" if manual.get(d) is None else "manual",
                        **({} if manual.get(d) is None else {"manual_value": manual[d]})}
                   for d, s in scores.items()},
        "manual_scores": manual,
        "grade": grade,
        "model_level": model_level,
        "metric_details": dim_results,
        "test_cases_used": [],
    }


def to_json(report: Dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)


def to_markdown(report: Dict) -> str:
    g = report["grade"]
    lines: List[str] = []
    lines.append("# A-Level 画质评估报告")
    lines.append("")
    lines.append(f"- **等级**: **{g['level']}** {g['public']} (等效 {g['equiv']})")
    lines.append(f"- **综合得分**: {g['composite']:.2f} / 10 (分制 {g['scale']})")
    if g.get("cap_reason"):
        lines.append(f"- ⚠️ **一票否决**: {g['cap_reason']} → 最高等级 {g['level']}")
    if g.get("capped"):
        lines.append(f"- ⚠️ 因否决项从 {g['capped_from']} 下调至 {g['level']}")
    v = report.get("video")
    if v:
        lines.append("")
        lines.append("## 视频信息")
        lines.append(f"- {v.get('path')} | {v.get('width')}x{v.get('height')} @ {v.get('fps'):.2f}fps | "
                     f"{v.get('duration_s', 0):.1f}s | codec: {v.get('codec')}")
    lines.append("")
    lines.append("## 维度得分 (1-5)")
    lines.append("")
    lines.append("| 维度 | 名称 | 得分 | 来源 | 说明 |")
    lines.append("|------|------|------|------|------|")
    for d, meta in report["scores"].items():
        info = spec.DIM_INFO[d]
        src = meta["source"]
        note = ""
        for md in report["metric_details"]:
            if md.get("dim") == d:
                note = md.get("note", "")
                if md.get("metrics"):
                    note += " " + json.dumps(md["metrics"], ensure_ascii=False)
        lines.append(f"| {d} | {info['name']} | {meta['value']} | {src} | {note} |")
    lines.append("")
    lines.append("## 等级判定过程")
    lines.append("")
    lines.append("| 等级 | 综合分要求 | 满足? | 缺失项 |")
    lines.append("|------|-----------|-------|--------|")
    for r in g["requirements"]:
        mark = "✅" if r["met"] else "❌"
        lines.append(f"| {r['level']} | ≥{r['min_req']} | {mark} | "
                     f"{'、'.join(r['missing']) if r['missing'] else '—'} |")
    if report.get("model_level"):
        ml = report["model_level"]
        lines.append("")
        lines.append(f"## 模型能力分级: {ml['level'] or '未达 L1'} — {ml['reason']}")
    lines.append("")
    lines.append("> 自动指标为初筛代理, 阈值需在真实语料上标定; 高等级 (A7+) 建议人工复核。")
    return "\n".join(lines)
