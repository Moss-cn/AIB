// ============================================================================
// A-Level 评估引擎 (JS 版) — 与 alevel/engine.py + spec.py 严格等价
// 双重实现的目的: 人工评分模式无需加载 Pyodide, 浏览器内即时计算。
// 等价性由 web/parity_test.mjs 对照 Python 引擎验证 (3125 组合全量比对)。
// ============================================================================
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) module.exports = factory();
  else root.ALEVEL_ENGINE = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const CORE_DIMS = ["A", "B", "C", "D", "E"];
  const ADV_DIMS = ["F", "G", "H"];
  const WEIGHTS = { A: 0.20, B: 0.30, C: 0.20, D: 0.15, E: 0.15 };
  const SEVERE_SCORE = 1.0;

  // 与 spec.GRADES 完全一致 (min 为 2-10 分制)
  const GRADES = [
    { level: "A1",  public: "草稿预览",   equiv: "<720p",  min: 2.0,  core: {}, adv: {} },
    { level: "A2",  public: "基础可用",   equiv: "≈720p",  min: 3.0,  core: {}, adv: {} },
    { level: "A3",  public: "标清可用",   equiv: "≈1080p", min: 4.0,  core: {}, adv: {} },
    { level: "A4",  public: "高清可用",   equiv: "≈2K",    min: 5.0,  core: { C: 3 }, adv: {} },
    { level: "A5",  public: "高清良好",   equiv: "≈2.5K",  min: 6.0,  core: { B: 3 }, adv: {} },
    { level: "A6",  public: "高清优秀",   equiv: "≈3K",    min: 7.0,  core: { B: 4, C: 4 }, adv: {} },
    { level: "A7",  public: "影院级",     equiv: "等效4K",  min: 8.0,  core: { A: 4, B: 4, C: 4, D: 4, E: 4 }, adv: {} },
    { level: "A8",  public: "超高清级",   equiv: "等效5K",  min: 8.5,  core: { A: 4.5, B: 4.5, C: 4.5, D: 4.5, E: 4.5 }, adv: { F: 4 } },
    { level: "A9",  public: "超高清优秀", equiv: "6K-8K",   min: 9.0,  core: { A: 4.5, B: 4.5, C: 4.5, D: 4.5, E: 4.5 }, adv: { F: 4.5, G: 4 } },
    { level: "A10", public: "世界模拟级", equiv: "8K+",     min: 9.5,  core: { A: 5, B: 5, C: 5, D: 5, E: 5 }, adv: { F: 4.5, G: 4.5, H: 4.5 } },
  ];
  const LEVELS = GRADES.map((g) => g.level);

  const SCALES = {
    "2-10": { mult: 2.0, mins: [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 8.5, 9.0, 9.5] },
    "1-5":  { mult: 1.0, mins: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.25, 4.5, 4.75] },
  };
  const DEFAULT_SCALE = "2-10";

  const VETO = {
    C: { flag: "c_severe", cap: "A2", reason: "结构完整性严重畸形(六指/面部崩坏/文字乱码)" },
    B: { flag: "b_severe", cap: "A3", reason: "持续大幅闪烁或身份漂移" },
  };

  const DIM_INFO = {
    A: { name: "有效空间分辨率", desc: "画面里有多少细节是真实、清晰的", traditional: "分辨率、锐度" },
    B: { name: "时间稳定性", desc: "连续播放是否稳定、不闪不跳", traditional: "帧率、抖动、运动模糊" },
    C: { name: "结构完整性", desc: "手、脸、文字等关键结构是否正常", traditional: "几何失真、畸变" },
    D: { name: "物理一致性", desc: "光影、反射、碰撞是否合理", traditional: "色彩准确、光影真实" },
    E: { name: "纹理自然度", desc: "表面质感是否自然, 无 AI 塑料感", traditional: "噪点、压缩伪影" },
    F: { name: "3D 几何一致性", desc: "画面是否像真实 3D 场景, 视角变化正确", traditional: "立体感、透视" },
    G: { name: "长期时空记忆", desc: "长视频中人物、物体是否保持一致", traditional: "角色连续性、场景一致性" },
    H: { name: "因果与交互合理性", desc: "接触、推动等交互是否符合逻辑", traditional: "事件逻辑" },
  };

  function compositeScore(scores, scale) {
    scale = scale || DEFAULT_SCALE;
    for (const d of CORE_DIMS) {
      if (!(d in scores)) throw new Error("缺少核心维度分数: " + d);
      const v = scores[d];
      if (!(v >= 1 && v <= 5)) throw new Error("维度 " + d + " 得分超出 1-5 范围: " + v);
    }
    const sc = SCALES[scale];
    if (!sc) throw new Error("未知分制 " + scale);
    let weighted = 0;
    for (const d of CORE_DIMS) weighted += WEIGHTS[d] * scores[d];
    return Math.round(weighted * sc.mult * 10000) / 10000;
  }

  function requirementsMet(level, composite, scores, adv, scale) {
    const sc = SCALES[scale] || SCALES[DEFAULT_SCALE];
    const idx = LEVELS.indexOf(level.level);
    const minReq = sc.mins[idx];
    const missing = [];
    if (composite < minReq) missing.push("综合得分≥" + minReq + " (实际 " + composite.toFixed(2) + ")");
    for (const d of Object.keys(level.core)) {
      const req = level.core[d];
      const val = scores[d] != null ? scores[d] : 0;
      if (val < req) missing.push(d + "≥" + req + " (实际 " + val.toFixed(1) + ")");
    }
    for (const d of Object.keys(level.adv)) {
      const req = level.adv[d];
      const val = adv && adv[d] != null ? adv[d] : null;
      if (val == null) missing.push(d + "≥" + req + " (未测)");
      else if (val < req) missing.push(d + "≥" + req + " (实际 " + val.toFixed(1) + ")");
    }
    return { met: missing.length === 0, missing, min_req: minReq };
  }

  function assignGrade(scores, adv, flags, scale) {
    scale = scale || DEFAULT_SCALE;
    const composite = compositeScore(scores, scale);
    adv = adv || {};
    flags = flags || {};
    if ((scores.C != null && scores.C <= SEVERE_SCORE) && !("c_severe" in flags)) flags.c_severe = true;
    if ((scores.B != null && scores.B <= SEVERE_SCORE) && !("b_severe" in flags)) flags.b_severe = true;

    let chosen = GRADES[0], chosenReq = null;
    for (let i = GRADES.length - 1; i >= 0; i--) {
      const req = requirementsMet(GRADES[i], composite, scores, adv, scale);
      if (req.met) { chosen = GRADES[i]; chosenReq = req; break; }
    }

    let capLevel = null, capReason = null;
    for (const dim of Object.keys(VETO)) {
      const rule = VETO[dim];
      if (flags[rule.flag]) { capLevel = rule.cap; capReason = rule.reason; break; }
    }
    let finalLevel = chosen.level;
    if (capLevel && LEVELS.indexOf(finalLevel) > LEVELS.indexOf(capLevel)) finalLevel = capLevel;

    const reqTable = GRADES.map((g) => Object.assign({ level: g.level }, requirementsMet(g, composite, scores, adv, scale)));

    return {
      level: finalLevel,
      public: GRADES.find((g) => g.level === finalLevel).public,
      equiv: GRADES.find((g) => g.level === finalLevel).equiv,
      composite,
      scale,
      capped: finalLevel !== chosen.level,
      capped_from: capLevel ? chosen.level : null,
      cap_reason: capReason,
      chosen_req: chosenReq,
      requirements: reqTable,
      veto: { c_severe: !!flags.c_severe, b_severe: !!flags.b_severe },
    };
  }

  // 方案 5.2 模型能力分级 (L1-L3)
  function modelCapability(caseResults) {
    const med = (xs) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
    const core = caseResults.filter((c) => (c.kind || "core") === "core").map((c) => c.composite);
    const adv = caseResults.filter((c) => c.kind === "adv").map((c) => c.composite);
    const coreMed = med(core), advMed = med(adv);
    const t02 = (caseResults.find((c) => c.case === "T02") || {}).composite;
    const t06 = (caseResults.find((c) => c.case === "T06") || {}).composite;
    let level = null, reason = "未达 L1";
    if (coreMed != null) {
      if (coreMed >= 4.0 && (advMed || 0) >= 3.5) { level = "L3"; reason = "核心中位数 " + coreMed.toFixed(2) + "≥4.0, 进阶中位数 " + (advMed || 0).toFixed(2) + "≥3.5"; }
      else if (coreMed >= 3.5 && (advMed || 0) >= 3.0) { level = "L2"; reason = "核心中位数 " + coreMed.toFixed(2) + "≥3.5, 进阶中位数 " + (advMed || 0).toFixed(2) + "≥3.0"; }
      else if (coreMed >= 3.0 && (t02 || 0) >= 3.0 && (t06 || 0) >= 3.0) { level = "L1"; reason = "核心中位数 " + coreMed.toFixed(2) + "≥3.0 且 T02=" + (t02 || 0) + ", T06=" + (t06 || 0) + " 均≥3.0"; }
      else reason = "核心中位数 " + coreMed.toFixed(2) + ", T02=" + (t02 || 0) + ", T06=" + (t06 || 0) + " 未达 L1 要求";
    }
    return { level, reason, stats: { core_median: coreMed, adv_median: advMed, T02: t02, T06: t06 } };
  }

  return { CORE_DIMS, ADV_DIMS, WEIGHTS, GRADES, LEVELS, SCALES, DEFAULT_SCALE, VETO, DIM_INFO, compositeScore, requirementsMet, assignGrade, modelCapability };
});
