# Analytics Overhaul Phase 1 (Hook Infrastructure) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the analytics module's generation-1 hooks with the dev-flow router + gates standard, including the new bootstrap/techdocs/final-format/run-output gates, offline test suites, and rewired smoke checks.

**Architecture:** `router.py`, `_lib.py`, `git_guard.py`, and `hook_probe.py` are copied from `feature/dev-flow-enforcement` (verbatim except a small git_guard diff for the spec-bootstrap rule). Five gates are written new for the analytics flow. Two offline test suites (`test_router.py`, `test_gates.py`) plus rewritten smoke checks verify everything without GigaCode, MCP, or network. Design: `docs/superpowers/specs/2026-06-11-gigacode-analytics-flow-overhaul-design.md`.

**Tech Stack:** Python 3 stdlib only (hooks + tests), JSON configs, bash + PowerShell 5.1 smoke scripts.

---

## Execution Context

- Work happens on a new branch off the analytics template (create via the superpowers:using-git-worktrees skill):

```bash
git worktree add .worktrees/analytics-overhaul -b feature/analytics-overhaul feature/analytics-template
cd .worktrees/analytics-overhaul
```

- **All test/smoke commands run from `modules/analytics/` inside the worktree.** `git show` copy commands and `git add` paths are worktree-root-relative.
- Phase 2 (skill/agents/commands/README rewrite) is a separate plan. Until then the module keeps 5 agents and the old skill text; smoke checks keep asserting 5 agents in this phase.
- Run statuses in `manifest.json`: `scoping` → `draft` → `confirmed` → `complete` (`scoping` was added to the design so the mandatory scope-confirmation stop is not blocked by the Stop gate).

## File Structure

```text
modules/analytics/
  .gitignore                                  # NEW: runtime dirs
  .gigacode/
    settings.json                             # REWRITTEN: router wiring, permissions
    quality-gates.json                        # NEW: optional validator commands
    hooks/
      router.py                               # COPY (verbatim) from dev-flow
      router.config.json                      # NEW: analytics routes
      hook_probe.py                           # COPY (verbatim) from dev-flow
      preflight_check.py                      # DELETED (replaced by gate)
      validate_output.py                      # DELETED (replaced by gate)
      gates/
        _lib.py                               # COPY (verbatim) from dev-flow
        git_guard.py                          # COPY + spec-bootstrap diff
        gate_context_inject.py                # NEW (adapted from dev-flow)
        preflight_check.py                    # NEW (port of gen-1 hook as gate)
        gate_spec_bootstrap.py                # NEW
        gate_techdocs.py                      # NEW
        gate_final_format.py                  # NEW
        validate_run_output.py                # NEW
  scripts/
    test_router.py                            # NEW: offline router suite
    test_gates.py                             # NEW: offline gates suite
    smoke-check.sh                            # REWRITTEN
    smoke-check.ps1                           # REWRITTEN
```

---

### Task 1: Copy router infrastructure from dev-flow

**Files:**
- Create: `modules/analytics/.gigacode/hooks/router.py` (copy)
- Create: `modules/analytics/.gigacode/hooks/hook_probe.py` (copy)
- Create: `modules/analytics/.gigacode/hooks/gates/_lib.py` (copy)
- Create: `modules/analytics/.gitignore`

- [ ] **Step 1: Copy the three files verbatim** (from the worktree root; `git show` avoids BOM/encoding issues that PowerShell redirects introduce — keep using bash):

```bash
mkdir -p modules/analytics/.gigacode/hooks/gates
git show feature/dev-flow-enforcement:.gigacode/hooks/router.py        > modules/analytics/.gigacode/hooks/router.py
git show feature/dev-flow-enforcement:.gigacode/hooks/hook_probe.py    > modules/analytics/.gigacode/hooks/hook_probe.py
git show feature/dev-flow-enforcement:.gigacode/hooks/gates/_lib.py    > modules/analytics/.gigacode/hooks/gates/_lib.py
```

- [ ] **Step 2: Create `modules/analytics/.gitignore`:**

```gitignore
__pycache__/
*.pyc
.gigacode/logs/
.gigacode/tmp/
```

- [ ] **Step 3: Sanity-check the copied router fails closed without a config** (from `modules/analytics/`):

```bash
printf '%s' '{}' | python .gigacode/hooks/router.py
```

Expected: one JSON line with `"decision": "block"` and a reason mentioning `router.config.json` (the config is intentionally not created until Task 10).

- [ ] **Step 4: Commit**

```bash
git add modules/analytics/.gigacode/hooks/router.py modules/analytics/.gigacode/hooks/hook_probe.py modules/analytics/.gigacode/hooks/gates/_lib.py modules/analytics/.gitignore
git commit -m "Copy hook router infrastructure into analytics module"
```

---

### Task 2: Router test suite

**Files:**
- Create: `modules/analytics/scripts/test_router.py`

- [ ] **Step 1: Write the full suite.** It copies `.gigacode/hooks` into a temp sandbox (so journal/state writes never touch the tree) and drives `router.py` via subprocess:

