# GigaCode Dev-Flow Phase 3: Hook Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-hook registrations with a single config-driven router that dispatches quality gates, journals every decision, and protects against Stop-block loops.

**Architecture:** `router.py` is the only script registered in `.gigacode/settings.json`. It reads the event JSON from stdin (utf-8-sig), matches `(event, tool_pattern)` routes in `router.config.json`, imports gate modules from `.gigacode/hooks/gates/` and calls their `run(event) -> dict` in-process (one interpreter — latency), aggregates decisions (block > ask > allow), and appends every decision to `.gigacode/logs/decisions.jsonl`. Existing hooks (`git_guard`, `preflight_check`, `validate_development_output`) become gates: same logic, new `run()` entry point, CLI stdin wrapper kept for standalone testing.

**Tech Stack:** Python 3 stdlib only (json, re, importlib, argparse). Tests: `scripts/test_router.py` (plain asserts, no pytest), invoked from both smoke-check scripts. Working dir: worktree `.worktrees/dev-flow-enforcement`, branch `feature/dev-flow-enforcement`.

**Design references:** `docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md` sections 0–2 (hierarchy, router, gates). Key constraints: router and every gate < 10,000 chars; utf-8-sig stdin; safety-critical gate crash → soft block naming the escape hatch; Stop-block budget 2 then degrade to warning; PreToolUse latency budget 200 ms; narrow matchers.

---

### Task 1: Hook probe (design "step 0" deliverable)

The design requires verifying real GigaCode event/tool names before trusting matchers (fork-drift risk). The dev environment has no GigaCode runtime, so the deliverable is the probe tool plus instructions; running it against a live build is recorded as a follow-up for the user.

**Files:**
- Create: `.gigacode/hooks/hook_probe.py`
- Modify: `README.md` (new subsection under «Адаптация под команду»)

- [ ] **Step 1: Write the probe script**

```python
#!/usr/bin/env python3
"""Hook probe: log raw hook events to verify GigaCode's real event/tool names.

Register temporarily for any event in .gigacode/settings.json:
    {"type": "command", "command": "python .gigacode/hooks/hook_probe.py"}
Then exercise the flow and inspect .gigacode/logs/hook-probe.jsonl.
Always answers "allow"; never blocks anything.
"""
import json
import os
import sys
import time

LOGS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs"))


def main():
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "raw": raw}
    try:
        event = json.loads(raw)
        record["hook_event_name"] = event.get("hook_event_name", "")
        record["tool_name"] = event.get("tool_name", "")
        record["keys"] = sorted(event.keys())
    except json.JSONDecodeError as exc:
        record["parse_error"] = str(exc)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(os.path.join(LOGS_DIR, "hook-probe.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the probe runs standalone**

Run: `'{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"}}' | python .gigacode/hooks/hook_probe.py`
Expected: `{"decision": "allow"}` on stdout; `.gigacode/logs/hook-probe.jsonl` contains one record with `"tool_name": "Bash"`.

- [ ] **Step 3: Document live verification in README**

Append to README.md after the «Адаптация под команду» section body:

```markdown
### Проверка семантики хуков вашей сборки GigaCode

Имена событий и тулов в `router.config.json` соответствуют документации
Qwen Code. GigaCode — форк, поэтому перед продакшен-использованием один раз
проверьте реальные имена: временно зарегистрируйте
`python .gigacode/hooks/hook_probe.py` на интересующие события в
`.gigacode/settings.json`, выполните типовые действия (запрос, правка файла,
git-команда) и сверьте `hook_event_name`/`tool_name` в
`.gigacode/logs/hook-probe.jsonl` с матчерами в `router.config.json`.
```

- [ ] **Step 4: Commit**

```bash
git add .gigacode/hooks/hook_probe.py README.md
git commit -m "Add hook probe for live event-name verification"
```

---

### Task 2: Move git_guard behind the gates/ contract

**Files:**
- Create: `.gigacode/hooks/gates/git_guard.py` (move of `.gigacode/hooks/git_guard.py`)
- Modify: `scripts/smoke-check.ps1`, `scripts/smoke-check.sh` (paths), `.gigacode/settings.json` (hook path + permission)

- [ ] **Step 1: git mv the file**

```bash
git mv .gigacode/hooks/git_guard.py .gigacode/hooks/gates/git_guard.py
```

- [ ] **Step 2: Replace main() with run() + CLI wrapper**

In `gates/git_guard.py`, keep every function above `main()` unchanged (`PROTECTED_BRANCHES`, `PROTECTED_PATHS`, `respond`, `run_git`, `current_branch`, `is_protected_branch`, `command_from_event`, `path_from_event`, `protected_path`, `split_command`, `GIT_GLOBAL_VALUE_FLAGS`, `git_subcommand_index`, `is_destructive_git_command`, `is_branch_write`). Replace `main()` with:

```python
def run(event):
    """Gate contract: event dict in, decision dict out."""
    command = command_from_event(event)
    file_path = path_from_event(event)

    if command:
        blocked, reason = is_destructive_git_command(command)
        if blocked:
            return {"decision": "block", "reason": reason + " Use an explicit human-approved recovery workflow."}
        branch = current_branch()
        if is_protected_branch(branch) and is_branch_write(command):
            return {"decision": "block", "reason": f"Blocked git write operation on protected branch '{branch}'. Create a feature or bugfix branch first."}

    if protected_path(file_path):
        return {"decision": "ask", "reason": f"Protected path '{file_path}' requires explicit confirmation with risk explanation."}

    return {"decision": "allow"}


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Note: `current_branch()` moves inside the `if command:` branch — no git subprocess for write/path events.

