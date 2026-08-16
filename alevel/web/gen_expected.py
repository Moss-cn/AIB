# -*- coding: utf-8 -*-
"""生成 JS 引擎等价性测试的期望值 (由 parity_test.mjs 调用)。"""
import itertools, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from alevel import engine

def main():
    out = {}
    combos = list(itertools.product([1.0, 2.0, 3.0, 4.0, 5.0], repeat=5))
    adv_variants = [
        ("none", None),
        ("f4", {"F": 4.0}), ("f45", {"F": 4.5}), ("fg", {"F": 4.5, "G": 4.0}),
        ("fgh", {"F": 4.5, "G": 4.5, "H": 4.5}),
    ]
    flag_variants = [("none", None), ("csev", {"c_severe": True}), ("bsev", {"b_severe": True})]
    for scale in ("2-10", "1-5"):
        for combo in combos:
            scores = dict(zip("ABCDE", combo))
            key = f"{scale}|{','.join(str(int(x)) for x in combo)}|none|none"
            g = engine.assign_grade(scores, scale=scale)
            out[key] = {"level": g["level"], "composite": g["composite"], "capped_from": g["capped_from"]}
            for aname, adv in adv_variants:
                for fname, flags in flag_variants:
                    key = f"{scale}|{','.join(str(int(x)) for x in combo)}|{aname}|{fname}"
                    g = engine.assign_grade(scores, adv=adv, flags=flags, scale=scale)
                    out[key] = {"level": g["level"], "composite": g["composite"], "capped_from": g["capped_from"]}
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"expected cases: {len(out)}")

if __name__ == "__main__":
    main()