```python
#!/usr/bin/env python3
"""Offline tests for the analytics hook router. Run from modules/analytics:
    python scripts/test_router.py
Copies .gigacode/hooks into a temp sandbox so journal/state writes never
touch the working tree; drives router.py via subprocess."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_SRC = os.path.join(ROOT, ".gigacode", "hooks")
PASSED = 0

ALLOW_GATE = "def run(event):\n    return {'decision': 'allow'}\n"
BLOCK_GATE = "def run(event):\n    return {'decision': 'block', 'reason': 'fixture block'}\n"
CRASH_GATE = "def run(event):\n    raise RuntimeError('boom')\n"
BAD_GATE = "def run(event):\n    return ['nope']\n"


def check(name, condition, detail=""):
    # explicit raise (not assert) so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


class Sandbox:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="arouter-")
        self.hooks = os.path.join(self.tmp, "hooks")
        shutil.copytree(HOOKS_SRC, self.hooks)
        config = os.path.join(self.hooks, "router.config.json")
        if os.path.exists(config):
            os.remove(config)  # each test writes its own
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def config(self, data):
        path = os.path.join(self.hooks, "router.config.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(data if isinstance(data, str) else json.dumps(data))

    def gate(self, name, body):
        path = os.path.join(self.hooks, "gates", name + ".py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)

    def run(self, payload, args=()):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        proc = subprocess.run(
            [sys.executable, os.path.join(self.hooks, "router.py"), *args],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            raise SystemExit(f"router exit {proc.returncode}: {proc.stderr.decode(errors='replace')}")
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise SystemExit(f"router emitted non-JSON: {out!r}")


def test_stdin_safety():
    with Sandbox() as sb:
        sb.config({"version": 1, "routes": [
            {"event": "UserPromptSubmit", "gates": ["fixture_block"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        bom = b"\xef\xbb\xbf" + json.dumps({"hook_event_name": "UserPromptSubmit"}).encode("utf-8")
        check("rt_bom_parsed", sb.run(bom)["decision"] == "block")
        check("rt_garbage_allow", sb.run(b"not json")["decision"] == "allow")
        check("rt_nondict_allow", sb.run(b"[1, 2]")["decision"] == "allow")
        check("rt_unknown_args", sb.run({"hook_event_name": "Other"},
                                        args=("--weird", "x"))["decision"] == "allow")


def test_config_failclosed():
    with Sandbox() as sb:
        check("rt_missing_config",
              sb.run({"hook_event_name": "Stop"})["decision"] == "block")
        sb.config("{broken")
        check("rt_broken_config",
              sb.run({"hook_event_name": "Stop"})["decision"] == "block")


def test_routing():
    with Sandbox() as sb:
        sb.config({"version": 1, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^(WriteFile|Edit)$",
             "gates": ["fixture_block"]},
            {"event": "SubagentStart", "agent_pattern": "^(code-mapping|documentation)$",
             "gates": ["fixture_block"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        check("rt_tool_match", sb.run({"hook_event_name": "PreToolUse",
                                       "tool_name": "Edit"})["decision"] == "block")
        check("rt_tool_anchored", sb.run({"hook_event_name": "PreToolUse",
                                          "tool_name": "MyEdit"})["decision"] == "allow")
        check("rt_agent_match", sb.run({"hook_event_name": "SubagentStart",
                                        "agent_type": "documentation"})["decision"] == "block")
        check("rt_agent_missing_skips",
              sb.run({"hook_event_name": "SubagentStart"})["decision"] == "allow")


def test_gate_failures():
    with Sandbox() as sb:
        sb.config({"version": 1, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^Bash$",
             "gates": ["fixture_crash"], "safety_critical": True},
            {"event": "PostToolUse", "gates": ["fixture_crash"]},
            {"event": "Notification", "gates": ["fixture_bad"]}]})
        sb.gate("fixture_crash", CRASH_GATE)
        sb.gate("fixture_bad", BAD_GATE)
        check("rt_critical_crash_blocks",
              sb.run({"hook_event_name": "PreToolUse", "tool_name": "Bash"})["decision"] == "block")
        check("rt_noncritical_crash_allows",
              sb.run({"hook_event_name": "PostToolUse", "tool_name": "Edit"})["decision"] == "allow")
        check("rt_bad_result_allows",
              sb.run({"hook_event_name": "Notification"})["decision"] == "allow")


def test_stop_budget():
    with Sandbox() as sb:
        sb.config({"version": 1, "stop_block_budget": 1, "routes": [
            {"event": "Stop", "gates": ["fixture_block"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        ev = {"hook_event_name": "Stop", "session_id": "s1"}
        check("rt_stop_first_blocks", sb.run(ev)["decision"] == "block")
        degraded = sb.run(ev)
        check("rt_stop_degrades", degraded["decision"] == "allow"
              and "systemMessage" in degraded, repr(degraded))
        sb.gate("fixture_block", ALLOW_GATE)
        check("rt_stop_allow_resets", sb.run(ev)["decision"] == "allow")
        sb.gate("fixture_block", BLOCK_GATE)
        check("rt_stop_counts_again", sb.run(ev)["decision"] == "block")


def test_real_config():
    # No size checks: the 10k-character limit applies to agent .md files only,
    # not to Python scripts (user decision 2026-06-11).
    config_path = os.path.join(HOOKS_SRC, "router.config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        for route in config.get("routes", []):
            for gate in route.get("gates", []):
                check(f"rt_gate_exists:{gate}",
                      os.path.exists(os.path.join(HOOKS_SRC, "gates", gate + ".py")))
    else:
        print("skip: router.config.json not wired yet")


def main():
    test_stdin_safety()
    test_config_failclosed()
    test_routing()
    test_gate_failures()
    test_stop_budget()
    test_real_config()
    print(f"All {PASSED} router checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the suite** (from `modules/analytics/`):

```bash
python scripts/test_router.py
```

Expected: `skip: router.config.json not wired yet` line (config arrives in Task 10), every `ok:` line, final `All N router checks passed`.

- [ ] **Step 3: Commit**

```bash
git add modules/analytics/scripts/test_router.py
git commit -m "Add analytics router test suite"
```

---

### Task 3: git_guard copy + bootstrap-rule adaptation

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/git_guard.py`
- Create: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Write the failing test suite harness with git_guard checks:**

```python
#!/usr/bin/env python3
"""Offline unit tests for analytics quality gates. Run from modules/analytics:
    python scripts/test_gates.py
Gates load in-process; fixtures live in temp dirs via GIGACODE_ROOT."""
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

GOOD_TECHDOC = ("= Обзор фичи\n:feature: card-blocking\n:run-date: 2026-06-11\n"
                ":code-commit: abc1234\n\nПоведение подтверждено. Источник: код.\n")
GOOD_FINAL_ADOC = "= Кейс блокировки карты\n\nОсновной сценарий использования.\n"


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
    tmp = tempfile.mkdtemp(prefix="agates-")
    os.makedirs(os.path.join(tmp, "rules"))
    shutil.copy(os.path.join(ROOT, "rules", "reverse-analysis.md"),
                os.path.join(tmp, "rules"))
    os.makedirs(os.path.join(tmp, ".gigacode", "logs"))
    os.makedirs(os.path.join(tmp, "openspec", "specs"))
    os.makedirs(os.path.join(tmp, "docs", "features"))
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


def write_file(root_dir, rel, text):
    path = os.path.join(root_dir, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def write_qg(root_dir, config):
    write_file(root_dir, ".gigacode/quality-gates.json", json.dumps(config))


def file_event(path):
    return {"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
            "tool_input": {"file_path": path}}


def test_git_guard():
    gate = load_gate("git_guard")
    check("gg_reset_hard",
          gate.run({"tool_input": {"command": "git reset --hard"}})["decision"] == "block")
    check("gg_shell_specs",
          gate.run({"tool_input": {"command": "echo x > openspec/specs/cap/spec.md"}})["decision"] == "block")
    check("gg_shell_archive",
          gate.run({"tool_input": {"command": "cp a.md openspec/changes/archive/a.md"}})["decision"] == "block")
    check("gg_file_specs_allowed",
          gate.run({"tool_input": {"file_path": "openspec/specs/cap/spec.md"}})["decision"] == "allow")
    check("gg_file_gigacode",
          gate.run({"tool_input": {"file_path": ".gigacode/hooks/router.py"}})["decision"] == "block")
    check("gg_env_ask",
          gate.run({"tool_input": {"file_path": ".env"}})["decision"] == "ask")
    check("gg_benign",
          gate.run({"tool_input": {"command": "git status"}})["decision"] == "allow")


def main():
    test_git_guard()
    print(f"All {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run to verify it fails** (from `modules/analytics/`):

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/git_guard.py`.