- [ ] **Step 3: Update both smoke scripts to the new path**

In `scripts/smoke-check.ps1` and `scripts/smoke-check.sh`: replace every `.gigacode/hooks/git_guard.py` with `.gigacode/hooks/gates/git_guard.py` (required-files list and all sample invocations).

- [ ] **Step 4: Update settings.json**

In `.gigacode/settings.json`: change the PreToolUse hook command to `python .gigacode/hooks/gates/git_guard.py`; in `permissions.allow` add `"Bash(python .gigacode/hooks/gates/*)"` after the existing `"Bash(python .gigacode/hooks/*)"`.

- [ ] **Step 5: Run smoke checks**

Run: `.\scripts\smoke-check.ps1` and `bash scripts/smoke-check.sh`
Expected: both end with `Smoke check passed`.

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks .gigacode/settings.json scripts/smoke-check.ps1 scripts/smoke-check.sh
git commit -m "Move git_guard behind the gates/ contract"
```

(Никогда не `git add -A`: в `docs/` могут лежать неотслеживаемые файлы пользователя.)

---

### Task 3: Move preflight_check and validate_development_output to gates/

**Files:**
- Create: `.gigacode/hooks/gates/preflight_check.py`, `.gigacode/hooks/gates/validate_development_output.py` (moves)
- Modify: `scripts/smoke-check.ps1`, `scripts/smoke-check.sh`, `.gigacode/settings.json`

- [ ] **Step 1: git mv both files**

```bash
git mv .gigacode/hooks/preflight_check.py .gigacode/hooks/gates/preflight_check.py
git mv .gigacode/hooks/validate_development_output.py .gigacode/hooks/gates/validate_development_output.py
```

- [ ] **Step 2: Refactor preflight_check main() into run()**

Keep `prompt_from_event` and `has_any` unchanged; `respond` is no longer needed — delete it. Replace `main()` with:

```python
def run(event):
    prompt = prompt_from_event(event)
    lowered = prompt.lower()

    if "/develop-feature" not in lowered and "/fix-bug" not in lowered:
        return {"decision": "allow"}

    if len(prompt.strip().split()) < 3:
        return {"decision": "ask", "reason": "Укажите имя задачи или короткое описание."}

    implement_mode = has_any(lowered, [" implement", " implementation", "реализ", "исправь", "сделай"])

    if "/develop-feature" in lowered and implement_mode:
        if not has_any(lowered, ["acceptance", "criteria", "критер", "поведение", "behavior"]):
            return {"decision": "ask", "reason": "Для implement mode по фиче нужны acceptance criteria или ожидаемое поведение."}

    if "/fix-bug" in lowered and implement_mode:
        if not has_any(lowered, ["expected", "actual", "repro", "symptom", "ожид", "факт", "воспро", "симптом", "stack", "trace", "error"]):
            return {"decision": "ask", "reason": "Для implement mode по багу нужны симптом, expected/actual behavior, reproduction evidence или error details."}

    return {"decision": "allow", "reason": "Проверьте analytics и Graphify при наличии; если их нет, используйте описанные fallbacks."}


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Refactor validate_development_output main() into run()**

