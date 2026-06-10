#!/usr/bin/env python3
"""Offline unit tests for quality gates. Run from the repo root:
    python scripts/test_gates.py
Gates are loaded in-process; fixtures live in temp dirs pointed at via
the GIGACODE_ROOT env override."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES_DIR = os.path.join(ROOT, ".gigacode", "hooks", "gates")
PASSED = 0


def load_gate(name):
    path = os.path.join(GATES_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, condition, detail=""):
    # explicit raise (not assert) so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def make_fixture():
    """Temp template root: rules/, openspec/changes/, .gigacode/logs/."""
    tmp = tempfile.mkdtemp(prefix="gates-test-")
    os.makedirs(os.path.join(tmp, "rules"))
    for rule in ("development-flow.md", "openspec.md"):
        shutil.copy(os.path.join(ROOT, "rules", rule), os.path.join(tmp, "rules"))
    os.makedirs(os.path.join(tmp, "openspec", "changes", "archive"))
    src_config = os.path.join(ROOT, "openspec", "config.yaml")
    if os.path.exists(src_config):
        shutil.copy(src_config, os.path.join(tmp, "openspec"))
    os.makedirs(os.path.join(tmp, ".gigacode", "logs"))
    return tmp


class fixture_root:
    """Context manager: point _lib.root() at a fresh fixture tree."""

    def __enter__(self):
        self.tmp = make_fixture()
        self._orig = os.environ.get("GIGACODE_ROOT")
        os.environ["GIGACODE_ROOT"] = self.tmp
        return self.tmp

    def __exit__(self, *exc):
        if self._orig is None:
            os.environ.pop("GIGACODE_ROOT", None)
        else:
            os.environ["GIGACODE_ROOT"] = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def write_qg(root_dir, config):
    path = os.path.join(root_dir, ".gigacode", "quality-gates.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)


def write_script(root_dir, name, exit_code):
    """Tiny python script used as a fake lint/build command."""
    with open(os.path.join(root_dir, name), "w", encoding="utf-8") as handle:
        handle.write(f"import sys\nsys.exit({exit_code})\n")


def test_lib():
    lib = load_gate("_lib")
    check("lib_glob_root_file", lib.matches_globs("Main.kt", ["**/*.kt"]))
    check("lib_glob_nested", lib.matches_globs("src/a/B.kt", ["**/*.kt"]))
    check("lib_glob_nonmatch", not lib.matches_globs("README.md", ["**/*.kt"]))
    rc, tail = lib.run_command("definitely-missing-tool-xyz", 5)
    check("lib_missing_command", rc == -1, (rc, tail))
    with fixture_root() as fix:
        lib.journal_skip("gate_test", "test reason")
        journal = os.path.join(fix, ".gigacode", "logs", "decisions.jsonl")
        with open(journal, "r", encoding="utf-8") as handle:
            line = handle.read()
        check("lib_journal_skip", '"gate_test"' in line and '"skip"' in line, line)


def main():
    test_lib()
    print(f"\nAll {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
