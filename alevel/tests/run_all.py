# -*- coding: utf-8 -*-
"""极简测试运行器: python tests/run_all.py"""
import importlib, os, sys, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODULES = ["test_engine", "test_metrics"]

def main():
    total = passed = 0
    failed = []
    for mname in MODULES:
        mod = importlib.import_module(mname)
        fns = sorted(n for n in dir(mod) if n.startswith("test_"))
        for fn in fns:
            total += 1
            try:
                getattr(mod, fn)()
                passed += 1
                print(f"  ✅ {mname}.{fn}")
            except Exception as e:
                failed.append((mname, fn, e))
                print(f"  ❌ {mname}.{fn}: {e}")
                traceback.print_exc()
    print(f"\n{passed}/{total} passed")
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
