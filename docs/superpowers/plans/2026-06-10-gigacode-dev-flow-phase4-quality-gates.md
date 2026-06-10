# GigaCode Dev-Flow Phase 4: Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the six Phase 4 quality gates (`gate_context_inject`, `gate_spec_structure`, `gate_lint`, `gate_build`, `gate_clean_code`, `gate_existing_code`) behind the existing hook router, configured through `.gigacode/quality-gates.json`, fully covered by offline tests.

**Architecture:** Each gate is a standalone Python file under `.gigacode/hooks/gates/` exposing `run(event) -> dict` (decisions: `allow`/`ask`/`block`, optional `reason`/`additionalContext`) plus a stdin CLI wrapper — same contract as the Phase 3 gates. Shared helpers live in `gates/_lib.py`. The router gets two small config-driven extensions (`agent_pattern` matching, canonical `hook_event_name` injection). Context injection is the primary mechanism; only deterministic checks (`openspec validate`, lint, build) block; heuristics (`clean_code`, `existing_code`) are advisory-only and never deny.

**Tech Stack:** Python 3 stdlib only (no pip deps), openspec CLI 1.4.1 (optional at runtime — skip-with-record when absent), `rg` with `git grep` fallback for symbol search.

**Working directory:** `F:/Coding/gigacode_agents/.worktrees/dev-flow-enforcement` (branch `feature/dev-flow-enforcement`). NEVER use `git add -A` here — an untracked user file `docs/Текстовый документ.txt` must never be committed.

---

## Design decisions locked in this plan

1. **Search engine for `gate_existing_code`: `rg`, falling back to `git grep --no-pager`-style invocation, then skip-with-record.** Serena is an MCP server; querying it from a hook subprocess is not cheap or reliable. Serena stays the *agent-side* search tool (prompts already require it); the gate uses text search. The dev machine has no `rg` on PATH, so the `git grep` fallback is what tests exercise.
2. **`gate_build` and the Stop-time OpenSpec validation run only at "PR-readiness" moments** — when the last assistant message mentions `docs/development/` or `openspec/changes`. The Stop event fires at the end of *every* assistant turn; running a Gradle build each turn is unacceptable. `validate_development_output` already uses the same message-trigger pattern.
3. **Skip-with-record = a `{"kind": "skip", ...}` line in `.gigacode/logs/decisions.jsonl`.** `additionalContext` is added only for anomalies (a *configured* command that could not run, or an unavailable openspec CLI during an active change) so unconfigured repos are not spammed every turn.
4. **`gate_spec_structure` PostToolUse blocking is conditional on change completeness.** While the agent is still creating change artifacts (`proposal.md` written, `tasks.md` not yet), strict validation necessarily fails; blocking would thrash. Rule: validation failure **blocks** only when the change has `proposal.md` + `tasks.md` + at least one `specs/*/spec.md`; otherwise the failure is injected as advisory context. The Stop-time backstop validates all active changes strictly.
5. **`OPENSPEC_BIN` and `GIGACODE_ROOT` env overrides** exist so tests can simulate a missing CLI and point gates at fixture trees. `_lib.root()` resolves the template root from the gate file location (not cwd), overridable via `GIGACODE_ROOT`.
6. **Serena e2e verification (Kotlin LSP) is decoupled from this phase** — no gate depends on Serena. It remains a pre-rollout checklist item (install `uv` + `serena-agent`, run `find_symbol` against real Kotlin code).
7. **`lint` config accepts an object or an array of objects** so Kotlin and Java linters can run side by side (as promised in `docs/flow-overview.md` §7).

## Verified facts this plan relies on

- `openspec` 1.4.1 is installed in the dev env; `openspec validate --changes --strict --json --no-interactive` exits 0 on an empty `openspec/changes/` tree.
- `openspec validate <id> --type change --strict` is the per-change form (`--type change` required when names are ambiguous — Phase 1 finding).
- `rg` is NOT on PATH in the dev environment; `git` is.
- Router (`router.py`, committed `f2a46b0`) loads gates in-process via `importlib`, aggregates `block > ask > allow`, concatenates `additionalContext` with `\n`, journals to `.gigacode/logs/decisions.jsonl`, applies the Stop budget (2 blocks then degrade), reads stdin as `utf-8-sig`, and always exits 0 with exactly one JSON object on stdout. Reasons returned by gates on `allow` results get concatenated into the final `reason` — so gates must NOT set `reason` on allow.
- `safety_critical` is a **route-level** flag: a crashing gate in a safety-critical route soft-blocks. Advisory gates therefore live in their own non-critical routes.
- Existing test suites: `scripts/test_router.py` (28 checks, subprocess-level), wired into `scripts/smoke-check.ps1` (line 81) and `scripts/smoke-check.sh` (line 77). Router test #13 auto-checks every `gates/*.py` stays under 10,000 chars.

---

### Task 1: Router extensions — `agent_pattern` matching and canonical `hook_event_name`

**Files:**
- Modify: `.gigacode/hooks/router.py` (function `decide`, function `main`)
- Test: `scripts/test_router.py`

- [ ] **Step 1: Add failing router tests**

Append to `scripts/test_router.py` immediately before the final `print(f"\nAll {PASSED} router checks passed")` line:

```python
    # 15. agent_pattern routes match the subagent type
    tmp3, tmp_router3, tmp_config3 = temp_hooks_copy()
    with open(tmp_config3, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "SubagentStart", "agent_pattern": "^coder$",
             "gates": ["nonexistent_gate"], "safety_critical": True}
        ]}, handle)
    result = run_router("SubagentStart", {"agent_type": "coder"}, router=tmp_router3)
    check("agent_pattern_match", result["decision"] == "block", result)
    result = run_router("SubagentStart", {"agent_type": "verifier"}, router=tmp_router3)
    check("agent_pattern_no_match", result["decision"] == "allow", result)
    # alternative field name fork-drift tolerance
    result = run_router("SubagentStart", {"subagent_type": "coder"}, router=tmp_router3)
    check("agent_pattern_alt_field", result["decision"] == "block", result)
    shutil.rmtree(tmp3, ignore_errors=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/test_router.py` (from the worktree root)
Expected: FAIL at `agent_pattern_no_match`. The old router ignores `agent_pattern`, so the route (which has no `tool_pattern`) matches every `SubagentStart` event and the missing safety-critical gate blocks — including for `verifier`, where the test expects `allow`.

- [ ] **Step 3: Implement `agent_pattern` matching in `decide()`**

In `.gigacode/hooks/router.py`, inside `decide()`, after the existing `tool_pattern` check:

```python
        pattern = route.get("tool_pattern")
        if pattern and not re.search(pattern, tool_name):
            continue
```

insert:

```python
        agent_pattern = route.get("agent_pattern")
        if agent_pattern:
            agent = ""
            for key in ("agent_type", "subagent_type", "agent_name"):
                value = event.get(key)
                if isinstance(value, str) and value:
                    agent = value
                    break
            if not re.search(agent_pattern, agent):
                continue
```

- [ ] **Step 4: Inject the canonical event name into the event dict**

In `main()`, directly after `tool_name = str(event.get("tool_name", ""))`, add:

```python
    event["hook_event_name"] = event_name  # canonical name so gates can branch on it
```