Keep `REQUIRED_FILES`, `PLACEHOLDER_RE`, `TASK_DIR_RE`, `last_message`, `find_task_dir`, `read_file` unchanged; delete `respond`. Replace `main()` with:

```python
def run(event):
    message = last_message(event)
    if "docs/development/" not in message.replace("\\", "/"):
        return {"decision": "allow"}

    task_dir = find_task_dir(message)
    if not task_dir:
        return {"decision": "block", "reason": "Сообщение упоминает docs/development, но не содержит валидный task directory."}

    missing = [name for name in REQUIRED_FILES if not os.path.exists(os.path.join(task_dir, name))]
    if missing:
        return {"decision": "block", "reason": f"Не хватает development artifact files: {', '.join(missing)}"}

    for name in REQUIRED_FILES:
        path = os.path.join(task_dir, name)
        content = read_file(path)
        if PLACEHOLDER_RE.search(content):
            return {"decision": "block", "reason": f"Placeholder marker найден в {path}."}

    verification = read_file(os.path.join(task_dir, "verification.md")).lower()
    if "passed" in message.lower() and "command" not in verification and "exit" not in verification:
        return {"decision": "block", "reason": "Сообщение заявляет passing checks без command evidence в verification.md."}

    return {"decision": "allow"}


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update smoke scripts and settings.json paths**

Replace `.gigacode/hooks/preflight_check.py` → `.gigacode/hooks/gates/preflight_check.py` and `.gigacode/hooks/validate_development_output.py` → `.gigacode/hooks/gates/validate_development_output.py` in both smoke scripts (required-files list + invocations) and in the `UserPromptSubmit` / `Stop` hook commands in `.gigacode/settings.json`.

- [ ] **Step 5: Run smoke checks**

Run: `.\scripts\smoke-check.ps1` and `bash scripts/smoke-check.sh`
Expected: both end with `Smoke check passed`.

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks .gigacode/settings.json scripts/smoke-check.ps1 scripts/smoke-check.sh
git commit -m "Move preflight and output validator behind the gates/ contract"
```

---

### Task 4: Router core + config + tests

**Files:**
- Create: `.gigacode/hooks/router.config.json`
- Create: `.gigacode/hooks/router.py`
- Create: `scripts/test_router.py`

- [ ] **Step 1: Write the config**

`.gigacode/hooks/router.config.json`:

