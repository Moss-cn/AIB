#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 web/index.html: 内联 JS 引擎 + 内嵌 Python 模块 (供 Pyodide 使用)。

用法:
    python web/build.py [repo_url]
      repo_url 可选, 写入页头 GitHub 链接 (默认 #)

产物: web/index.html — 单文件, 双击即可在浏览器打开 (自动指标需联网加载 Pyodide)。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# 内嵌到浏览器的 Python 模块 (Pyodide 中运行): 键为引导脚本使用的文件名
PY_SOURCES = {
    "spec.py": ROOT / "alevel" / "spec.py",
    "util.py": ROOT / "alevel" / "metrics" / "util.py",
    "engine.py": ROOT / "alevel" / "engine.py",
    "spatial.py": ROOT / "alevel" / "metrics" / "spatial.py",
    "temporal.py": ROOT / "alevel" / "metrics" / "temporal.py",
    "texture.py": ROOT / "alevel" / "metrics" / "texture.py",
}


def main() -> int:
    repo_url = sys.argv[1] if len(sys.argv) > 1 else "#"
    tpl = (WEB / "template.html").read_text(encoding="utf-8")

    js_engine = (WEB / "js_engine.js").read_text(encoding="utf-8")
    # 防止内联 JS 中出现 </script> 提前闭合
    js_engine = js_engine.replace("</script", "<\\/script")

    py_mods = {name: (path.read_text(encoding="utf-8")) for name, path in PY_SOURCES.items()}
    py_json = json.dumps(py_mods, ensure_ascii=False)

    html = tpl
    html = html.replace("/*__JS_ENGINE__*/", js_engine)
    html = html.replace("/*__PY_MODULES__*/", py_json)
    html = html.replace('id="gh-link" href="#"', 'id="gh-link" href="' + repo_url + '"')

    out = WEB / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"built {out} ({len(html)} bytes, py_modules={len(py_mods)}, engine={len(js_engine)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