(Gates added in later tasks branch on `event["hook_event_name"]`; the stdin payload may omit it while `--event` supplies it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/test_router.py`
Expected: `All 31 router checks passed` (28 existing + 3 new). Also confirm the size check still passes (router.py must stay < 10,000 chars; this change adds ~450).

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/router.py scripts/test_router.py
git commit -m "Add agent_pattern routing and canonical event name to router"
```

---

### Task 2: Shared gate helpers `_lib.py`, `quality-gates.json`, test scaffold

**Files:**
- Create: `.gigacode/hooks/gates/_lib.py`
- Create: `.gigacode/quality-gates.json`
- Create: `scripts/test_gates.py`

- [ ] **Step 1: Write the test scaffold with `_lib` tests**

Create `scripts/test_gates.py`:

```python
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
        os.environ["GIGACODE_ROOT"] = self.tmp
        return self.tmp

    def __exit__(self, *exc):
        os.environ.pop("GIGACODE_ROOT", None)
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `FileNotFoundError` for `gates/_lib.py`.

- [ ] **Step 3: Create `.gigacode/hooks/gates/_lib.py`**

```python
#!/usr/bin/env python3
"""Shared helpers for quality gates.

Each gate imports this module after putting the gates directory on sys.path:

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _lib
"""
import fnmatch
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

GATES_DIR = os.path.dirname(os.path.abspath(__file__))


def root():
    """Template repo root, derived from this file's location (not cwd).

    GIGACODE_ROOT overrides for tests."""
    override = os.environ.get("GIGACODE_ROOT")
    if override:
        return override
    return os.path.normpath(os.path.join(GATES_DIR, "..", "..", ".."))


def journal_skip(gate, reason):
    """Skip-with-record: append a skip entry to the decisions journal."""
    path = os.path.join(root(), ".gigacode", "logs", "decisions.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"kind": "skip", "gate": gate, "reason": reason,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                ensure_ascii=False) + "\n")
    except OSError:
        pass  # journaling must never change a decision


def load_quality_gates():
    path = os.path.join(root(), ".gigacode", "quality-gates.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def path_from_event(event):
    for key in ("path", "file_path", "filename"):
        value = event.get(key)
        if isinstance(value, str):
            return value.replace("\\", "/")
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "filename"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value.replace("\\", "/")
    return ""


def content_from_event(event):
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("content", "new_string", "text"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    return ""


def message_from_event(event):
    for key in ("last_assistant_message", "message", "response"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def matches_globs(path, globs):
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    for pattern in globs:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        # fnmatch's '*' crosses '/', but '**/*.kt' still demands one slash;
        # also match root-level files against the suffix.
        if pattern.startswith("**/") and fnmatch.fnmatch(normalized, pattern[3:]):
            return True
    return False


def run_command(command, timeout, extra_args=None):
    """Run a configured command string from the repo root.

    Returns (rc, output_tail). rc -1 = could not run, -2 = timeout."""
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return -1, "empty command"
    exe = shutil.which(tokens[0]) or shutil.which(tokens[0], path=root())
    if not exe:
        candidate = os.path.join(root(), tokens[0])
        if os.path.exists(candidate):
            exe = candidate
        else:
            return -1, f"command not found: {tokens[0]}"
    try:
        proc = subprocess.run(
            [exe] + tokens[1:] + list(extra_args or []),
            cwd=root(), text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -2, f"timed out after {timeout}s"
    except OSError as exc:
        return -1, str(exc)
    tail = "\n".join(proc.stdout.splitlines()[-30:])
    return proc.returncode, tail


def stdin_event():
    """CLI entry helper: parse the hook event from stdin (BOM-safe)."""
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None
```

Note on `run_command`: `shutil.which` resolves `python`/`gradle` from PATH; the extra `root()`-relative lookup lets `gradlew.bat build` / `./gradlew build` style commands work. The fake-command test relies on a clean `-1` for unknown tools.

- [ ] **Step 4: Create `.gigacode/quality-gates.json`**

Shipped unconfigured (language-agnostic template; commands documented in README, Task 10):

```json
{
  "lint": {
    "command": "",
    "applies_to": ["**/*.kt", "**/*.kts", "**/*.java"],
    "timeout_seconds": 120
  },
  "build": {
    "command": "",
    "timeout_seconds": 600
  },
  "test": {
    "command": ""
  },
  "clean_code": {
    "max_file_lines": 400,
    "max_function_lines": 60,
    "placeholder_markers": ["TODO", "FIXME", "XXX"]
  }
}
```

(`test.command` is consumed by the `verifier` agent, not by a gate — documented in Task 10.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: `All 5 gate checks passed`

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/gates/_lib.py .gigacode/quality-gates.json scripts/test_gates.py
git commit -m "Add shared gate helpers and quality-gates config"
```

---

### Task 3: `gate_context_inject` — primary mechanism

**Files:**
- Create: `.gigacode/hooks/gates/gate_context_inject.py`
- Modify: `.gigacode/hooks/router.config.json`
- Modify: `.gigacode/settings.json` (hooks: `SessionStart` router entry, new `SubagentStart` block)
- Test: `scripts/test_gates.py`

- [ ] **Step 1: Add failing tests**

In `scripts/test_gates.py`, add this function after `test_lib()` and call it in `main()` (`test_context_inject()` line before the final print):

```python
def test_context_inject():
    gate = load_gate("gate_context_inject")
    with fixture_root() as fix:
        os.makedirs(os.path.join(fix, "openspec", "changes", "add-sample"))
        result = gate.run({"hook_event_name": "SessionStart"})
        ctx = result.get("additionalContext", "")
        check("ci_session_decision", result["decision"] == "allow", result)
        check("ci_session_rules", "Development Flow Rules" in ctx, ctx[:200])
        check("ci_session_changes", "add-sample" in ctx, ctx[-200:])

        result = gate.run({"hook_event_name": "SubagentStart", "agent_type": "coder"})
        ctx = result.get("additionalContext", "")
        check("ci_subagent_search", "find_symbol" in ctx, ctx[:200])
        check("ci_subagent_changes", "add-sample" in ctx, ctx[-200:])

        result = gate.run({"hook_event_name": "UserPromptSubmit",
                           "prompt": "/develop-feature implement payment retry"})
        ctx = result.get("additionalContext", "")
        check("ci_prompt_changes", "add-sample" in ctx, result)

        result = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "привет"})
        check("ci_plain_prompt_silent", "additionalContext" not in result, result)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `gate_context_inject.py` not found.

- [ ] **Step 3: Create `.gigacode/hooks/gates/gate_context_inject.py`**

```python
#!/usr/bin/env python3
"""Advisory gate: inject rules, the module map and active OpenSpec changes.

Primary enforcement mechanism (design revision 2026-06-10): ground the agent
before generation. Never blocks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

RULE_FILES = ["development-flow.md", "openspec.md"]
MODULE_MAP = os.path.join(".gigacode", "context", "module-map.md")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def active_changes():
    changes_dir = os.path.join(_lib.root(), "openspec", "changes")
    try:
        return sorted(
            name for name in os.listdir(changes_dir)
            if name != "archive" and os.path.isdir(os.path.join(changes_dir, name))
        )
    except OSError:
        return []


def changes_line():
    changes = active_changes()
    return "Active OpenSpec changes: " + (", ".join(changes) if changes else "none") + "."


def run(event):
    name = str(event.get("hook_event_name", ""))
    if name == "SessionStart":
        parts = [read_text(os.path.join(_lib.root(), "rules", rule)) for rule in RULE_FILES]
        parts.append(read_text(os.path.join(_lib.root(), MODULE_MAP)))
        parts.append(changes_line())
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "SubagentStart":
        parts = [
            "Before creating any function, class or module: search for an existing "
            "implementation first (mcp__serena__find_symbol when available, else "
            "rg / git grep). Reuse or extend matches; record the search result in "
            "docs/development/<task-slug>/journal.md.",
            read_text(os.path.join(_lib.root(), MODULE_MAP)),
            changes_line(),
        ]
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "UserPromptSubmit":
        prompt = str(event.get("prompt", "")).lstrip()
        if prompt.startswith(("/develop-feature", "/fix-bug")):
            return {"decision": "allow", "additionalContext": changes_line() + (
                " Каждая фича/багфикс проходит через OpenSpec change "
                "(см. rules/openspec.md): propose -> apply -> archive.")}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: `All 12 gate checks passed`

- [ ] **Step 5: Wire routes in `.gigacode/hooks/router.config.json`**

Replace the `UserPromptSubmit` route and add `SessionStart`/`SubagentStart` routes. Full file after this task:

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
      "agent_pattern": "coder",
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
      "event": "Stop",
      "gates": ["validate_development_output"]
    }
  ]
}
```

- [ ] **Step 6: Register the router for `SessionStart` and `SubagentStart` in `.gigacode/settings.json`**

The `SessionStart` array becomes (router entry first, existing serena entry second; the router entry is synchronous — async hooks cannot inject context):

```json
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python .gigacode/hooks/router.py --event SessionStart"
          }
        ]
      },
      {
        "matcher": "",
        "async": true,
        "hooks": [
          {
            "type": "command",
            "command": "serena-hooks activate --client=claude-code",
            "timeout": 10000
          }
        ]
      }
    ],
```

Add a new top-level `SubagentStart` block inside `"hooks"`:

```json
    "SubagentStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python .gigacode/hooks/router.py --event SubagentStart"
          }
        ]
      }
    ],
```

- [ ] **Step 7: Verify wiring**

Run: `python -m json.tool .gigacode/settings.json` and `python scripts/test_router.py`
Expected: valid JSON; all 31 router checks pass (the new UserPromptSubmit route adds `gate_context_inject` to existing checks #5 — decision stays `allow`).

- [ ] **Step 8: Commit**

```bash
git add .gigacode/hooks/gates/gate_context_inject.py .gigacode/hooks/router.config.json .gigacode/settings.json scripts/test_gates.py
git commit -m "Add context-inject gate for session, subagent and prompt events"
```

---

### Task 4: `gate_spec_structure` — OpenSpec enforcement

**Files:**
- Create: `.gigacode/hooks/gates/gate_spec_structure.py`
- Modify: `.gigacode/hooks/router.config.json` (PreToolUse write route, new PostToolUse route, Stop route)
- Modify: `.gigacode/settings.json` (new `PostToolUse` hooks block)
- Test: `scripts/test_gates.py`, `scripts/test_router.py`

- [ ] **Step 1: Add failing gate tests**

In `scripts/test_gates.py`, add helper + test function; call `test_spec_structure()` in `main()`:

```python
def write_change(root_dir, change_id, complete=True, valid=False):
    """OpenSpec change fixture. complete=False omits tasks.md and the delta."""
    base = os.path.join(root_dir, "openspec", "changes", change_id)
    os.makedirs(os.path.join(base, "specs", "sample"), exist_ok=True)
    with open(os.path.join(base, "proposal.md"), "w", encoding="utf-8") as handle:
        handle.write("## Why\nReason.\n\n## What Changes\n- change\n\n## Impact\n- none\n")
    if complete:
        with open(os.path.join(base, "tasks.md"), "w", encoding="utf-8") as handle:
            handle.write("## 1. Group\n- [ ] 1.1 Do it\n")
        if valid:
            spec = ("## ADDED Requirements\n\n### Requirement: Sample\n"
                    "The system SHALL sample.\n\n#### Scenario: Works\n"
                    "- **WHEN** invoked\n- **THEN** it works\n")
        else:
            spec = "## ADDED Requirements\n\n### Requirement: Sample\nNo scenario here.\n"
        with open(os.path.join(base, "specs", "sample", "spec.md"), "w", encoding="utf-8") as handle:
            handle.write(spec)
    return base


def test_spec_structure():
    gate = load_gate("gate_spec_structure")
    with fixture_root() as fix:
        # PreToolUse: spec truth and archive are write-protected
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/specs/payments/spec.md"}})
        check("ss_pre_specs_block", result["decision"] == "block", result)
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/changes/archive/old/proposal.md"}})
        check("ss_pre_archive_block", result["decision"] == "block", result)
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/changes/my-change/proposal.md"}})
        check("ss_pre_change_allow", result["decision"] == "allow", result)

        # PostToolUse: CLI unavailable -> skip-with-record + advisory context
        write_change(fix, "my-change", complete=True, valid=False)
        os.environ["OPENSPEC_BIN"] = os.path.join(fix, "missing-openspec")
        try:
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/my-change/tasks.md"}})
        finally:
            os.environ.pop("OPENSPEC_BIN", None)
        check("ss_post_cli_missing_allow", result["decision"] == "allow", result)
        check("ss_post_cli_missing_note", "пропущена" in result.get("additionalContext", ""), result)

        # Stop: no PR-readiness mention -> no validation at all
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "hello"})
        check("ss_stop_no_mention_allow", result["decision"] == "allow", result)

        if shutil.which("openspec"):
            # PostToolUse: complete but invalid change -> block
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/my-change/specs/sample/spec.md"}})
            check("ss_post_invalid_block", result["decision"] == "block", result)

            # PostToolUse: incomplete invalid change -> advisory only
            write_change(fix, "draft-change", complete=False)
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/draft-change/proposal.md"}})
            check("ss_post_incomplete_advisory",
                  result["decision"] == "allow" and "additionalContext" in result, result)

            # Stop with PR-readiness mention and an invalid change -> block
            result = gate.run({"hook_event_name": "Stop",
                               "last_assistant_message": "Готово, см. openspec/changes/my-change/"})
            check("ss_stop_invalid_block", result["decision"] == "block", result)

            # Valid change passes PostToolUse
            shutil.rmtree(os.path.join(fix, "openspec", "changes", "draft-change"))
            shutil.rmtree(os.path.join(fix, "openspec", "changes", "my-change"))
            write_change(fix, "good-change", complete=True, valid=True)
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/good-change/tasks.md"}})
            check("ss_post_valid_allow", result["decision"] == "allow", result)
        else:
            print("SKIP: openspec CLI not on PATH; live validation tests skipped")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `gate_spec_structure.py` not found.

- [ ] **Step 3: Create `.gigacode/hooks/gates/gate_spec_structure.py`**

```python
#!/usr/bin/env python3
"""Spec-structure gate: protect openspec/ truth and enforce `openspec validate --strict`.

PreToolUse: deny direct writes to openspec/specs/ and openspec/changes/archive/.
PostToolUse: validate the written change; block only when the change is
structurally complete (otherwise advisory while artifacts are being created).
Stop: validate all active changes at PR-readiness moments."""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

DENY_RE = re.compile(r"(^|/)openspec/(specs|changes/archive)/")
CHANGE_RE = re.compile(r"(^|/)openspec/changes/([A-Za-z0-9][A-Za-z0-9._-]*)/")


def openspec_validate(args):
    """Returns (ok, detail): ok True/False, or None when the CLI is unavailable."""
    exe = os.environ.get("OPENSPEC_BIN") or shutil.which("openspec")
    if not exe:
        return None, "openspec CLI not found on PATH"
    cmd = [exe, "validate"] + args + ["--strict", "--no-interactive"]
    try:
        proc = subprocess.run(
            cmd, cwd=_lib.root(), text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"openspec validate could not run: {exc}"
    if proc.returncode == 0:
        return True, ""
    return False, "\n".join(proc.stdout.splitlines()[-30:])


def change_complete(change_id):
    base = os.path.join(_lib.root(), "openspec", "changes", change_id)
    has_delta = False
    for _dirpath, _dirs, files in os.walk(os.path.join(base, "specs")):
        if "spec.md" in files:
            has_delta = True
            break
    return (os.path.exists(os.path.join(base, "proposal.md"))
            and os.path.exists(os.path.join(base, "tasks.md"))
            and has_delta)


def active_changes():
    changes_dir = os.path.join(_lib.root(), "openspec", "changes")
    try:
        return [name for name in os.listdir(changes_dir)
                if name != "archive" and os.path.isdir(os.path.join(changes_dir, name))]
    except OSError:
        return []


def run(event):
    name = str(event.get("hook_event_name", ""))
    path = _lib.path_from_event(event)

    if name == "PreToolUse":
        if path and DENY_RE.search(path):
            return {"decision": "block", "reason": (
                f"Запись в '{path}' запрещена: openspec/specs/ и openspec/changes/archive/ "
                "обновляются только командой `openspec archive` (см. rules/openspec.md).")}
        return {"decision": "allow"}

    if name == "PostToolUse":
        match = CHANGE_RE.search(path or "")
        if not match or match.group(2) == "archive":
            return {"decision": "allow"}
        change_id = match.group(2)
        ok, detail = openspec_validate([change_id, "--type", "change"])
        if ok is None:
            _lib.journal_skip("gate_spec_structure", detail)
            return {"decision": "allow", "additionalContext": (
                f"gate_spec_structure: strict-валидация пропущена ({detail}). "
                "Зафиксируй пропуск в verification.md.")}
        if ok:
            return {"decision": "allow"}
        if change_complete(change_id):
            return {"decision": "block", "reason": (
                f"openspec validate {change_id} --strict failed:\n{detail}")}
        return {"decision": "allow", "additionalContext": (
            f"gate_spec_structure: change '{change_id}' ещё не проходит strict-валидацию "
            f"(артефакты не завершены):\n{detail}")}

    if name == "Stop":
        message = _lib.message_from_event(event).replace("\\", "/")
        if "openspec/changes" not in message and "docs/development/" not in message:
            return {"decision": "allow"}
        if not active_changes():
            return {"decision": "allow"}
        ok, detail = openspec_validate(["--changes"])
        if ok is None:
            _lib.journal_skip("gate_spec_structure", detail)
            return {"decision": "allow"}
        if not ok:
            return {"decision": "block", "reason": (
                f"openspec validate --changes --strict failed:\n{detail}\n"
                "Исправь структуру change или заархивируй завершённые changes.")}
        return {"decision": "allow"}

    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: with openspec on PATH (this machine): `All 22 gate checks passed` (12 from Tasks 2-3, 6 unconditional + 4 CLI-dependent new). Note: live-validation assertions (`ss_post_invalid_block` etc.) depend on openspec 1.4.1 behavior against the fixture — if a fixture detail fails validation differently than expected, fix the fixture, not the gate, as long as the gate's block/advisory split follows `change_complete`.

- [ ] **Step 5: Wire routes**

In `.gigacode/hooks/router.config.json`:

1. Append `"gate_spec_structure"` to the PreToolUse WriteFile/Edit safety route's gates:
```json
    {
      "event": "PreToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["git_guard", "gate_spec_structure"],
      "safety_critical": true
    },
```
2. Add a new PostToolUse route (non-critical — a crash here must not block):
```json
    {
      "event": "PostToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["gate_spec_structure"]
    },
```
3. Append to the Stop route's gates:
```json
    {
      "event": "Stop",
      "gates": ["validate_development_output", "gate_spec_structure"]
    }
```

- [ ] **Step 6: Register `PostToolUse` in `.gigacode/settings.json`**

Add inside `"hooks"` (after the `PreToolUse` block):

```json
    "PostToolUse": [
      {
        "matcher": "^(WriteFile|Edit)$",
        "hooks": [
          {
            "type": "command",
            "command": "python .gigacode/hooks/router.py --event PostToolUse"
          }
        ]
      }
    ],
```

- [ ] **Step 7: Add a router-level integration check**

Append to `scripts/test_router.py` before the final print (this also proves Task 1's `hook_event_name` injection reaches gates — the payload carries no `hook_event_name`):

```python
    # 16. Spec truth is write-protected through the full router path
    result = run_router("PreToolUse", {"tool_name": "WriteFile",
                                       "tool_input": {"file_path": "openspec/specs/payments/spec.md",
                                                      "content": "x"}})
    check("spec_truth_write_block", result["decision"] == "block", result)
```

- [ ] **Step 8: Run both suites**

Run: `python scripts/test_router.py` then `python scripts/test_gates.py`
Expected: `All 32 router checks passed`; all gate checks pass.

- [ ] **Step 9: Commit**

```bash
git add .gigacode/hooks/gates/gate_spec_structure.py .gigacode/hooks/router.config.json .gigacode/settings.json scripts/test_gates.py scripts/test_router.py
git commit -m "Add spec-structure gate enforcing openspec validate"
```

---

### Task 5: `gate_lint` — changed-file linting

**Files:**
- Create: `.gigacode/hooks/gates/gate_lint.py`
- Modify: `.gigacode/hooks/router.config.json` (PostToolUse route)
- Test: `scripts/test_gates.py`

- [ ] **Step 1: Add failing tests**

Add to `scripts/test_gates.py`; call `test_lint()` in `main()`:

```python
def test_lint():
    gate = load_gate("gate_lint")
    with fixture_root() as fix:
        event = {"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                 "tool_input": {"file_path": "src/Main.kt"}}

        # unconfigured -> silent allow (journal-only skip)
        write_qg(fix, {"lint": {"command": "", "applies_to": ["**/*.kt"]}})
        result = gate.run(event)
        check("lint_unconfigured_allow",
              result["decision"] == "allow" and "additionalContext" not in result, result)

        # failing linter blocks
        write_script(fix, "fail.py", 1)
        write_qg(fix, {"lint": {"command": "python fail.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 30}})
        result = gate.run(event)
        check("lint_fail_block", result["decision"] == "block", result)
        check("lint_fail_reason", "exit 1" in result.get("reason", ""), result)

        # passing linter allows
        write_script(fix, "pass.py", 0)
        write_qg(fix, {"lint": {"command": "python pass.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 30}})
        result = gate.run(event)
        check("lint_pass_allow", result["decision"] == "allow", result)

        # non-matching file skipped even with a failing command
        write_qg(fix, {"lint": {"command": "python fail.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "README.md"}})
        check("lint_nonmatching_skip", result["decision"] == "allow", result)

        # configured-but-broken command -> allow with anomaly note
        write_qg(fix, {"lint": {"command": "definitely-missing-tool-xyz",
                                "applies_to": ["**/*.kt"], "timeout_seconds": 30}})
        result = gate.run(event)
        check("lint_broken_command_note",
              result["decision"] == "allow" and "additionalContext" in result, result)

        # list form: kotlin + java linters side by side
        write_script(fix, "fail2.py", 2)
        write_qg(fix, {"lint": [
            {"command": "python pass.py", "applies_to": ["**/*.kt"], "timeout_seconds": 30},
            {"command": "python fail2.py", "applies_to": ["**/*.java"], "timeout_seconds": 30},
        ]})
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/Main.java"}})
        check("lint_list_java_block", result["decision"] == "block", result)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `gate_lint.py` not found.

- [ ] **Step 3: Create `.gigacode/hooks/gates/gate_lint.py`**

```python
#!/usr/bin/env python3
"""Lint gate: run the configured project linter on the file just written.

Deterministic -> may block. Unconfigured -> skip-with-record (journal only).
Configured but unable to run -> allow with an anomaly note."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib


def lint_configs():
    config = _lib.load_quality_gates().get("lint")
    if isinstance(config, dict):
        return [config]
    if isinstance(config, list):
        return [entry for entry in config if isinstance(entry, dict)]
    return []


def run(event):
    path = _lib.path_from_event(event)
    if not path:
        return {"decision": "allow"}
    configs = lint_configs()
    if not any((entry.get("command") or "").strip() for entry in configs):
        _lib.journal_skip("gate_lint", "lint command not configured")
        return {"decision": "allow"}
    notes = []
    for entry in configs:
        command = (entry.get("command") or "").strip()
        if not command:
            continue
        globs = entry.get("applies_to") or []
        if globs and not _lib.matches_globs(path, globs):
            continue
        rc, tail = _lib.run_command(command, entry.get("timeout_seconds", 120), [path])
        if rc < 0:
            _lib.journal_skip("gate_lint", f"{command}: {tail}")
            notes.append(f"gate_lint: линтер '{command}' не удалось запустить ({tail}). "
                         "Зафиксируй пропуск в verification.md.")
            continue
        if rc != 0:
            return {"decision": "block",
                    "reason": f"Lint failed for {path} (exit {rc}):\n{tail}"}
    if notes:
        return {"decision": "allow", "additionalContext": "\n".join(notes)}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: all checks pass (7 new).

- [ ] **Step 5: Wire the route**

In `.gigacode/hooks/router.config.json`, extend the PostToolUse route:

```json
    {
      "event": "PostToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["gate_spec_structure", "gate_lint"]
    },
```

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/gates/gate_lint.py .gigacode/hooks/router.config.json scripts/test_gates.py
git commit -m "Add lint gate scoped to changed files"
```

---

### Task 6: `gate_build` — build check at PR-readiness

**Files:**
- Create: `.gigacode/hooks/gates/gate_build.py`
- Modify: `.gigacode/hooks/router.config.json` (Stop route)
- Modify: `.gigacode/settings.json` (Stop hook timeout)
- Test: `scripts/test_gates.py`

- [ ] **Step 1: Add failing tests**

Add to `scripts/test_gates.py`; call `test_build()` in `main()`:

```python
def test_build():
    gate = load_gate("gate_build")
    with fixture_root() as fix:
        write_script(fix, "fail.py", 1)
        write_script(fix, "pass.py", 0)

        # not a PR-readiness moment -> no build even with a failing command
        write_qg(fix, {"build": {"command": "python fail.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "hi"})
        check("build_not_pr_moment", result["decision"] == "allow", result)

        pr_message = "Готово: docs/development/sample-task/pr-summary.md"

        # unconfigured -> silent allow (journal-only skip)
        write_qg(fix, {"build": {"command": ""}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_unconfigured_allow",
              result["decision"] == "allow" and "additionalContext" not in result, result)

        # failing build blocks
        write_qg(fix, {"build": {"command": "python fail.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_fail_block", result["decision"] == "block", result)

        # passing build allows
        write_qg(fix, {"build": {"command": "python pass.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_pass_allow", result["decision"] == "allow", result)

        # configured-but-broken command -> allow with anomaly note
        write_qg(fix, {"build": {"command": "definitely-missing-tool-xyz"}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_broken_command_note",
              result["decision"] == "allow" and "additionalContext" in result, result)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `gate_build.py` not found.

- [ ] **Step 3: Create `.gigacode/hooks/gates/gate_build.py`**

```python
#!/usr/bin/env python3
"""Build gate: run the configured build command on Stop, but only at
PR-readiness moments (the message mentions task artifacts) — Stop fires on
every assistant turn and a full build per turn is unacceptable.

Deterministic -> may block. The router's stop budget (2 blocks, then degrade)
caps repeated failures."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib


def run(event):
    message = _lib.message_from_event(event).replace("\\", "/")
    if "docs/development/" not in message and "openspec/changes" not in message:
        return {"decision": "allow"}
    config = _lib.load_quality_gates().get("build") or {}
    command = (config.get("command") or "").strip()
    if not command:
        _lib.journal_skip("gate_build", "build command not configured")
        return {"decision": "allow"}
    rc, tail = _lib.run_command(command, config.get("timeout_seconds", 600))
    if rc < 0:
        _lib.journal_skip("gate_build", f"{command}: {tail}")
        return {"decision": "allow", "additionalContext": (
            f"gate_build: сборку '{command}' не удалось запустить ({tail}). "
            "Зафиксируй пропуск в verification.md.")}
    if rc != 0:
        return {"decision": "block", "reason": f"Build failed (exit {rc}):\n{tail}"}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: all checks pass (5 new).

- [ ] **Step 5: Wire the route and the Stop hook timeout**

In `.gigacode/hooks/router.config.json`, extend the Stop route:

```json
    {
      "event": "Stop",
      "gates": ["validate_development_output", "gate_spec_structure", "gate_build"]
    }
```

In `.gigacode/settings.json`, give the Stop router entry an explicit timeout covering the 600 s build budget (milliseconds, matching the serena-hooks entries' unit; real GigaCode semantics to be confirmed by the pending `hook_probe` run):

```json
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python .gigacode/hooks/router.py --event Stop",
            "timeout": 630000
          }
        ]
      }
    ],
```

- [ ] **Step 6: Verify router suite still passes**

Run: `python scripts/test_router.py`
Expected: all checks pass. Check #6 (`stop_missing_artifacts_block`) still blocks: the message mentions `docs/development/`, `gate_spec_structure` finds no active changes in the real repo (allow), `gate_build` finds no configured command (allow), `validate_development_output` blocks.

- [ ] **Step 7: Commit**

```bash
git add .gigacode/hooks/gates/gate_build.py .gigacode/hooks/router.config.json .gigacode/settings.json scripts/test_gates.py
git commit -m "Add build gate triggered at PR-readiness"
```

---

### Task 7: `gate_clean_code` — advisory heuristics

**Files:**
- Create: `.gigacode/hooks/gates/gate_clean_code.py`
- Modify: `.gigacode/hooks/router.config.json` (PostToolUse route)
- Test: `scripts/test_gates.py`

- [ ] **Step 1: Add failing tests**

Add to `scripts/test_gates.py`; call `test_clean_code()` in `main()`:

```python
def test_clean_code():
    gate = load_gate("gate_clean_code")
    with fixture_root() as fix:
        write_qg(fix, {"clean_code": {"max_file_lines": 400, "max_function_lines": 60,
                                      "placeholder_markers": ["TODO", "FIXME", "XXX"]}})
        src = os.path.join(fix, "src")
        os.makedirs(src)

        def write_kt(name, text):
            path = os.path.join(src, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return path

        # long file warns
        path = write_kt("Big.kt", "\n".join(["// line"] * 450))
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_long_file_warn", "450" in result.get("additionalContext", ""), result)
        check("cc_long_file_allow", result["decision"] == "allow", result)

        # TODO marker warns
        path = write_kt("Todo.kt", "fun a() {\n    // TODO finish\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_todo_warn", "TODO" in result.get("additionalContext", ""), result)

        # long function warns
        body = "fun bigFunction(x: Int) {\n" + "    println(x)\n" * 70 + "}\n"
        path = write_kt("LongFun.kt", body)
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_long_function_warn", "блок" in result.get("additionalContext", ""), result)

        # Thread.sleep in a test file warns
        path = write_kt("PaymentServiceTest.kt",
                        "class PaymentServiceTest {\n    fun t() { Thread.sleep(1000) }\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_sleep_in_test_warn", "Thread.sleep" in result.get("additionalContext", ""), result)

        # clean small file is silent
        path = write_kt("Ok.kt", "fun ok() {\n    println(1)\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_clean_silent", "additionalContext" not in result, result)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `gate_clean_code.py` not found.

- [ ] **Step 3: Create `.gigacode/hooks/gates/gate_clean_code.py`**

```python
#!/usr/bin/env python3
"""Clean-code gate: heuristics on the file just written. ADVISORY-ONLY —
always returns allow; findings go through additionalContext. Promotion to
blocking requires decision-journal evidence (design revision 2026-06-10)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

CODE_EXTS = (".kt", ".kts", ".java", ".py", ".ts", ".tsx", ".js", ".jsx",
             ".go", ".rs", ".cs")
CONTROL_RE = re.compile(r"^(if|for|while|when|switch|try|do|else|catch|synchronized)\b")
TEST_FILE_RE = re.compile(r"(test|spec)", re.IGNORECASE)


def resolve(path):
    if os.path.isabs(path):
        return path
    candidate = os.path.abspath(path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(_lib.root(), path)


def long_blocks(lines, max_len):
    """Naive brace-depth scan; function-like = the opening line has '(' and is
    not a control-flow statement. Heuristic by design — advisory only."""
    warnings = []
    stack = []
    for lineno, line in enumerate(lines, 1):
        for char in line:
            if char == "{":
                head = line.lstrip()
                func_like = "(" in line and not CONTROL_RE.match(head)
                stack.append((lineno, func_like))
            elif char == "}" and stack:
                start, func_like = stack.pop()
                length = lineno - start + 1
                if func_like and length > max_len:
                    warnings.append(
                        f"строка {start}: блок на {length} строк (максимум {max_len})")
    return warnings


def run(event):
    path = _lib.path_from_event(event)
    if not path or not path.endswith(CODE_EXTS):
        return {"decision": "allow"}
    target = resolve(path)
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return {"decision": "allow"}
    config = _lib.load_quality_gates().get("clean_code") or {}
    max_file = int(config.get("max_file_lines", 400))
    max_func = int(config.get("max_function_lines", 60))
    markers = config.get("placeholder_markers") or ["TODO", "FIXME", "XXX"]

    warnings = []
    if len(lines) > max_file:
        warnings.append(f"файл {len(lines)} строк (максимум {max_file})")
    marker_re = re.compile(r"\b(" + "|".join(re.escape(m) for m in markers) + r")\b")
    marker_lines = [str(i) for i, line in enumerate(lines, 1) if marker_re.search(line)]
    if marker_lines:
        warnings.append("маркеры " + "/".join(markers)
                        + " на строках: " + ", ".join(marker_lines[:10]))
    warnings.extend(long_blocks(lines, max_func)[:5])
    if TEST_FILE_RE.search(os.path.basename(path)) and any(
            "Thread.sleep" in line for line in lines):
        warnings.append("Thread.sleep в тестовом файле — используй Awaitility "
                        "или другой механизм ожидания вместо sleep")

    if not warnings:
        return {"decision": "allow"}
    return {"decision": "allow", "additionalContext": (
        f"gate_clean_code (advisory) для {path}:\n- " + "\n- ".join(warnings))}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: all checks pass (6 new).

- [ ] **Step 5: Wire the route**

In `.gigacode/hooks/router.config.json`, extend the PostToolUse route:

```json
    {
      "event": "PostToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["gate_spec_structure", "gate_lint", "gate_clean_code"]
    },
```

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/gates/gate_clean_code.py .gigacode/hooks/router.config.json scripts/test_gates.py
git commit -m "Add advisory clean-code heuristics gate"
```

---

### Task 8: `gate_existing_code` — advisory duplicate detection

**Files:**
- Create: `.gigacode/hooks/gates/gate_existing_code.py`
- Modify: `.gigacode/hooks/router.config.json` (new non-critical PreToolUse route)
- Test: `scripts/test_gates.py`

- [ ] **Step 1: Add failing tests**

Add to `scripts/test_gates.py`; call `test_existing_code()` in `main()`:

```python
def init_git(root_dir):
    subprocess.run(["git", "init", "-q"], cwd=root_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "-A"], cwd=root_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_existing_code():
    gate = load_gate("gate_existing_code")
    with fixture_root() as fix:
        src = os.path.join(fix, "src")
        os.makedirs(src)
        with open(os.path.join(src, "Existing.kt"), "w", encoding="utf-8") as handle:
            handle.write('class PaymentService(\n    @KafkaListener(topics = ["payment-events"])\n)\n')
        init_git(fix)

        # duplicate class name -> advisory context naming the existing file
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/new/PaymentService2.kt",
                                          "content": "class PaymentService { }"}})
        check("ec_duplicate_symbol_warn", "Existing.kt" in result.get("additionalContext", ""), result)
        check("ec_advisory_allow", result["decision"] == "allow", result)

        # duplicate Kafka topic literal -> advisory context
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/new/AnotherConsumer.kt",
                                          "content": '@KafkaListener(topics = ["payment-events"])\nclass AnotherConsumer { }'}})
        check("ec_topic_warn", "payment-events" in result.get("additionalContext", ""), result)

        # no declarations in content -> silent allow
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/notes.txt", "content": "x = 1"}})
        check("ec_no_symbols_silent", "additionalContext" not in result, result)

        # Edit of an existing file is skipped
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                           "tool_input": {"file_path": os.path.join(src, "Existing.kt"),
                                          "new_string": "class PaymentService { }"}})
        check("ec_edit_existing_skip", "additionalContext" not in result, result)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_gates.py`
Expected: FAIL — `gate_existing_code.py` not found.

- [ ] **Step 3: Create `.gigacode/hooks/gates/gate_existing_code.py`**

```python
#!/usr/bin/env python3
"""Existing-code gate: detect declarations (and Kafka topic literals) in the
content about to be written that already exist in the tree. ADVISORY-ONLY —
always allow; never deny (promotion needs decision-journal evidence).

Search engine: rg when available, else `git grep` (tracked files), else
skip-with-record. Serena stays an agent-side tool; hooks use text search."""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

DECL_KEYWORDS = "class|interface|object|enum|fun|def|function"
SYMBOL_RE = re.compile(r"\b(?:" + DECL_KEYWORDS + r")\s+([A-Za-z_][A-Za-z0-9_]{2,})")
TOPIC_RE = re.compile(r"topics?\s*=\s*[\[{]?\s*\"([^\"]+)\"")
EXCLUDED = ("build", "target", "out", "dist", "node_modules")


def resolve(path):
    if os.path.isabs(path):
        return path
    candidate = os.path.abspath(path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(_lib.root(), path)


def search(pattern):
    """Returns (hit_lines, skip_reason)."""
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "-n", "--no-heading", "-m", "20",
               "-g", "!{" + ",".join((".git",) + EXCLUDED) + "}", "-e", pattern]
    else:
        git = shutil.which("git")
        if not git:
            return [], "neither rg nor git available"
        cmd = [git, "grep", "-n", "-I", "-E", pattern, "--", "."]
        cmd += [":!{0}".format(name) for name in EXCLUDED]
    try:
        proc = subprocess.run(cmd, cwd=_lib.root(), text=True, encoding="utf-8",
                              errors="replace", stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)
    if proc.returncode not in (0, 1):
        return [], f"search exited {proc.returncode}"
    return proc.stdout.splitlines(), ""


def run(event):
    tool = str(event.get("tool_name", ""))
    path = _lib.path_from_event(event)
    content = _lib.content_from_event(event)
    if not content:
        return {"decision": "allow"}
    if tool == "Edit" and path and os.path.exists(resolve(path)):
        return {"decision": "allow"}  # only new files are checked

    boundary = "(^|[^A-Za-z0-9_])"
    patterns = []
    symbols = []
    for name in SYMBOL_RE.findall(content):
        if name not in symbols:
            symbols.append(name)
    if symbols:
        names = "|".join(re.escape(s) for s in symbols[:5])
        patterns.append(f"{boundary}({DECL_KEYWORDS})[ \\t]+({names})([^A-Za-z0-9_]|$)")
    topics = []
    for topic in TOPIC_RE.findall(content):
        if topic not in topics:
            topics.append(topic)
    if topics:
        patterns.append("|".join(re.escape(t) for t in topics[:5]))
    if not patterns:
        return {"decision": "allow"}

    normalized = (path or "").replace("\\", "/").lstrip("./")
    hits = []
    for pattern in patterns:
        lines, skip = search(pattern)
        if skip:
            _lib.journal_skip("gate_existing_code", skip)
            return {"decision": "allow"}
        hits.extend(line for line in lines
                    if normalized and normalized not in line.replace("\\", "/"))
    if not hits:
        return {"decision": "allow"}
    return {"decision": "allow", "additionalContext": (
        "gate_existing_code (advisory): найдены существующие объявления/топики "
        "с теми же именами:\n" + "\n".join(hits[:10]) +
        "\nПрочитай их и переиспользуй/расширь вместо дубликата; "
        "результат поиска зафиксируй в journal.md.")}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_gates.py`
Expected: all checks pass (4 new). On this machine `rg` is absent, so the `git grep` path is exercised; the fixture is `git init`-ed and `git add`-ed for that reason.

- [ ] **Step 5: Wire the route (own non-critical route — advisory crash must not block)**

In `.gigacode/hooks/router.config.json`, add after the safety-critical WriteFile/Edit route:

```json
    {
      "event": "PreToolUse",
      "tool_pattern": "^(WriteFile|Edit)$",
      "gates": ["gate_existing_code"]
    },
```

- [ ] **Step 6: Verify router latency**

Run: `python scripts/test_router.py`
Expected: all checks pass. Watch the printed latency line; the existing latency check measures the Bash route (unchanged). If the journal later shows WriteFile-route latency above ~200 ms, narrowing options are: skip files > 64 KB content, or drop the topic search — note this in the journal review, do not pre-optimize.

- [ ] **Step 7: Commit**

```bash
git add .gigacode/hooks/gates/gate_existing_code.py .gigacode/hooks/router.config.json scripts/test_gates.py
git commit -m "Add advisory existing-code gate with rg and git grep search"
```

---

### Task 9: Smoke-check wiring and full offline verification

**Files:**
- Modify: `scripts/smoke-check.ps1` (required files list at line 3-23; new test invocation after line 84)
- Modify: `scripts/smoke-check.sh` (required files list at line 4-24; new test invocation after line 77)

- [ ] **Step 1: Extend the required-files lists**

In `scripts/smoke-check.ps1`, append to the `$required` array (before the closing `)`):

```powershell
  ".gigacode/hooks/gates/_lib.py",
  ".gigacode/hooks/gates/gate_context_inject.py",
  ".gigacode/hooks/gates/gate_spec_structure.py",
  ".gigacode/hooks/gates/gate_lint.py",
  ".gigacode/hooks/gates/gate_build.py",
  ".gigacode/hooks/gates/gate_clean_code.py",
  ".gigacode/hooks/gates/gate_existing_code.py",
  ".gigacode/quality-gates.json"
```

(Add a trailing comma to the current last entry `".serena/project.yml"`.)

In `scripts/smoke-check.sh`, append to the `required=(...)` array the same eight paths in shell syntax:

```bash
  ".gigacode/hooks/gates/_lib.py"
  ".gigacode/hooks/gates/gate_context_inject.py"
  ".gigacode/hooks/gates/gate_spec_structure.py"
  ".gigacode/hooks/gates/gate_lint.py"
  ".gigacode/hooks/gates/gate_build.py"
  ".gigacode/hooks/gates/gate_clean_code.py"
  ".gigacode/hooks/gates/gate_existing_code.py"
  ".gigacode/quality-gates.json"
```

- [ ] **Step 2: Wire `test_gates.py` into both smoke scripts**

In `scripts/smoke-check.ps1`, after the `test_router.py` block (after line 84):

```powershell
python -m json.tool .gigacode/quality-gates.json | Out-Null

python scripts/test_gates.py
if ($LASTEXITCODE -ne 0) {
  throw "gate tests failed"
}
```

In `scripts/smoke-check.sh`, after the `test_router.py` line (line 77):

```bash
"$python_cmd" -m json.tool .gigacode/quality-gates.json >/dev/null
"$python_cmd" scripts/test_gates.py
```

- [ ] **Step 3: Run the full PowerShell smoke check**

Run from the worktree root: `powershell -ExecutionPolicy Bypass -File scripts/smoke-check.ps1`
Expected: `Smoke check passed` with all router + gate tests green and the openspec/serena notes unchanged.

- [ ] **Step 4: Run the bash smoke check**

Run: `bash scripts/smoke-check.sh` (via the Bash tool / Git Bash)
Expected: `Smoke check passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke-check.ps1 scripts/smoke-check.sh
git commit -m "Wire gate tests and quality-gates config into smoke checks"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md` (new Russian section after the Serena setup section)
- Modify: `docs/flow-overview.md` (§7 config example — align with the real schema)
- Modify: `rules/development-flow.md` (append quality-gates note)
- Modify: `.gigacode/agents/verifier.md` (test command source)
- Modify: `.gigacode/skills/development-flow/SKILL.md` (append "Quality Gates" section)

- [ ] **Step 1: README — add a Russian "Quality gates" section**

Insert after the Serena setup section (find the heading containing "Serena"; place the new `##` section right after that section's end):

```markdown
## Quality gates (Phase 4)

Шесть гейтов качества работают через hook router (`.gigacode/hooks/router.py`)
и настраиваются одним файлом `.gigacode/quality-gates.json` — языковая
специфика живёт в конфиге, не в коде гейтов.

| Гейт | Событие | Режим |
|---|---|---|
| `gate_context_inject` | SessionStart, SubagentStart(coder), UserPromptSubmit | инъекция правил и активных OpenSpec changes |
| `gate_spec_structure` | PreToolUse, PostToolUse, Stop | блок: запись в `openspec/specs/`, провал `openspec validate --strict` |
| `gate_lint` | PostToolUse (изменённый файл) | блок при ненулевом exit code линтера |
| `gate_build` | Stop (момент готовности PR) | блок при провале сборки |
| `gate_clean_code` | PostToolUse | advisory: размер файла/функции, TODO/FIXME, Thread.sleep в тестах |
| `gate_existing_code` | PreToolUse (новые файлы) | advisory: дубликаты символов и Kafka-топиков (rg → git grep) |

Пример настройки для Kotlin/Java + Gradle:

```json
{
  "lint": [
    { "command": "gradlew.bat ktlintCheck", "applies_to": ["**/*.kt", "**/*.kts"], "timeout_seconds": 300 },
    { "command": "gradlew.bat checkstyleMain", "applies_to": ["**/*.java"], "timeout_seconds": 300 }
  ],
  "build": { "command": "gradlew.bat compileKotlin compileTestKotlin", "timeout_seconds": 600 },
  "test": { "command": "gradlew.bat test" },
  "clean_code": { "max_file_lines": 400, "max_function_lines": 60, "placeholder_markers": ["TODO", "FIXME", "XXX"] }
}
```

Пустая `command` = проверка пропускается с записью в
`.gigacode/logs/decisions.jsonl` (skip-with-record); смоук-чеки и работа в
репозитории без настроенных команд не блокируются. `test.command` использует
агент `verifier` (гейты тесты не гоняют). На Linux/macOS указывайте
`./gradlew ...`.
```

- [ ] **Step 2: flow-overview — align the §7 config example**

In `docs/flow-overview.md`, replace the JSON example at lines 116-124 with:

```json
{
  "lint": [
    { "command": "./gradlew ktlintCheck detekt", "applies_to": ["**/*.kt"] },
    { "command": "./gradlew checkstyleMain", "applies_to": ["**/*.java"] }
  ],
  "build": { "command": "./gradlew compileKotlin compileTestKotlin" },
  "test":  { "command": "./gradlew test" },
  "clean_code": { "max_file_lines": 400, "max_function_lines": 60 }
}
```

And in item 3 of §7 (lines 134-138), replace the last sentence «Это эвристики уровня advisory, конкретный список правил — настройка в `quality-gates.json`.» with: «Это эвристики уровня advisory: `Thread.sleep` в тестовых файлах ловит `gate_clean_code`, остальное — зона `verifier`.»

- [ ] **Step 3: rules/development-flow.md — append**

```markdown
## Quality Gates

Гейты качества (`.gigacode/hooks/gates/`) работают автоматически через hook
router. Команды линтера/сборки/тестов настраиваются в
`.gigacode/quality-gates.json`. Если команда не настроена, проверка
пропускается с записью в `.gigacode/logs/decisions.jsonl` — зафиксируй такой
пропуск в `verification.md`. Advisory-предупреждения гейтов (existing_code,
clean_code) не блокируют, но требуют явной реакции: переиспользовать найденное
или обосновать в journal.md, почему создаётся новое.
```

- [ ] **Step 4: verifier.md — test command source**

In `.gigacode/agents/verifier.md`, add one line in the section describing how to run checks (after the existing instruction about running tests; adapt placement to the file's structure):

```markdown
- Команда тестов берётся из `.gigacode/quality-gates.json` (`test.command`);
  если она пуста — определи команду по проекту и зафиксируй её в verification.md.
```

- [ ] **Step 5: development-flow SKILL.md — append a "Quality Gates" section**

Append to `.gigacode/skills/development-flow/SKILL.md` (before any closing notes section if present, else at the end):

```markdown
## Quality Gates

Hook-гейты сопровождают весь цикл: контекст инъецируется на старте сессии и
сабагентов; записи в `openspec/specs/` и `openspec/changes/archive/`
заблокированы (только `openspec archive`); после каждой записи файла
запускаются линтер и advisory-эвристики; на Stop в момент готовности PR —
strict-валидация changes и сборка. Команды настраиваются в
`.gigacode/quality-gates.json`; ненастроенная команда = skip-with-record в
`.gigacode/logs/decisions.jsonl`.
```

- [ ] **Step 6: Verify and commit**

Run: `powershell -ExecutionPolicy Bypass -File scripts/smoke-check.ps1`
Expected: `Smoke check passed` (agent files must stay under 10,000 chars — the verifier.md addition is small).

```bash
git add README.md docs/flow-overview.md rules/development-flow.md .gigacode/agents/verifier.md .gigacode/skills/development-flow/SKILL.md
git commit -m "Document quality gates configuration and behavior"
```

---

## Out of scope / follow-ups

- **Serena e2e verification** (install `uv` + `serena-agent`, exercise `find_symbol` on real Kotlin code) — pre-rollout checklist, independent of these gates.
- **Live hook verification against a real GigaCode build** (`hook_probe.py`) — still pending from Phase 3; confirms real event/tool names, `SubagentStart` agent-type field name, and hook timeout units. The `agent_pattern` field candidates (`agent_type`, `subagent_type`, `agent_name`) and the `630000` ms Stop timeout are the two assumptions to re-check first.
- **Ultracode red-team review** of the enforcement layer after this phase (user-requested; bypass hunting: cmd /c wrappers, encodings, aliases).
- **Phase 5**: Context7 MCP + Graphify JSON feeding `gate_context_inject` (the gate already reads `.gigacode/context/module-map.md` when present — that is the Phase 5 integration point).

## Self-review notes

- Spec coverage: all six Phase 4 gates from the design table are implemented (Tasks 3-8); `quality-gates.json` (Task 2) matches design §3 with skip-with-record; router stays gate-agnostic (Task 1 adds only config-driven matching); smoke checks cover design §Smoke Checks items for new gates (sizes auto-checked by router test #13, journal by existing test #7).
- Advisory gates (`context_inject`, `clean_code`, `existing_code`) never return anything but `allow` and never set `reason` — consistent with the router's reason-concatenation behavior.
- Type consistency: every gate exposes `run(event) -> dict` and a stdin `main()`; `_lib` function names match across all tasks (`root`, `journal_skip`, `load_quality_gates`, `path_from_event`, `content_from_event`, `message_from_event`, `matches_globs`, `run_command`, `stdin_event`).