- [ ] **Step 3: Copy git_guard and apply the bootstrap diff.** Copy verbatim (worktree root):

```bash
git show feature/dev-flow-enforcement:.gigacode/hooks/gates/git_guard.py > modules/analytics/.gigacode/hooks/gates/git_guard.py
```

Then apply exactly three edits. The dev-flow version blocks every write under `openspec/specs/`; in analytics, file-tool writes there are governed by `gate_spec_bootstrap` (create-once rule), while shell redirects stay blocked so they cannot bypass that gate.

Edit 1 — replace the regex line:

```python
# old
OPENSPEC_TRUTH_RE=re.compile(r"(^|/)openspec/(specs|changes/archive)/",re.IGNORECASE)
# new
OPENSPEC_ARCHIVE_RE=re.compile(r"(^|/)openspec/changes/archive/",re.IGNORECASE)
OPENSPEC_SPECS_RE=re.compile(r"(^|/)openspec/specs/",re.IGNORECASE)
```

Edit 2 — replace `classify_path`:

```python
# old
def classify_path(path):
    p=_norm(path)
    if any(fnmatch.fnmatch(p,pat) or p==pat.rstrip("/*") for pat in SELF_PROTECT): return "block"
    if OPENSPEC_TRUTH_RE.search(p): return "block"
    if any(fnmatch.fnmatch(p,pat) for pat in PROTECTED_PATHS): return "ask"
    return ""
# new
def classify_path(path,shell=False):
    p=_norm(path)
    if any(fnmatch.fnmatch(p,pat) or p==pat.rstrip("/*") for pat in SELF_PROTECT): return "block"
    if OPENSPEC_ARCHIVE_RE.search(p): return "block"
    if shell and OPENSPEC_SPECS_RE.search(p): return "block"
    if any(fnmatch.fnmatch(p,pat) for pat in PROTECTED_PATHS): return "ask"
    return ""
```

Edit 3 — in `inspect_command`, change the call site:

```python
# old
            c=classify_path(tgt)
# new
            c=classify_path(tgt,shell=True)
```

- [ ] **Step 4: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed` (the suite prints the count; do not pin it).

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/git_guard.py modules/analytics/scripts/test_gates.py
git commit -m "Adapt git_guard for analytics spec bootstrap rule"
```

---

### Task 4: Context-inject gate

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/gate_context_inject.py`
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Add the failing tests.** Insert above `main()` and add `test_context_inject()` to `main()` after `test_git_guard()`:

```python
def test_context_inject():
    gate = load_gate("gate_context_inject")
    with fixture_root() as tmp:
        result = gate.run({"hook_event_name": "SessionStart"})
        ctx = result.get("additionalContext", "")
        check("ci_session_rules", "reverse-analysis" in ctx, ctx[:200])
        check("ci_session_caps_none", "none" in ctx, ctx[-200:])
        os.makedirs(os.path.join(tmp, "openspec", "specs", "cap-a"))
        ctx2 = gate.run({"hook_event_name": "SessionStart"}).get("additionalContext", "")
        check("ci_session_caps_listed", "cap-a" in ctx2, ctx2[-200:])
        sub = gate.run({"hook_event_name": "SubagentStart", "agent_type": "documentation"})
        check("ci_subagent_search", "find_symbol" in sub.get("additionalContext", ""))
        cmd = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "/reverse-analysis card"})
        check("ci_command_bootstrap", "bootstrap" in cmd.get("additionalContext", "").lower())
        other = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "привет"})
        check("ci_other_prompt_silent", "additionalContext" not in other)
```

- [ ] **Step 2: Run to verify it fails**

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/gate_context_inject.py`.

- [ ] **Step 3: Write the gate** (`gate_context_inject.py`, full file — adapted from dev-flow: analytics rules, bootstrapped-capabilities line instead of active changes, search-before-claim wording, `/reverse-analysis` command hint):

```python
#!/usr/bin/env python3
"""Advisory gate: inject rules, the module map and bootstrapped capabilities.

Primary enforcement mechanism: ground the agent before generation. Never blocks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

RULE_FILES = ["reverse-analysis.md", "openspec.md"]
MODULE_MAP = os.path.join(".gigacode", "context", "module-map.md")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def bootstrapped_capabilities():
    specs_dir = os.path.join(_lib.root(), "openspec", "specs")
    try:
        return sorted(
            name for name in os.listdir(specs_dir)
            if os.path.isdir(os.path.join(specs_dir, name))
        )
    except OSError:
        return []


def specs_line():
    caps = bootstrapped_capabilities()
    return ("Bootstrapped capabilities (openspec/specs): "
            + (", ".join(caps) if caps else "none") + ".")


def run(event):
    name = str(event.get("hook_event_name", ""))
    if name == "SessionStart":
        parts = [read_text(os.path.join(_lib.root(), "rules", rule)) for rule in RULE_FILES]
        parts.append(read_text(os.path.join(_lib.root(), MODULE_MAP)))
        parts.append(specs_line())
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "SubagentStart":
        parts = [
            "Перед любым утверждением о поведении кода: найди подтверждение "
            "(mcp__serena__find_symbol когда доступен, иначе rg / git grep) и "
            "зафиксируй путь и символ в docs/features/<feature>/journal.md.",
            read_text(os.path.join(_lib.root(), MODULE_MAP)),
            specs_line(),
        ]
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "UserPromptSubmit":
        # lstrip: a slash command preceded by accidental whitespace still counts
        prompt = str(event.get("prompt", "")).lstrip()
        if prompt.startswith("/reverse-analysis"):
            return {"decision": "allow", "additionalContext": specs_line() + (
                " Реверс-анализ — одноразовый bootstrap: ФТ пишутся в "
                "openspec/specs/<capability>/spec.md только для новой capability; "
                "существующие спеки меняются через OpenSpec change lifecycle.")}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Note: `rules/openspec.md` does not exist in the module until Phase 2; `read_text` returns `""` and the part is dropped — by design.

- [ ] **Step 4: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/gate_context_inject.py modules/analytics/scripts/test_gates.py
git commit -m "Add analytics context-inject gate"
```

---

### Task 5: Preflight gate (port of gen-1 hook)

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/preflight_check.py`
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Add the failing tests** (above `main()`; add `test_preflight()` to `main()`):

```python
def test_preflight():
    gate = load_gate("preflight_check")
    check("pf_unrelated",
          gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "hello"})["decision"] == "allow")
    check("pf_missing_feature",
          gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "сделай реверс-анализ"})["decision"] == "block")
    complete = "reverse-analysis feature Card Blocking jira ABC-123"
    check("pf_complete",
          gate.run({"hook_event_name": "UserPromptSubmit", "prompt": complete})["decision"] == "allow")
    check("pf_wrong_event",
          gate.run({"hook_event_name": "PreToolUse", "prompt": "реверс"})["decision"] == "allow")
    payload = b"\xef\xbb\xbf" + json.dumps(
        {"hook_event_name": "UserPromptSubmit", "prompt": "сделай реверс-анализ"}).encode("utf-8")
    proc = subprocess.run([sys.executable, os.path.join(GATES_DIR, "preflight_check.py")],
                          input=payload, stdout=subprocess.PIPE, timeout=60)
    data = json.loads(proc.stdout.decode("utf-8"))
    check("pf_cli_bom", data["decision"] == "block", repr(data))
