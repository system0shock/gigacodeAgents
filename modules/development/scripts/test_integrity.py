#!/usr/bin/env python3
"""Tests for gate_integrity (S2): Stop-time control-plane integrity baseline."""
import os
import shutil
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".gigacode", "hooks")
sys.path.insert(0, os.path.join(HOOKS, "gates"))
import gate_integrity as gi  # noqa: E402

PASSED = 0


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"ok: {name}")
    else:
        print(f"FAIL {name}: {detail}")
        sys.exit(1)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def setup_tree(root):
    gig = os.path.join(root, ".gigacode")
    write(os.path.join(gig, "hooks", "router.py"), "print('router')\n")
    write(os.path.join(gig, "hooks", "router.config.json"), '{"routes": []}\n')
    write(os.path.join(gig, "hooks", "gates", "git_guard.py"), "def run(e):\n    return {}\n")
    write(os.path.join(gig, "hooks", "gates", "_lib.py"), "def root():\n    pass\n")
    write(os.path.join(gig, "quality-gates.json"), '{"test": {}}\n')
    # runtime + caches that MUST stay out of the baseline:
    write(os.path.join(gig, "logs", "decisions.jsonl"), '{"x": 1}\n')
    write(os.path.join(gig, "logs", "router-state.json"), '{"s": 1}\n')
    write(os.path.join(gig, "approvals", "slug", "intake.ok"), "ok\n")
    write(os.path.join(gig, "hooks", "gates", "__pycache__", "git_guard.cpython-314.pyc"), "bytecode")
    return gig


def regen(gig):
    with open(os.path.join(gig, gi.MANIFEST_NAME), "w", encoding="utf-8") as fh:
        fh.write(gi.render_manifest(gi.compute(gig)))


def main():
    tmp = tempfile.mkdtemp()
    stop = {"hook_event_name": "Stop"}
    try:
        gig = setup_tree(tmp)
        os.environ["GIGACODE_ROOT"] = tmp

        # 1. No manifest -> fail-open allow + warn
        r = gi.run(stop)
        check("absent_fail_open", r["decision"] == "allow" and "baseline absent" in r.get("reason", ""), r)

        # 2. enforcement set = code+config only; runtime/caches excluded
        files = gi.enforcement_files(gig)
        check("includes_code_config", "hooks/router.py" in files and "quality-gates.json" in files
              and "hooks/gates/git_guard.py" in files, files)
        check("excludes_runtime_cache",
              all(not f.startswith(("logs/", "approvals/")) and "__pycache__" not in f
                  and not f.endswith((".pyc", ".jsonl")) for f in files), files)

        # 3. baseline generated -> pristine allow
        regen(gig)
        check("pristine_allow", gi.run(stop)["decision"] == "allow", gi.run(stop))

        # 4. legitimate runtime churn (logs/approvals) does NOT trip it
        write(os.path.join(gig, "logs", "decisions.jsonl"), '{"x": 2}\n{"y": 3}\n')
        write(os.path.join(gig, "approvals", "slug2", "contract.ok"), "ok\n")
        check("runtime_churn_allow", gi.run(stop)["decision"] == "allow", gi.run(stop))

        # 5. tampered enforcement file -> block, names it
        write(os.path.join(gig, "hooks", "gates", "git_guard.py"),
              "def run(e):\n    return {'decision': 'allow'}  # neutered\n")
        r = gi.run(stop)
        check("tamper_block", r["decision"] == "block" and "git_guard.py" in r.get("reason", ""), r)
        write(os.path.join(gig, "hooks", "gates", "git_guard.py"), "def run(e):\n    return {}\n")
        check("restore_allow", gi.run(stop)["decision"] == "allow", gi.run(stop))

        # 6. extra/untracked enforcement file -> block
        write(os.path.join(gig, "hooks", "gates", "evil.py"), "def run(e):\n    return {'decision': 'allow'}\n")
        r = gi.run(stop)
        check("untracked_block", r["decision"] == "block" and "evil.py" in r.get("reason", ""), r)
        os.remove(os.path.join(gig, "hooks", "gates", "evil.py"))

        # 7. a manifested file removed -> block
        os.remove(os.path.join(gig, "quality-gates.json"))
        r = gi.run(stop)
        check("missing_block", r["decision"] == "block" and "quality-gates.json" in r.get("reason", ""), r)

        # 8. non-Stop event -> allow without scanning
        check("non_stop_allow", gi.run({"hook_event_name": "PreToolUse"})["decision"] == "allow")

        print(f"\nAll {PASSED} integrity checks passed")
    finally:
        os.environ.pop("GIGACODE_ROOT", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
