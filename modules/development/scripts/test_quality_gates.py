#!/usr/bin/env python3
"""Lock the shipped quality-gates profile (WI-1). The gates treat an empty
command as silent-allow, so an accidental revert to "" would disable lint/build
enforcement without any signal. This guards against that regression.

Run from the repo root:  python scripts/test_quality_gates.py"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSED = 0


def check(name, condition, detail=""):
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def main():
    with open(os.path.join(ROOT, ".gigacode", "quality-gates.json"),
              encoding="utf-8") as handle:
        qg = json.load(handle)
    for section in ("lint", "build", "test"):
        cfg = qg.get(section)
        check(f"{section}_section_present", isinstance(cfg, dict), cfg)
        check(f"{section}_command_nonempty",
              bool((cfg.get("command") or "").strip()), section)
    check("lint_applies_to_code",
          any(g.endswith((".kt", ".java")) for g in qg["lint"].get("applies_to", [])),
          qg["lint"].get("applies_to"))
    print(f"\nAll {PASSED} quality-gates checks passed")


if __name__ == "__main__":
    main()