```

`pf_cli_bom` is the regression test for the gen-1 BOM bug: a BOM-prefixed event must still be parsed (the gen-1 hook silently answered `allow`).

- [ ] **Step 2: Run to verify it fails**

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/preflight_check.py`.

- [ ] **Step 3: Write the gate** (full file; markers ported from the gen-1 hook, stdin via `_lib.stdin_event`):

```python
#!/usr/bin/env python3
"""Preflight gate for reverse-analysis prompts (UserPromptSubmit)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

REVERSE_MARKERS = ("reverse-analysis", "reverse analysis", "reverse analyze",
                   "реверс", "обратн")
FEATURE_RES = (
    r"\bfeature\s+['\"]?[\w .:/-]+",
    r"\bfunction\s+['\"]?[\w .:/-]+",
    r"функци[ияю]\s+['\"]?[\w .:/-]+",
    r"фич[ауи]\s+['\"]?[\w .:/-]+",
)
CONTEXT_RES = (
    r"\bjira\b", r"\bconfluence\b", r"[A-Z][A-Z0-9]+-\d+",
    r"код[- ]?only", r"code[- ]?only", r"без\s+jira", r"без\s+confluence",
    r"только\s+код", r"without\s+jira", r"without\s+confluence",
)


def matches_any(patterns, text):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def run(event):
    if str(event.get("hook_event_name", "")) != "UserPromptSubmit":
        return {"decision": "allow"}
    prompt = str(event.get("prompt", "")).strip()
    if not any(marker in prompt.lower() for marker in REVERSE_MARKERS):
        return {"decision": "allow"}
    questions = []
    if not matches_any(FEATURE_RES, prompt):
        questions.append("Какую бизнес-фичу анализируем (укажи: feature/фича <название>)?")
    if not matches_any(CONTEXT_RES, prompt):
        questions.append("Есть ли Jira/Confluence-контекст (тикет, страница) или анализ только по коду?")
    if questions:
        return {"decision": "block",
                "reason": "Запрос на реверс-анализ неполон. " + " ".join(questions)}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/preflight_check.py modules/analytics/scripts/test_gates.py
git commit -m "Port analytics preflight as router gate"
```

---

### Task 6: Spec bootstrap gate

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/gate_spec_bootstrap.py`
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Add the failing tests** (above `main()`; add `test_spec_bootstrap()` to `main()`):

```python
def test_spec_bootstrap():
    gate = load_gate("gate_spec_bootstrap")
    with fixture_root() as tmp:
        ev = {"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
              "tool_input": {"file_path": "openspec/specs/new-cap/spec.md"}}
        check("sb_new_allow", gate.run(ev)["decision"] == "allow")
        write_file(tmp, "openspec/specs/new-cap/spec.md", "# Spec\n")
        check("sb_existing_block", gate.run(ev)["decision"] == "block")
        other = {"tool_input": {"file_path": "openspec/specs/notes.md"}}
        check("sb_other_block", gate.run(other)["decision"] == "block")
        fr = gate.run({"tool_input": {"file_path": "analytics/functional-requirements/Card.adoc"}})
        check("sb_fr_advisory", fr["decision"] == "allow" and "additionalContext" in fr, repr(fr))
        check("sb_unrelated", gate.run({"tool_input": {"file_path": "src/Main.kt"}})["decision"] == "allow")
```

- [ ] **Step 2: Run to verify it fails**

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/gate_spec_bootstrap.py`.

- [ ] **Step 3: Write the gate** (full file):

```python
#!/usr/bin/env python3
"""Bootstrap rule for openspec/specs: create once, change via lifecycle."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

SPEC_RE = re.compile(r"(^|/)openspec/specs/[^/]+/spec\.md$", re.IGNORECASE)
SPECS_DIR_RE = re.compile(r"(^|/)openspec/specs/", re.IGNORECASE)
FR_RE = re.compile(r"(^|/)analytics/functional-requirements/", re.IGNORECASE)


def _norm(path):
    p = path.replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def run(event):
    path = _norm(_lib.path_from_event(event))
    if not path:
        return {"decision": "allow"}
    match = SPEC_RE.search(path)
    if match:
        rel = path[match.start():].lstrip("/")
        target = os.path.join(_lib.root(), *rel.split("/"))
        if os.path.exists(target):
            return {"decision": "block", "reason": (
                f"Спека capability уже существует: {rel}. Bootstrap-правило: прямое "
                "создание разрешено один раз; изменения существующей спеки идут "
                "только через OpenSpec change lifecycle.")}
        return {"decision": "allow"}
    if SPECS_DIR_RE.search(path):
        return {"decision": "block", "reason": (
            "В openspec/specs/ допускается только создание "
            f"<capability>/spec.md; получено: {path}.")}
    if FR_RE.search(path):
        return {"decision": "allow", "additionalContext": (
            "Напоминание: analytics/functional-requirements/*.adoc — производная от "
            "openspec/specs/<capability>/spec.md. Спека пишется первой; не редактируй "
            "FR-документ в обход спеки.")}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/gate_spec_bootstrap.py modules/analytics/scripts/test_gates.py
git commit -m "Add spec bootstrap gate"
```

---

### Task 7: Techdocs gate

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/gate_techdocs.py`
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Add the failing tests** (above `main()`; add `test_techdocs()` to `main()`):

```python
def test_techdocs():
    gate = load_gate("gate_techdocs")
    with fixture_root() as tmp:
        rel = "docs/features/card-blocking/overview.adoc"
        write_file(tmp, rel, GOOD_TECHDOC)
        check("td_good", gate.run(file_event(rel))["decision"] == "allow")
        write_file(tmp, rel, "= Обзор\n\nБез атрибутов.\n")
        check("td_missing_attrs", gate.run(file_event(rel))["decision"] == "block")
        write_file(tmp, rel, GOOD_TECHDOC + "\n```code```\n")
        check("td_markdown", gate.run(file_event(rel))["decision"] == "block")
        write_file(tmp, rel, "= Overview\n:feature: x\n:run-date: d\n:code-commit: c\n\nEnglish only.\n")
        check("td_non_russian", gate.run(file_event(rel))["decision"] == "block")
        check("td_other_path",
              gate.run(file_event("docs/features/card-blocking/journal.md"))["decision"] == "allow")