```json
{
  "version": 1,
  "stop_block_budget": 2,
  "routes": [
    {
      "event": "UserPromptSubmit",
      "gates": ["preflight_check"]
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

Gate names are module filenames in `.gigacode/hooks/gates/` without `.py`.

- [ ] **Step 2: Write the failing tests**

`scripts/test_router.py` (run from repo root; plain asserts, exits non-zero on failure):

```python
#!/usr/bin/env python3
"""Offline tests for the hook router. Run from the repo root: python scripts/test_router.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTER = os.path.join(ROOT, ".gigacode", "hooks", "router.py")
HOOKS_DIR = os.path.join(ROOT, ".gigacode", "hooks")
PASSED = 0


def run_router(event_name, payload, router=ROUTER, bom=False):
    data = json.dumps(payload).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    proc = subprocess.run(
        [sys.executable, router, "--event", event_name],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    assert proc.returncode == 0, f"router exited {proc.returncode}: {proc.stderr.decode()}"
    return json.loads(proc.stdout.decode("utf-8"))


def check(name, condition, detail=""):
    global PASSED
    assert condition, f"{name}: {detail}"
    PASSED += 1
    print(f"ok: {name}")


def temp_hooks_copy():
    tmp = tempfile.mkdtemp(prefix="router-test-")
    shutil.copytree(HOOKS_DIR, os.path.join(tmp, "hooks"))
    return tmp, os.path.join(tmp, "hooks", "router.py"), os.path.join(tmp, "hooks", "router.config.json")


def main():
    # 1. Destructive git through BOM-prefixed stdin is blocked
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git -C . reset --hard HEAD"}}, bom=True)
    check("bom_destructive_block", result["decision"] == "block", result)

    # 2. Benign git command is allowed
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    check("benign_allow", result["decision"] == "allow", result)

    # 3. Unmatched tool produces allow without running gates
    result = run_router("PreToolUse", {"tool_name": "ReadFile", "tool_input": {"path": "README.md"}})
    check("unmatched_tool_allow", result["decision"] == "allow", result)

    # 4. Protected path write asks
    result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": ".github/workflows/deploy.yml"}})
    check("protected_path_ask", result["decision"] == "ask", result)

    # 5. Valid plan-only feature prompt allowed
    result = run_router("UserPromptSubmit", {"prompt": "/develop-feature plan-only payment retry"})
    check("preflight_allow", result["decision"] == "allow", result)

    # 6. Stop with missing artifacts blocks
    # Unique session id: the stop budget counts consecutive blocks per session,
    # so reusing one id would degrade to allow on the third smoke run.
    session = f"t-main-{os.getpid()}-{int(time.time())}"
    result = run_router("Stop", {"last_assistant_message": "Complete in docs/development/sample-task/", "session_id": session})
    check("stop_missing_artifacts_block", result["decision"] == "block", result)

    # 7. Decisions journal is written
    journal = os.path.join(ROOT, ".gigacode", "logs", "decisions.jsonl")
    check("journal_written", os.path.exists(journal) and os.path.getsize(journal) > 0, journal)

    # 8. Corrupt config soft-blocks with escape hatch
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    with open(tmp_config, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, router=tmp_router)
    check("config_error_block", result["decision"] == "block" and "disableAllHooks" in result.get("reason", ""), result)
    shutil.rmtree(tmp, ignore_errors=True)

    # 9. Missing safety-critical gate soft-blocks with escape hatch
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    with open(tmp_config, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^Bash$", "gates": ["nonexistent_gate"], "safety_critical": True}
        ]}, handle)
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, router=tmp_router)
    check("missing_gate_soft_block", result["decision"] == "block" and "disableAllHooks" in result.get("reason", ""), result)

    # 10. Missing non-critical gate degrades to allow
    with open(tmp_config, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^Bash$", "gates": ["nonexistent_gate"]}
        ]}, handle)
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, router=tmp_router)
    check("missing_gate_noncritical_allow", result["decision"] == "allow", result)
    shutil.rmtree(tmp, ignore_errors=True)

    # 11. Stop budget: third consecutive block degrades to warning
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    payload = {"last_assistant_message": "Complete in docs/development/sample-task/", "session_id": "t-budget"}
    first = run_router("Stop", payload, router=tmp_router)
    second = run_router("Stop", payload, router=tmp_router)
    third = run_router("Stop", payload, router=tmp_router)
    check("stop_budget_first_block", first["decision"] == "block", first)
    check("stop_budget_second_block", second["decision"] == "block", second)
    check("stop_budget_third_degrades", third["decision"] == "allow" and "systemMessage" in third, third)
    shutil.rmtree(tmp, ignore_errors=True)

    # 12. Latency: full router run on a benign PreToolUse sample
    start = time.monotonic()
    run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    elapsed_ms = (time.monotonic() - start) * 1000
    print(f"latency: {elapsed_ms:.0f} ms (budget 200 ms, hard limit 1000 ms)")
    check("latency_hard_limit", elapsed_ms < 1000, f"{elapsed_ms:.0f} ms")
    if elapsed_ms > 200:
        print(f"WARNING: latency {elapsed_ms:.0f} ms exceeds the 200 ms design budget")

    # 13. Size limits: router and every gate below 10,000 characters
    for path in [ROUTER] + [os.path.join(HOOKS_DIR, "gates", name) for name in os.listdir(os.path.join(HOOKS_DIR, "gates")) if name.endswith(".py")]:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        check(f"size_{os.path.basename(path)}", len(content) < 10000, f"{len(content)} chars")

    print(f"\nAll {PASSED} router checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python scripts/test_router.py`
Expected: FAIL — `router.py` does not exist yet (`FileNotFoundError` / non-zero exit).

- [ ] **Step 4: Write the router**

`.gigacode/hooks/router.py`:

```python
#!/usr/bin/env python3
"""Hook router: the single dispatcher for all GigaCode hook events.

Registered once per event in .gigacode/settings.json. Matches routes in
router.config.json, runs gate modules from gates/ in-process, aggregates
decisions (block > ask > allow), journals every decision to
.gigacode/logs/decisions.jsonl, and degrades repeated Stop blocks to a
warning after the configured budget.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HOOKS_DIR, "router.config.json")
GATES_DIR = os.path.join(HOOKS_DIR, "gates")
LOGS_DIR = os.path.normpath(os.path.join(HOOKS_DIR, "..", "logs"))
JOURNAL_PATH = os.path.join(LOGS_DIR, "decisions.jsonl")
STATE_PATH = os.path.join(LOGS_DIR, "router-state.json")

