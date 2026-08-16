# -*- coding: utf-8 -*-
"""评级引擎单元测试: 公式 / 阈值 / 一票否决 / 进阶维度 / 模型分级。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alevel import engine, spec


def s(**kw):
    """默认全5分的核心分, 可用关键字覆盖。"""
    base = {"A": 5.0, "B": 5.0, "C": 5.0, "D": 5.0, "E": 5.0}
    base.update({k: float(v) for k, v in kw.items()})
    return base


def test_composite_formula():
    assert engine.composite_score(s()) == 10.0                 # 全5 → 10
    assert engine.composite_score(s(A=4, B=4, C=5, D=4, E=4)) == 8.4   # 附录A示例
    assert engine.composite_score(s(A=2, B=2, C=2, D=2, E=2)) == 4.0   # 全2 → 4
    # 权重正确性: B=0.30 权重最大
    assert engine.composite_score(s(B=1)) < engine.composite_score(s(A=1))
    assert engine.composite_score(s(B=1)) < engine.composite_score(s(C=1))


def test_grade_boundaries():
    g = engine.assign_grade(s(A=4, B=4, C=5, D=4, E=4))
    assert g["level"] == "A7", g            # 8.4 且核心均≥4 → A7
    g = engine.assign_grade(s(), adv={"F": 5.0, "G": 5.0, "H": 5.0})   # 全5+进阶 → A10
    assert g["level"] == "A10", g
    g = engine.assign_grade(s(A=3.9, B=4, C=4, D=4, E=4))   # 综合 7.96 → A6
    assert g["level"] == "A6", g
    g = engine.assign_grade(s(A=4, B=4, C=4, D=4, E=4))     # 综合 8.0 → A7 (边界)
    assert g["level"] == "A7", g
    # 方案 3.3 等级表的已知缺陷: A4 需 C≥3, 但 A5 仅需 B≥3 (核心项要求不单调)。
    # 本工具忠实实现方案原文 → C=2 会落到 A5; 该缺陷在可行性报告中标注。
    g = engine.assign_grade(s(A=5, B=5, C=2, D=5, E=5))
    assert g["level"] == "A5", g
    g = engine.assign_grade(s(A=3, B=3, C=3, D=3, E=3))     # 综合 6.0, B=3≥3 → A5
    assert g["level"] == "A5", g
    # C=2.9 → 综合 5.96 < 6.0, A5 门槛不过 → A3
    g = engine.assign_grade(s(A=3, B=3, C=2.9, D=3, E=3))
    assert g["level"] == "A3", g


def test_advanced_gates():
    core45 = s(A=4.5, B=4.5, C=4.5, D=4.5, E=4.5)           # 综合 9.0
    g = engine.assign_grade(core45, adv={"F": 4.0})
    assert g["level"] == "A8", g                            # A9 需 G≥4 → 无 → A8
    g = engine.assign_grade(core45, adv={"F": 4.5, "G": 4.0})
    assert g["level"] == "A9", g                            # A10 需综合9.5 → 否
    g = engine.assign_grade(s(), adv={"F": 4.5, "G": 4.5, "H": 4.5})
    assert g["level"] == "A10", g
    # 进阶维度未测 → A8 不可达
    g = engine.assign_grade(core45, adv=None)
    assert g["level"] == "A7", g


def test_veto():
    # C 严重畸形 (得分1) → 即使其他全5也封顶 A2 (自然判定上限 A5, 再被否决到 A2)
    g = engine.assign_grade(s(C=1))
    assert g["level"] == "A2" and g["capped"] and g["capped_from"] == "A5", g
    # B 严重闪烁 → 封顶 A3 (自然判定上限 A4, 再被否决到 A3)
    g = engine.assign_grade(s(B=1))
    assert g["level"] == "A3" and g["capped_from"] == "A4", g
    # 显式 flag + 全5分+进阶 → 自然上限 A10 被否决到 A3
    g = engine.assign_grade(s(), adv={"F": 5.0, "G": 5.0, "H": 5.0}, flags={"b_severe": True})
    assert g["level"] == "A3" and g["capped_from"] == "A10", g
    # 显式 flag 覆盖: 即使 C=4, flag 也触发否决 (全5分+进阶 → 自然上限 A10)
    g = engine.assign_grade(s(), adv={"F": 5.0, "G": 5.0, "H": 5.0}, flags={"c_severe": True})
    assert g["level"] == "A2" and g["capped_from"] == "A10", g
    # 得分1但综合分低于A2 → 落到 A1
    g = engine.assign_grade(s(A=1, B=1, C=1, D=1, E=1))
    assert g["level"] == "A1", g


def test_scale_1to5():
    g = engine.assign_grade(s(A=4, B=4, C=5, D=4, E=4), scale="1-5")
    assert abs(g["composite"] - 4.2) < 1e-6
    g2 = engine.assign_grade(s(A=4, B=4, C=5, D=4, E=4))
    assert g["level"] == g2["level"] == "A7"    # 两种分制下同一组分数等级一致


def test_model_capability():
    def case(cid, comp):
        return {"case": cid, "composite": comp, "scores": s()}
    core = [case(f"T0{i}", 3.2) for i in range(1, 9)]
    core[1] = case("T02", 3.1)   # 手部
    core[5] = case("T06", 3.2)   # 文字
    advs = [case(f"T{ i }", 3.1) for i in range(9, 13)]
    ml = engine.model_capability(core + advs)
    assert ml["level"] == "L1", ml
    core2 = [case(f"T0{i}", 4.1) for i in range(1, 9)]
    advs2 = [case(f"T{i}", 3.6) for i in range(9, 13)]
    ml2 = engine.model_capability(core2 + advs2)
    assert ml2["level"] == "L3", ml2


def test_spec_consistency():
    # 等级表与权重一致性: 全5分 → 综合10 → A10 可达到
    assert spec.GRADES[-1]["min"] <= 10.0
    # 每个等级的 min 应随等级单调不减
    mins = [g["min"] for g in spec.GRADES]
    assert mins == sorted(mins)
    # 等级表长度 = 10
    assert len(spec.GRADES) == 10 and len(spec.LEVELS) == 10
