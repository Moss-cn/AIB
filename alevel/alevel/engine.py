# -*- coding: utf-8 -*-
"""A-Level 评级引擎: 综合得分计算 / 等级判定 / 一票否决 / 需求核查

只依赖标准库。所有阈值均来自 spec.py, 本文件不含魔法数字。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import spec


class GradeError(ValueError):
    """评分输入不合法。"""


def composite_score(scores: Dict[str, float], scale: str = spec.DEFAULT_SCALE) -> float:
    """按方案 3.2 计算综合得分: (Σ w_i * s_i) * multiplier。

    scores 需包含全部核心五项 (A-E), 值域 1..5。进阶维度 (F-H) 不参与综合得分。
    """
    missing = [d for d in spec.CORE_DIMS if d not in scores]
    if missing:
        raise GradeError(f"缺少核心维度分数: {missing}")
    for d, v in scores.items():
        if d not in spec.CORE_DIMS:
            continue
        if not (1.0 <= v <= 5.0):
            raise GradeError(f"维度 {d} 得分 {v} 超出 1-5 范围")
    if scale not in spec.SCALES:
        raise GradeError(f"未知分制 {scale}, 可选: {list(spec.SCALES)}")
    weighted = sum(spec.WEIGHTS[d] * scores[d] for d in spec.CORE_DIMS)
    return round(weighted * spec.SCALES[scale]["multiplier"], 4)


def _grade_min(scale: str) -> List[float]:
    return spec.SCALES[scale]["grade_min"]


def requirements_met(level: Dict, composite: float, scores: Dict[str, float],
                     adv: Optional[Dict[str, float]], scale: str) -> Dict:
    """检查单个等级的全部要求, 返回 {met, missing[]}。

    adv 为进阶维度得分; 缺失 (None) 的进阶维度视为"未测/未满足"。
    """
    mins = _grade_min(scale)
    idx = spec.LEVELS.index(level["level"])
    min_req = mins[idx]
    missing: List[str] = []
    if composite < min_req:
        missing.append(f"综合得分≥{min_req} (实际 {composite:.2f})")
    for d, req in level["core"].items():
        if scores.get(d, 0) < req:
            missing.append(f"{d}≥{req} (实际 {scores.get(d):.1f})")
    for d, req in level["adv"].items():
        val = (adv or {}).get(d)
        if val is None:
            missing.append(f"{d}≥{req} (未测)")
        elif val < req:
            missing.append(f"{d}≥{req} (实际 {val:.1f})")
    return {"met": not missing, "missing": missing, "min_req": min_req}


def assign_grade(scores: Dict[str, float], adv: Optional[Dict[str, float]] = None,
                 flags: Optional[Dict[str, bool]] = None,
                 scale: str = spec.DEFAULT_SCALE) -> Dict:
    """从核心/进阶得分判定等级。

    逻辑: 从最高级往下找第一个满足全部要求的等级; 再应用一票否决上限。
    flags: {"c_severe": bool, "b_severe": bool}, 缺省按"维度得分==1"自动判定。
    返回: {level, composite, capped, cap_reason, requirements: [...], veto: {...}}
    """
    composite = composite_score(scores, scale)
    adv = {k: float(v) for k, v in (adv or {}).items()}
    flags = dict(flags or {})
    # 自动判定严重 (方案 3.4 的可操作化)
    if scores.get("C", 5) <= spec.SEVERE_SCORE:
        flags.setdefault("c_severe", True)
    if scores.get("B", 5) <= spec.SEVERE_SCORE:
        flags.setdefault("b_severe", True)

    # 1) 从最高级向下找第一个满足的等级
    chosen = spec.GRADES[0]
    chosen_req = None
    for g in reversed(spec.GRADES):
        req = requirements_met(g, composite, scores, adv, scale)
        if req["met"]:
            chosen = g
            chosen_req = req
            break

    # 2) 一票否决: 应用 cap
    cap_level: Optional[str] = None
    cap_reason: Optional[str] = None
    for dim, rule in spec.VETO.items():
        if flags.get(rule["flag"]):
            cap_level = rule["cap"]
            cap_reason = rule["reason"]
            break
    final_level = chosen["level"]
    if cap_level and spec.LEVELS.index(final_level) > spec.LEVELS.index(cap_level):
        final_level = cap_level

    # 3) 逐级列出要求核查, 便于报告
    req_table = []
    for g in spec.GRADES:
        r = requirements_met(g, composite, scores, adv, scale)
        req_table.append({"level": g["level"], **r})

    return {
        "level": final_level,
        "public": next(g["public"] for g in spec.GRADES if g["level"] == final_level),
        "equiv": next(g["equiv"] for g in spec.GRADES if g["level"] == final_level),
        "composite": composite,
        "scale": scale,
        "capped": final_level != chosen["level"],
        "capped_from": chosen["level"] if cap_level else None,
        "cap_reason": cap_reason,
        "chosen_req": chosen_req,
        "requirements": req_table,
        "veto": {"c_severe": bool(flags.get("c_severe")), "b_severe": bool(flags.get("b_severe"))},
    }


def model_capability(case_results: List[Dict]) -> Dict:
    """方案 5.2 模型能力分级 (L1-L3)。

    case_results: [{"case": "T01", "composite": float, "scores": {...}}, ...]
    返回 {level, reason, stats}。
    """
    core_cases = [c for c in case_results if spec.TEST_CASES.get(c["case"], {}).get("kind") == "core"]
    adv_cases = [c for c in case_results if spec.TEST_CASES.get(c["case"], {}).get("kind") == "adv"]
    def med(xs):
        if not xs:
            return None
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    core_med = med([c["composite"] for c in core_cases])
    adv_med = med([c["composite"] for c in adv_cases])
    t02 = next((c["composite"] for c in core_cases if c["case"] == "T02"), None)
    t06 = next((c["composite"] for c in core_cases if c["case"] == "T06"), None)
    reason, level = "未达 L1", None
    if core_med is not None:
        if core_med >= 4.0 and (adv_med or 0) >= 3.5:
            level, reason = "L3", f"核心中位数 {core_med:.2f}≥4.0, 进阶中位数 {adv_med:.2f}≥3.5"
        elif core_med >= 3.5 and (adv_med or 0) >= 3.0:
            level, reason = "L2", f"核心中位数 {core_med:.2f}≥3.5, 进阶中位数 {adv_med:.2f}≥3.0"
        elif core_med >= 3.0 and (t02 or 0) >= 3.0 and (t06 or 0) >= 3.0:
            level, reason = "L1", f"核心中位数 {core_med:.2f}≥3.0 且 T02={t02}, T06={t06} 均≥3.0"
        else:
            reason = (f"核心中位数 {core_med:.2f}, T02={t02}, T06={t06} 未达 L1 要求")
    return {"level": level, "reason": reason,
            "stats": {"core_median": core_med, "adv_median": adv_med, "T02": t02, "T06": t06}}