```

- [ ] **Step 2: Run to verify it fails**

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/gate_techdocs.py`.

- [ ] **Step 3: Write the gate** (full file; PostToolUse — content is read back from disk, the source of truth after a write):

```python
#!/usr/bin/env python3
"""Technical-layer AsciiDoc checks for docs/features/ (PostToolUse)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

TECHDOC_RE = re.compile(r"(^|/)docs/features/[^/]+/[^/]+\.adoc$", re.IGNORECASE)
MD_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
REQUIRED_ATTRS = (":feature:", ":run-date:", ":code-commit:")


def run(event):
    path = _lib.path_from_event(event)
    match = TECHDOC_RE.search(path.replace("\\", "/"))
    if not match:
        return {"decision": "allow"}
    normalized = path.replace("\\", "/")
    idx = normalized.lower().find("docs/features/")
    rel = normalized[idx:]
    target = os.path.join(_lib.root(), *rel.split("/"))
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return {"decision": "allow"}  # nothing on disk yet — not this gate's failure
    issues = []
    if not text.lstrip("\ufeff\r\n\t ").startswith("="):
        issues.append("нет заголовка AsciiDoc (=)")
    for attr in REQUIRED_ATTRS:
        if attr not in text:
            issues.append(f"нет атрибута {attr}")
    if "```" in text:
        issues.append("Markdown fenced-блок (```)")
    if MD_HEADING_RE.search(text):
        issues.append("Markdown-заголовок (#)")
    if not CYRILLIC_RE.search(text):
        issues.append("документ должен быть на русском")
    if issues:
        return {"decision": "block",
                "reason": f"Технический документ {rel}: " + "; ".join(issues) + "."}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Metadata-header contract checked here (and documented for agents in Phase 2): every techdoc carries `:feature:`, `:run-date:`, `:code-commit:` attribute lines; links to final artifacts are appended at run close and are not required by the gate.

- [ ] **Step 4: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/gate_techdocs.py modules/analytics/scripts/test_gates.py
git commit -m "Add techdocs gate"
```

---

### Task 8: Final-format gate + quality-gates.json

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/gate_final_format.py`
- Create: `modules/analytics/.gigacode/quality-gates.json`
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Add the failing tests** (above `main()`; add `test_final_format()` to `main()`):

```python
def test_final_format():
    gate = load_gate("gate_final_format")
    with fixture_root() as tmp:
        rel = "analytics/use-case/CardBlocking.adoc"
        write_file(tmp, rel, GOOD_FINAL_ADOC)
        check("ff_good_adoc", gate.run(file_event(rel))["decision"] == "allow")
        bad = "analytics/use-case/cardBlocking.adoc"
        write_file(tmp, bad, GOOD_FINAL_ADOC)
        check("ff_lower_name", gate.run(file_event(bad))["decision"] == "block")
        check("ff_puml_misplaced",
              gate.run(file_event("analytics/use-case/Diagram.puml"))["decision"] == "block")
        write_file(tmp, "architecture/Context.puml", "@startuml\nA -> B\n@enduml\n")
        check("ff_puml_ok", gate.run(file_event("architecture/Context.puml"))["decision"] == "allow")
        write_file(tmp, "architecture/Broken.puml", "@startuml\nA -> B\n")
        check("ff_puml_tags", gate.run(file_event("architecture/Broken.puml"))["decision"] == "block")
        check("ff_sql_misplaced",
              gate.run(file_event("analytics/db/data-model/Init.sql"))["decision"] == "block")
        write_file(tmp, "analytics/db/data-model/Model.dbml", "Table users { id int }\n")
        check("ff_dbml_ok",
              gate.run(file_event("analytics/db/data-model/Model.dbml"))["decision"] == "allow")
        write_file(tmp, "analytics/api/event/CardEvent.json", "{broken")
        check("ff_bad_json",
              gate.run(file_event("analytics/api/event/CardEvent.json"))["decision"] == "block")
        check("ff_gitkeep",
              gate.run(file_event("analytics/use-case/.gitkeep"))["decision"] == "allow")
        fail_script = write_file(tmp, "fail.py", "import sys\nsys.exit(1)\n")
        write_qg(tmp, {"final_validators": [
            {"name": "always-fail", "command": f'python "{fail_script}"',
             "applies_to": ["analytics/use-case/**"], "timeout": 30}]})
        check("ff_validator_fail", gate.run(file_event(rel))["decision"] == "block")
        write_qg(tmp, {"final_validators": [
            {"name": "ghost", "command": "no-such-binary-xyz",
             "applies_to": ["analytics/**"], "timeout": 5}]})
        check("ff_validator_missing", gate.run(file_event(rel))["decision"] == "allow")
        write_qg(tmp, {"final_validators": [
            {"name": "off", "command": "", "applies_to": ["**"]}]})
        check("ff_validator_unconfigured", gate.run(file_event(rel))["decision"] == "allow")
```

