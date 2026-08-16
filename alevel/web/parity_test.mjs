// JS 引擎 ↔ Python 引擎 全量等价性验证
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const eng = require("./js_engine.js");

const expectedPath = process.argv[2];
const expected = JSON.parse(readFileSync(expectedPath, "utf-8"));

let bad = 0, total = 0;
for (const [key, exp] of Object.entries(expected)) {
  const [scale, scoreStr, advName, flagName] = key.split("|");
  const vals = scoreStr.split(",").map(Number);
  const scores = { A: vals[0], B: vals[1], C: vals[2], D: vals[3], E: vals[4] };
  const advMap = {
    none: null, f4: { F: 4 }, f45: { F: 4.5 }, fg: { F: 4.5, G: 4 },
    fgh: { F: 4.5, G: 4.5, H: 4.5 },
  };
  const flagMap = { none: null, csev: { c_severe: true }, bsev: { b_severe: true } };
  const g = eng.assignGrade(scores, advMap[advName], flagMap[flagName], scale);
  total++;
  const got = { level: g.level, composite: g.composite, capped_from: g.capped_from };
  const ok = got.level === exp.level && Math.abs(got.composite - exp.composite) < 1e-6
    && got.capped_from === exp.capped_from;
  if (!ok) {
    bad++;
    if (bad <= 10) console.log("MISMATCH", key, "expect", JSON.stringify(exp), "got", JSON.stringify(got));
  }
}
console.log(bad === 0 ? "PASS: " + total + "/" + total + " cases identical" : "FAIL: " + bad + "/" + total);
process.exit(bad === 0 ? 0 : 1);