ESCAPE_HATCH = (
    'If the hooks themselves are broken, set "disableAllHooks": true in '
    ".gigacode/settings.json temporarily and report the issue."
)

SEVERITY = {"allow": 0, "ask": 1, "block": 2}


def journal(record):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(JOURNAL_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # journaling must never change a decision


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


def run_gate(name, event, safety_critical):
    try:
        path = os.path.join(GATES_DIR, name + ".py")
        spec = importlib.util.spec_from_file_location("gate_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.run(event)
        if not isinstance(result, dict) or result.get("decision") not in SEVERITY:
            raise ValueError(f"invalid gate result: {result!r}")
        return result, ""
    except Exception as exc:  # crash isolation: a broken gate must not kill routing
        if safety_critical:
            return {"decision": "block", "reason": f"Safety gate '{name}' failed: {exc}. {ESCAPE_HATCH}"}, str(exc)
        return {"decision": "allow"}, str(exc)


def aggregate(results):
    final = {"decision": "allow"}
    reasons = []
    contexts = []
    for result in results:
        if SEVERITY[result["decision"]] > SEVERITY[final["decision"]]:
            final["decision"] = result["decision"]
        if result.get("reason"):
            reasons.append(result["reason"])
        if result.get("additionalContext"):
            contexts.append(result["additionalContext"])
    if reasons:
        final["reason"] = " ".join(reasons)
    if contexts:
        final["additionalContext"] = "\n".join(contexts)
    return final


def apply_stop_budget(event_name, final, config, event):
    if event_name != "Stop":
        return final
    key = "stop:" + str(event.get("session_id", "default"))
    state = load_state()
    if final["decision"] != "block":
        if key in state:
            state.pop(key)
            save_state(state)
        return final
    count = state.get(key, 0) + 1
    state[key] = count
    save_state(state)
    budget = config.get("stop_block_budget", 2)
    if count > budget:
        journal({"kind": "stop_budget_exhausted", "session": key, "count": count})
        return {
            "decision": "allow",
            "systemMessage": f"Stop gate blocked {count} times; degraded to a warning. Unresolved: {final.get('reason', '')}",
        }
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default="")
    args = parser.parse_args()

    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        journal({"kind": "parse_error", "error": str(exc)})
        print(json.dumps({"decision": "allow"}))
        return

    event_name = args.event or str(event.get("hook_event_name", ""))
    tool_name = str(event.get("tool_name", ""))

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        journal({"kind": "config_error", "error": str(exc)})
        print(json.dumps({"decision": "block", "reason": f"router.config.json unreadable: {exc}. {ESCAPE_HATCH}"}, ensure_ascii=False))
        return

    results = []
    for route in config.get("routes", []):
        if route.get("event") != event_name:
            continue
        pattern = route.get("tool_pattern")
        if pattern and not re.search(pattern, tool_name):
            continue
        for gate_name in route.get("gates", []):
            result, error = run_gate(gate_name, event, route.get("safety_critical", False))
            journal({"kind": "gate", "event": event_name, "tool": tool_name, "gate": gate_name,
                     "decision": result["decision"], "reason": result.get("reason", ""), "error": error})
            results.append(result)

    final = aggregate(results)
    final = apply_stop_budget(event_name, final, config, event)
    journal({"kind": "final", "event": event_name, "tool": tool_name, "decision": final["decision"]})
    print(json.dumps(final, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/test_router.py`
Expected: `All ... router checks passed` (≥ 16 checks counting per-file size checks), latency line printed.

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/router.py .gigacode/hooks/router.config.json scripts/test_router.py
git commit -m "Add config-driven hook router with journal and stop budget"
```

---

### Task 5: Rewire settings.json to the router

**Files:**
- Modify: `.gigacode/settings.json` (hooks block)

- [ ] **Step 1: Replace the hooks block**

The three gate registrations collapse into router registrations with narrow matchers; serena-hooks entries stay untouched. New `hooks` value:

```json
{
  "UserPromptSubmit": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "python .gigacode/hooks/router.py --event UserPromptSubmit"
        }
      ]
    }
  ],
  "PreToolUse": [
    {
      "matcher": "Bash|Shell|WriteFile|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "python .gigacode/hooks/router.py --event PreToolUse"
        }
      ]
    },
    {
      "matcher": "",
      "async": true,
      "hooks": [
        {
          "type": "command",
          "command": "serena-hooks remind --client=claude-code",
          "timeout": 5000
        }
      ]
    },
    {
      "matcher": "mcp__serena__*",
      "async": true,
      "hooks": [
        {
          "type": "command",
          "command": "serena-hooks auto-approve --client=claude-code",
          "timeout": 5000
        }
      ]
    }
  ],
  "Stop": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "python .gigacode/hooks/router.py --event Stop"
        }
      ]
    }
  ],
  "SessionStart": [
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
  "SessionEnd": [
    {
      "matcher": "",
      "async": true,
      "hooks": [
        {
          "type": "command",
          "command": "serena-hooks cleanup --client=claude-code",
          "timeout": 5000
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Validate JSON**

Run: `python -m json.tool .gigacode/settings.json`
Expected: pretty-printed JSON, exit 0.

- [ ] **Step 3: Commit**

```bash
git add .gigacode/settings.json
git commit -m "Register hook router instead of individual hook scripts"
```

---

### Task 6: Smoke integration and docs

**Files:**
- Modify: `scripts/smoke-check.ps1`, `scripts/smoke-check.sh` (router assertions)
- Modify: `README.md` (hooks description)
- Modify: `docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md` (journal path)

- [ ] **Step 1: Add router files to required lists and run router tests from smoke**

In `scripts/smoke-check.ps1`: add to `$required`: `".gigacode/hooks/router.py"`, `".gigacode/hooks/router.config.json"`, `".gigacode/hooks/hook_probe.py"`. After the existing gate sample checks add:

```powershell
python -m json.tool .gigacode/hooks/router.config.json | Out-Null

python scripts/test_router.py
if ($LASTEXITCODE -ne 0) {
  throw "router tests failed"
}
```

In `scripts/smoke-check.sh`: add the same three paths to `required=(...)` and after the gate sample checks:

```bash
"$python_cmd" -m json.tool .gigacode/hooks/router.config.json >/dev/null
"$python_cmd" scripts/test_router.py
```

- [ ] **Step 2: Verify config references only existing gates (smoke assertion)**

Append to `scripts/test_router.py` `main()` before the final print:

```python
    # 14. Config references only existing gate files
    with open(os.path.join(HOOKS_DIR, "router.config.json"), "r", encoding="utf-8") as handle:
        config = json.load(handle)
    for route in config["routes"]:
        for gate in route["gates"]:
            gate_path = os.path.join(HOOKS_DIR, "gates", gate + ".py")
            check(f"gate_exists_{gate}", os.path.exists(gate_path), gate_path)
```

- [ ] **Step 3: Update README hooks description**

In `README.md`, in the «Enterprise Git Safety» section, append:

```markdown
Все хуки проходят через единый роутер `.gigacode/hooks/router.py`:
маршрутизация описана в `.gigacode/hooks/router.config.json`, каждое решение
журналируется в `.gigacode/logs/decisions.jsonl`. Добавление нового гейта —
это новый файл в `.gigacode/hooks/gates/` плюс строка в конфиге; роутер не
редактируется. Если хуки сломаны, временный выключатель —
`"disableAllHooks": true` в `.gigacode/settings.json`.
```

- [ ] **Step 4: Fix the journal path in the design doc**

In `docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md`, replace both occurrences of `.gigacode/hooks/decisions.jsonl` with `.gigacode/logs/decisions.jsonl` (the logs dir is gitignored; a runtime journal must not live under version-controlled hooks/).

- [ ] **Step 5: Full verification**

Run: `.\scripts\smoke-check.ps1` and `bash scripts/smoke-check.sh`
Expected: both end with `Smoke check passed`, router tests included.

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke-check.ps1 scripts/smoke-check.sh scripts/test_router.py README.md docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md
git commit -m "Wire router tests into smoke checks and document the router"
```

---

## Verification checklist (whole phase)

- [ ] `python scripts/test_router.py` — all checks pass, latency printed.
- [ ] `.\scripts\smoke-check.ps1` and `bash scripts/smoke-check.sh` — `Smoke check passed`.
- [ ] `git log --oneline` shows one commit per task.
- [ ] `.gigacode/logs/` stays untracked (`git status --short` clean of log files).
- [ ] Manual spot-check: `'{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | python .gigacode/hooks/router.py --event PreToolUse` → `block`.