- [ ] **Step 2: Run to verify it fails**

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/gate_final_format.py`.

- [ ] **Step 3: Write the gate** (full file):

```python
#!/usr/bin/env python3
"""Format and placement gate for the final documentation tree (PostToolUse)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

TREE_RE = re.compile(r"(^|/)(analytics|architecture)/", re.IGNORECASE)
UPPER_CAMEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*\.[a-z]+$")
KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DIR_EXCEPTIONS = {"nfr and contact"}
MD_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

YAML_DIRS = ("analytics/api/event/", "analytics/api/rest/public/",
             "analytics/api/rest/private/", "analytics/integration/event/",
             "analytics/integration/rest/")
PLACEMENT = {
    ".puml": ("architecture/",),
    ".adoc": ("analytics/functional-requirements/", "analytics/use-case/",
              "analytics/glossary/", "analytics/integration/mapping/",
              "analytics/integration/nfr and contact/",
              "analytics/api/mapping/", "analytics/api/nfr/"),
    ".yaml": YAML_DIRS,
    ".yml": YAML_DIRS,
    ".json": ("analytics/api/event/", "analytics/integration/event/"),
    ".dbml": ("analytics/db/data-model/",),
    ".sql": ("analytics/db/ddl/", "analytics/db/dml/"),
}


def rel_tree_path(path):
    p = path.replace("\\", "/")
    match = TREE_RE.search(p)
    return p[match.start():].lstrip("/") if match else ""


def read_target(rel):
    target = os.path.join(_lib.root(), *rel.split("/"))
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            return target, handle.read()
    except OSError:
        return target, None


def structure_issues(rel):
    issues = []
    segments = rel.split("/")
    name = segments[-1]
    for segment in segments[:-1]:
        if not (KEBAB_RE.match(segment) or segment in DIR_EXCEPTIONS):
            issues.append(f"каталог не в kebab-case: {segment!r}")
    ext = os.path.splitext(name)[1].lower()
    allowed = PLACEMENT.get(ext)
    if allowed is None:
        issues.append(f"неожиданный тип файла: {name}")
        return issues
    if not any(rel.startswith(prefix) for prefix in allowed):
        issues.append(f"{name}: файл {ext} не размещается в {os.path.dirname(rel)}/")
    if ext in (".adoc", ".puml") and not UPPER_CAMEL_RE.match(name):
        issues.append(f"имя не UpperCamelCase: {name}")
    return issues


def content_issues(rel, text):
    if text is None:
        return []
    ext = os.path.splitext(rel)[1].lower()
    issues = []
    if ext == ".puml":
        if "@startuml" not in text or "@enduml" not in text:
            issues.append("нет пары @startuml/@enduml")
    elif ext == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append(f"невалидный JSON: {exc}")
    elif ext == ".adoc":
        if not text.lstrip("\ufeff\r\n\t ").startswith("="):
            issues.append("нет заголовка AsciiDoc (=)")
        if "```" in text or MD_HEADING_RE.search(text):
            issues.append("Markdown-синтаксис в AsciiDoc")
        if not CYRILLIC_RE.search(text):
            issues.append("документ должен быть на русском")
    return issues


def validator_issues(rel, target):
    issues = []
    config = _lib.load_quality_gates()
    for spec in config.get("final_validators", []):
        if not isinstance(spec, dict):
            continue
        command = str(spec.get("command", "")).strip()
        if not command:
            continue  # unconfigured = silent allow
        globs = spec.get("applies_to", [])
        if globs and not _lib.matches_globs(rel, globs):
            continue
        try:
            timeout = max(1, int(spec.get("timeout", 60)))
        except (TypeError, ValueError):
            timeout = 60
        rc, tail = _lib.run_command(command, timeout, [target])
        name = str(spec.get("name", "validator"))
        if rc == -1:
            _lib.journal_skip("gate_final_format", f"{name}: {tail}")
        elif rc == -2:
            _lib.journal_skip("gate_final_format", f"{name} timed out")
        elif rc != 0:
            issues.append(f"{name} (rc={rc}): {tail}")
    return issues


def run(event):
    rel = rel_tree_path(_lib.path_from_event(event))
    if not rel or rel.endswith(".gitkeep"):
        return {"decision": "allow"}
    issues = structure_issues(rel)
    target, text = read_target(rel)
    issues.extend(content_issues(rel, text))
    if not issues:
        issues.extend(validator_issues(rel, target))
    if issues:
        return {"decision": "block",
                "reason": f"Финальный артефакт {rel}: " + "; ".join(issues)}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `modules/analytics/.gigacode/quality-gates.json`** (validators ship unconfigured — silent allow until the team wires real commands; `openspec_validate` ships configured and degrades to skip-with-record when the CLI is absent):

```json
{
  "final_validators": [
    {
      "name": "openapi-rest",
      "command": "",
      "applies_to": ["analytics/api/rest/**/*.yaml", "analytics/api/rest/**/*.yml", "analytics/integration/rest/**/*.yaml", "analytics/integration/rest/**/*.yml"],
      "timeout": 60
    },
    {
      "name": "asyncapi-event",
      "command": "",
      "applies_to": ["analytics/api/event/**/*.yaml", "analytics/api/event/**/*.yml", "analytics/integration/event/**/*.yaml", "analytics/integration/event/**/*.yml"],
      "timeout": 60
    },
    {
      "name": "plantuml",
      "command": "",
      "applies_to": ["architecture/**/*.puml"],
      "timeout": 60
    }
  ],
  "openspec_validate": {
    "command": "openspec validate --specs --strict",
    "timeout": 120
  }
}
```

- [ ] **Step 5: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed`.

- [ ] **Step 6: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/gate_final_format.py modules/analytics/.gigacode/quality-gates.json modules/analytics/scripts/test_gates.py
git commit -m "Add final-format gate and quality-gates config"
```

---

### Task 9: Run-output Stop gate

**Files:**
- Create: `modules/analytics/.gigacode/hooks/gates/validate_run_output.py`
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Add the failing tests** (above `main()`; add `test_validate_run_output()` to `main()`):

```python
def manifest(status, **extra):
    data = {"feature": "card-blocking", "run_date": "2026-06-11",
            "code_commit": "abc1234", "status": status,
            "capability": "card-blocking",
            "produced": {"technical": [], "spec": "", "final": []}}
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)


def write_techdocs(tmp):
    for doc in ("overview", "flow", "integrations", "data", "questions"):
        write_file(tmp, f"docs/features/card-blocking/{doc}.adoc", GOOD_TECHDOC)


def test_validate_run_output():
    gate = load_gate("validate_run_output")
    with fixture_root() as tmp:
        check("vr_no_runs", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", manifest("scoping"))
        check("vr_scoping", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", manifest("draft"))
        check("vr_draft_missing", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_techdocs(tmp)
        check("vr_draft_ready", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", manifest("confirmed"))
        check("vr_confirmed_no_spec", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_file(tmp, "openspec/specs/card-blocking/spec.md", "## Requirements\n")
        check("vr_confirmed_ok", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": ["analytics/use-case/CardBlocking.adoc"]}))
        check("vr_complete_missing_final",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_file(tmp, "analytics/use-case/CardBlocking.adoc", GOOD_FINAL_ADOC)
        check("vr_complete_ok", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", "{broken")
        check("vr_bad_manifest", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
```

- [ ] **Step 2: Run to verify it fails**

```bash
python scripts/test_gates.py
```

Expected: FAIL — `FileNotFoundError` for `gates/validate_run_output.py`.

- [ ] **Step 3: Write the gate** (full file; replaces gen-1 `last_assistant_message` sniffing with manifest + repo state; Stop budget in the router caps repeated blocks):

```python
#!/usr/bin/env python3
"""Stop gate: validate reverse-analysis run state from manifests + repo files."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

REQUIRED_TECHDOCS = ("overview.adoc", "flow.adoc", "integrations.adoc",
                     "data.adoc", "questions.adoc")
STATUSES = ("scoping", "draft", "confirmed", "complete")


def load_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def missing_files(root_dir, paths):
    missing = []
    for rel in paths:
        if not isinstance(rel, str) or not rel:
            continue
        if not os.path.exists(os.path.join(root_dir, *rel.replace("\\", "/").split("/"))):
            missing.append(rel)
    return missing


def check_feature(root_dir, feature_dir, manifest):
    name = os.path.basename(feature_dir)
    status = manifest.get("status", "")
    if status not in STATUSES:
        return [f"{name}: некорректный status {status!r} в manifest.json"]
    if status == "scoping":
        return []
    issues = []
    for doc in REQUIRED_TECHDOCS:
        if not os.path.exists(os.path.join(feature_dir, doc)):
            issues.append(f"{name}: отсутствует {doc}")
    if status in ("confirmed", "complete"):
        capability = str(manifest.get("capability", "")) or name
        spec_rel = f"openspec/specs/{capability}/spec.md"
        if not os.path.exists(os.path.join(root_dir, *spec_rel.split("/"))):
            issues.append(f"{name}: нет {spec_rel}")
    if status == "complete":
        produced = manifest.get("produced", {})
        if not isinstance(produced, dict):
            produced = {}
        for group in ("technical", "final"):
            for rel in missing_files(root_dir, produced.get(group, []) or []):
                issues.append(f"{name}: заявленный файл отсутствует: {rel}")
    return issues


def openspec_issue():
    config = _lib.load_quality_gates().get("openspec_validate", {})
    command = str(config.get("command", "")).strip() if isinstance(config, dict) else ""
    if not command:
        return ""
    try:
        timeout = max(1, int(config.get("timeout", 120)))
    except (TypeError, ValueError):
        timeout = 120
    rc, tail = _lib.run_command(command, timeout)
    if rc == -1:
        _lib.journal_skip("validate_run_output", f"openspec CLI unavailable: {tail}")
        return ""
    if rc == -2:
        _lib.journal_skip("validate_run_output", "openspec validate timed out")
        return ""
    return f"openspec validate failed: {tail}" if rc != 0 else ""


def run(event):
    root_dir = _lib.root()
    features_dir = os.path.join(root_dir, "docs", "features")
    issues = []
    needs_spec_check = False
    try:
        entries = sorted(os.listdir(features_dir))
    except OSError:
        entries = []
    for entry in entries:
        feature_dir = os.path.join(features_dir, entry)
        manifest_path = os.path.join(feature_dir, "manifest.json")
        if not os.path.isdir(feature_dir) or not os.path.exists(manifest_path):
            continue
        manifest = load_manifest(manifest_path)
        if manifest is None:
            issues.append(f"{entry}: manifest.json не читается или не объект")
            continue
        if manifest.get("status") in ("confirmed", "complete"):
            needs_spec_check = True
        issues.extend(check_feature(root_dir, feature_dir, manifest))
    if needs_spec_check and not issues:
        problem = openspec_issue()
        if problem:
            issues.append(problem)
    if issues:
        return {"decision": "block",
                "reason": "Прогон реверс-анализа не завершён: " + "; ".join(issues)}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the suite to verify it passes**

```bash
python scripts/test_gates.py
```

Expected: every `ok:` line, final `All <N> gate checks passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/.gigacode/hooks/gates/validate_run_output.py modules/analytics/scripts/test_gates.py
git commit -m "Add run-output Stop gate"
```

---

### Task 10: Wire the router — config, settings, remove gen-1 hooks, smoke checks

**Files:**
- Create: `modules/analytics/.gigacode/hooks/router.config.json`
- Modify: `modules/analytics/.gigacode/settings.json` (full replace)
- Delete: `modules/analytics/.gigacode/hooks/preflight_check.py`
- Delete: `modules/analytics/.gigacode/hooks/validate_output.py`
- Modify: `modules/analytics/scripts/smoke-check.sh` (full replace)
- Modify: `modules/analytics/scripts/smoke-check.ps1` (full replace)

- [ ] **Step 1: Create `router.config.json`** (routes from the design's Decision 7):

```json
{
  "version": 1,
  "stop_block_budget": 2,
  "routes": [
    {
      "event": "UserPromptSubmit",
      "gates": ["preflight_check", "gate_context_inject"]
    },
    {
      "event": "SessionStart",
      "gates": ["gate_context_inject"]
    },
    {
      "event": "SubagentStart",
      "agent_pattern": "^(code-mapping|documentation)$",
      "gates": ["gate_context_inject"]
    },
    {
      "event": "PreToolUse",
      "tool_pattern": "^(Bash|Shell)$",
      "gates": ["git_guard"],
      "safety_critical": true
    },
    {
      "event": "PreToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["git_guard"],
      "safety_critical": true
    },
    {
      "event": "PreToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["gate_spec_bootstrap"],
      "safety_critical": true
    },
    {
      "event": "PostToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["gate_techdocs", "gate_final_format"]
    },
    {
      "event": "Stop",
      "gates": ["validate_run_output"]
    }
  ]
}
```

- [ ] **Step 2: Replace `settings.json` entirely** (router wiring; `repomix` permission removed; `Edit` allowlist extended to the new output roots; tool-name matchers follow Qwen Code docs pending a `hook_probe.py` run against a real GigaCode build):

```json
{
  "ui": {
    "showCitations": true,
    "showLineNumbers": true,
    "hideTips": true,
    "shellOutputMaxLines": 20
  },
  "permissions": {
    "allow": [
      "Read",
      "Bash(git status*)",
      "Bash(git branch*)",
      "Bash(git diff*)",
      "Bash(git log*)",
      "Bash(rg *)",
      "Bash(graphify*)",
      "Bash(python .gigacode/hooks/*)",
      "Bash(python scripts/*)",
      "Edit(docs/features/**)",
      "Edit(openspec/specs/**)",
      "Edit(analytics/**)",
      "Edit(architecture/**)"
    ],
    "ask": [
      "Edit",
      "Bash(git add*)",
      "Bash(git commit*)"
    ],
    "deny": [
      "Read(.env)",
      "Read(.env.*)",
      "Bash(rm -rf *)",
      "Bash(del /s *)",
      "Bash(format *)"
    ]
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=UserPromptSubmit"}
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=SessionStart"}
        ]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "code-mapping|documentation",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=SubagentStart"}
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "^(Bash|Shell|WriteFile|Edit)$",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=PreToolUse"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "^(WriteFile|Edit)$",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=PostToolUse"}
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=Stop"}
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Delete the gen-1 hooks**

```bash
git rm modules/analytics/.gigacode/hooks/preflight_check.py modules/analytics/.gigacode/hooks/validate_output.py
```

- [ ] **Step 4: Replace `scripts/smoke-check.sh` entirely:**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

required=(
  ".gigacode/settings.json"
  ".gigacode/quality-gates.json"
  ".gigacode/skills/reverse-analysis/SKILL.md"
  ".gigacode/commands/reverse-analysis.md"
  ".gigacode/hooks/router.py"
  ".gigacode/hooks/router.config.json"
  ".gigacode/hooks/hook_probe.py"
  ".gigacode/hooks/gates/_lib.py"
  ".gigacode/hooks/gates/git_guard.py"
  ".gigacode/hooks/gates/gate_context_inject.py"
  ".gigacode/hooks/gates/preflight_check.py"
  ".gigacode/hooks/gates/gate_spec_bootstrap.py"
  ".gigacode/hooks/gates/gate_techdocs.py"
  ".gigacode/hooks/gates/gate_final_format.py"
  ".gigacode/hooks/gates/validate_run_output.py"
  "docs/templates/feature-analysis.adoc"
  "rules/reverse-analysis.md"
  "rules/branch-naming.md"
  "README.md"
)

for path in "${required[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
done

python -m json.tool .gigacode/settings.json >/dev/null
python -m json.tool .gigacode/hooks/router.config.json >/dev/null
python -m json.tool .gigacode/quality-gates.json >/dev/null

agent_count="$(find .gigacode/agents -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"
if [[ "$agent_count" != "5" ]]; then
  echo "Expected 5 agent files, found $agent_count" >&2
  exit 1
fi

for agent in .gigacode/agents/*.md; do
  chars="$(wc -m < "$agent" | tr -d ' ')"
  if [[ "$chars" -ge 10000 ]]; then
    echo "Agent file exceeds 10,000 characters: $agent" >&2
    exit 1
  fi
  boundaries="$(grep -c '^---$' "$agent")"
  if [[ "$boundaries" -lt 2 ]]; then
    echo "Agent file missing YAML frontmatter boundaries: $agent" >&2
    exit 1
  fi
done

decision="$(
  printf '%s' '{"hook_event_name":"SessionStart"}' |
    python .gigacode/hooks/router.py --event=SessionStart |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected SessionStart routing to allow, got $decision" >&2
  exit 1
fi

decision="$(
  printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"reverse-analysis missing info"}' |
    python .gigacode/hooks/router.py --event=UserPromptSubmit |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "block" ]]; then
  echo "Expected incomplete reverse-analysis prompt to block, got $decision" >&2
  exit 1
fi

if ! grep -q '^=' docs/templates/feature-analysis.adoc; then
  echo "AsciiDoc template must contain a document title" >&2
  exit 1
fi

python scripts/test_router.py
python scripts/test_gates.py

echo "Analytics module smoke check passed."
```

- [ ] **Step 5: Replace `scripts/smoke-check.ps1` entirely:**

```powershell
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$required = @(
  ".gigacode/settings.json",
  ".gigacode/quality-gates.json",
  ".gigacode/skills/reverse-analysis/SKILL.md",
  ".gigacode/commands/reverse-analysis.md",
  ".gigacode/hooks/router.py",
  ".gigacode/hooks/router.config.json",
  ".gigacode/hooks/hook_probe.py",
  ".gigacode/hooks/gates/_lib.py",
  ".gigacode/hooks/gates/git_guard.py",
  ".gigacode/hooks/gates/gate_context_inject.py",
  ".gigacode/hooks/gates/preflight_check.py",
  ".gigacode/hooks/gates/gate_spec_bootstrap.py",
  ".gigacode/hooks/gates/gate_techdocs.py",
  ".gigacode/hooks/gates/gate_final_format.py",
  ".gigacode/hooks/gates/validate_run_output.py",
  "docs/templates/feature-analysis.adoc",
  "rules/reverse-analysis.md",
  "rules/branch-naming.md",
  "README.md"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
}

foreach ($jsonFile in @(".gigacode/settings.json", ".gigacode/hooks/router.config.json", ".gigacode/quality-gates.json")) {
  Get-Content $jsonFile -Raw | ConvertFrom-Json | Out-Null
}

$agents = Get-ChildItem ".gigacode/agents/*.md"
if ($agents.Count -ne 5) {
  throw "Expected 5 agent files, found $($agents.Count)"
}

foreach ($agent in $agents) {
  $text = Get-Content $agent.FullName -Raw
  if ($text.Length -ge 10000) {
    throw "Agent file exceeds 10,000 characters: $($agent.Name)"
  }
  if (($text -split "`n" | Select-String -Pattern "^---$").Count -lt 2) {
    throw "Agent file missing YAML frontmatter boundaries: $($agent.Name)"
  }
}

$session = '{"hook_event_name":"SessionStart"}' | python .gigacode/hooks/router.py --event=SessionStart | ConvertFrom-Json
if ($session.decision -ne "allow") {
  throw "Expected SessionStart routing to allow, got $($session.decision)"
}

$incomplete = '{"hook_event_name":"UserPromptSubmit","prompt":"reverse-analysis missing info"}' | python .gigacode/hooks/router.py --event=UserPromptSubmit | ConvertFrom-Json
if ($incomplete.decision -ne "block") {
  throw "Expected incomplete reverse-analysis prompt to block, got $($incomplete.decision)"
}

$template = Get-Content "docs/templates/feature-analysis.adoc" -Raw
if (-not $template.TrimStart().StartsWith("=")) {
  throw "AsciiDoc template must start with a document title"
}

python scripts/test_router.py
if ($LASTEXITCODE -ne 0) { throw "test_router.py failed" }
python scripts/test_gates.py
if ($LASTEXITCODE -ne 0) { throw "test_gates.py failed" }

Write-Host "Analytics module smoke check passed."
```

Note: the PowerShell pipes to `python` are deliberate — PowerShell 5.1 piping is exactly the path that produced the gen-1 BOM bug, so the ps1 smoke run doubles as a BOM regression check at the wiring level. The incomplete-prompt sample is ASCII-only so PS 5.1 pipe encoding cannot mangle the marker.

- [ ] **Step 6: Run both smoke checks** (from `modules/analytics/`):

```bash
sh scripts/smoke-check.sh
```

```powershell
powershell -File scripts/smoke-check.ps1
```

Expected: both end with `Analytics module smoke check passed.`; `test_router.py` now also validates the real `router.config.json` (every referenced gate exists) instead of printing the skip line.

- [ ] **Step 7: Commit**

```bash
git add modules/analytics/.gigacode/hooks/router.config.json modules/analytics/.gigacode/settings.json modules/analytics/scripts/smoke-check.sh modules/analytics/scripts/smoke-check.ps1
git commit -m "Wire analytics hooks through the router and rewire smoke checks"
```

---

## Verification (end of phase)

From `modules/analytics/`:

1. `sh scripts/smoke-check.sh` → `Analytics module smoke check passed.`
2. `powershell -File scripts/smoke-check.ps1` → `Analytics module smoke check passed.`
3. `python scripts/test_router.py` → `All N router checks passed` with `rt_gate_exists:*` checks present (config wired).
4. `python scripts/test_gates.py` → `All <N> gate checks passed`.
5. `git -C ../.. log --oneline feature/analytics-template..HEAD` shows the 10 task commits (run from `modules/analytics/`; adjust if cwd differs).

## Out of Scope (Phase 2 plan)

Skill/command rewrite (manifest lifecycle, 9-step pipeline), 5 → 3 agents, `rules/openspec.md` + `rules/development-flow`-style updates, journal.md template, final-tree `.gitkeep` skeleton, `openspec/config.yaml`, Serena in `settings.json` + serena-hooks, graphify `build_module_map.py` + `module-map` smoke wiring, Context7 README snippet, README rewrite, removal of repomix mentions from agents/rules text.
