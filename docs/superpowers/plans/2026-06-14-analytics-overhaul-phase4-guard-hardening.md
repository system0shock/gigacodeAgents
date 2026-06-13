# Analytics Overhaul — Phase 4 (git_guard Hardening) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the security-bypass and validation gaps the Codex reviewer found on PR #2 by porting dev-flow's hardened `git_guard` engine into the analytics module (preserving the analytics create-once openspec split), adding four git-semantics fixes that dev-flow also lacks, routing `NotebookEdit` through the safety gates, and tightening the Stop gate.

**Architecture:** The analytics `git_guard.py` was copied from an early dev-flow snapshot; dev-flow's later red-team + Phase-6 hardening fixes most engine-level bypasses (absolute/nested path matching via component-regex, redirection/fd parsing, Unicode-separator folding, command-substitution recursion, `eval`/`command` wrappers, PowerShell/`dd`/`sed`/`find` write+delete detection). We re-port that engine but MUST preserve the analytics-only rule: `openspec/specs/` is blocked on the **shell** channel only — file-tool (`WriteFile`/`Edit`/`NotebookEdit`) writes to specs are intentionally allowed and governed by `gate_spec_bootstrap` (create-once). On top of the port we add four fixes neither module has yet, fix the `NotebookEdit` routing gap, and require `produced.final` for `complete` runs.

**Tech Stack:** Python 3 stdlib (re, shlex, fnmatch, unicodedata), the existing offline test harness (`check()` + explicit `SystemExit`), Bash + PowerShell smoke checks.

**Source of findings:** Codex review on PR #2 (13 inline comments), triaged 2026-06-14. **Source of the hardened engine:** `F:/Coding/gigacode_agents/.worktrees/dev-flow-enforcement/.gigacode/hooks/gates/git_guard.py`.

**Base branch / working directory:** `feature/analytics-overhaul`, worktree `F:/Coding/gigacode_agents/.worktrees/analytics-overhaul` (HEAD `441e2c1`). **All tasks run from the worktree root; file paths are prefixed `modules/analytics/`.** The plan doc lives on `master`.

**Co-author line for every commit:**
```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

---

## Findings addressed (and what is NOT)

| Codex finding | Severity | Task |
|---|---|---|
| #1 self-protect absolute/nested `.gigacode` not matched | P1 | 1 (engine port: component-regex) |
| #2/#13 glued/fd redirections (`x>file`, `2>file`) not parsed | P1 | 1 (REDIR + embedded-redirect) |
| #12 `.git` delete via absolute/traversal path | P1 | 1 (engine port: `GIT_DIR_RE`) |
| #5 `git clean --exclude=…n…` false dry-run → destructive clean allowed | P1 | 2 |
| #6 `tee a b` only checks last operand | P1 | 2 |
| #8 `git restore <file>` (default worktree) not blocked | P2 | 2 |
| #11 `git checkout -f/--force <branch>` not blocked | P2 | 2 |
| #4 `NotebookEdit` not routed to safety gates | P1 | 3 |
| #9 manifest `complete` with empty `produced.final` passes Stop gate | P1 | 4 |
| #10 `gate_final_format` mis-relativizes absolute module paths | P2 | 1 (covered by relative paths today; engine port note) |

**Declined (by design):** Codex "Reject bootstrap SQL in `db/ddl`/`db/dml`" — `gate_final_format` is a format/placement gate, not the bootstrap-policy enforcer; `ddl/dml` are valid placements for the future change-cycle. The "not during bootstrap" rule lives on the agent/skill.

**Deferred (verification-blocked):** Codex #3 — router emits `additionalContext` at top level vs `hookSpecificOutput.additionalContext`. This is the same pattern in dev-flow and depends on GigaCode's real hook-output contract (the "live runtime probe pending" item). It is NOT fixed here; tracked for the shared runtime-probe task.

**Cross-module note:** #5, #6, #8, #11 (and #3) affect dev-flow too. Task 5 records a back-port follow-up; this plan scopes to analytics only.

---

## File structure (Phase 4)

Modified:
- `modules/analytics/.gigacode/hooks/gates/git_guard.py` — replaced with the hardened engine + analytics adaptations (Task 1) + four semantics fixes (Task 2).
- `modules/analytics/.gigacode/settings.json` — `PreToolUse` matcher gains `NotebookEdit` (Task 3).
- `modules/analytics/.gigacode/hooks/router.config.json` — file-tool `PreToolUse` routes gain `NotebookEdit` (Task 3).
- `modules/analytics/.gigacode/hooks/gates/validate_run_output.py` — `complete` requires non-empty `produced.final` (Task 4).
- `modules/analytics/scripts/test_gates.py` — new git_guard + validate_run_output cases (Tasks 1, 2, 4).
- `modules/analytics/scripts/test_router.py` — NotebookEdit routing cases (Task 3).

Not touched: agents, skill, command, rules, openspec, templates, final-tree skeleton, README, build_module_map, the other gates.

---

### Task 1: Port the hardened git_guard engine (preserve the openspec create-once split)

This replaces `git_guard.py` with dev-flow's hardened version, then re-applies the analytics-specific adaptations. **The single most important invariant: a file-tool write to `openspec/specs/<cap>/spec.md` must stay ALLOWED** (it is governed by `gate_spec_bootstrap`); only the SHELL channel blocks `openspec/specs/`.

**Files:**
- Modify: `modules/analytics/.gigacode/hooks/gates/git_guard.py`
- Test: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Copy the hardened engine over the analytics gate**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
cp F:/Coding/gigacode_agents/.worktrees/dev-flow-enforcement/.gigacode/hooks/gates/git_guard.py \
   modules/analytics/.gigacode/hooks/gates/git_guard.py
```

- [ ] **Step 2: Re-add `notebook_path` extraction (it exists in the analytics gates; dev-flow's copy lacks it)**

In `path_from_event`, both key tuples list only `("path", "file_path", "filename")`. Change BOTH occurrences to include `notebook_path`:

Replace:
```python
    for key in ("path", "file_path", "filename"):
        v = event.get(key)
        if isinstance(v, str):
            return _norm(v)
    ti = event.get("tool_input")
    if isinstance(ti, dict):
        for key in ("path", "file_path", "filename"):
```
with:
```python
    for key in ("path", "file_path", "filename", "notebook_path"):
        v = event.get(key)
        if isinstance(v, str):
            return _norm(v)
    ti = event.get("tool_input")
    if isinstance(ti, dict):
        for key in ("path", "file_path", "filename", "notebook_path"):
```

- [ ] **Step 3: Replace the openspec-truth constant with the analytics shell/file split**

Replace:
```python
# Mirror of gate_spec_structure.DENY_RE so shell-redirection writes to openspec
# truth are caught here too (gate_spec_structure only sees WriteFile/Edit).
OPENSPEC_TRUTH_RE = re.compile(r"(^|/)openspec/(specs|changes/archive)/", re.IGNORECASE)
```
with:
```python
# Analytics create-once split: openspec/specs is blocked on the SHELL channel
# only — file-tool (WriteFile/Edit/NotebookEdit) writes to specs are ALLOWED here
# and governed by gate_spec_bootstrap (create-once, fail-closed on its own route).
# openspec/changes/archive is blocked on BOTH channels.
OPENSPEC_ARCHIVE_RE = re.compile(r"(^|/)openspec/changes/archive/", re.IGNORECASE)
OPENSPEC_SPECS_RE = re.compile(r"(^|/)openspec/specs/", re.IGNORECASE)
```

- [ ] **Step 4: Make `classify_path` channel-aware**

Replace:
```python
def classify_path(path):
    """'block' for enforcement/.git/openspec-truth paths, 'ask' for protected,
    else ''. The block tier is matched component-wise (regex) so an absolute
    path cannot slip past a start-anchored glob."""
    p = _norm(path)
    if SELF_PROTECT_RE.search(p) or GIT_DIR_RE.search(p) or OPENSPEC_TRUTH_RE.search(p):
        return "block"
    if any(fnmatch.fnmatch(p, pat) for pat in PROTECTED_PATHS):
        return "ask"
    return ""
```
with:
```python
def classify_path(path, shell=False):
    """'block' for enforcement/.git paths and openspec/changes/archive (any
    channel), plus openspec/specs on the SHELL channel; 'ask' for protected;
    else ''. The block tier is matched component-wise (regex) so an absolute
    path cannot slip past a start-anchored glob."""
    p = _norm(path)
    if SELF_PROTECT_RE.search(p) or GIT_DIR_RE.search(p) or OPENSPEC_ARCHIVE_RE.search(p):
        return "block"
    if shell and OPENSPEC_SPECS_RE.search(p):
        return "block"
    if any(fnmatch.fnmatch(p, pat) for pat in PROTECTED_PATHS):
        return "ask"
    return ""
```

- [ ] **Step 5: Pass `shell=True` at the two shell-channel call sites**

In `_destructive_target`, replace `c = classify_path(_sq(t))` with `c = classify_path(_sq(t), shell=True)`.

In `inspect_command`, replace `c = classify_path(tgt)` with `c = classify_path(tgt, shell=True)`.

(The `run()` file-path branch keeps `classify_path(file_path)` — `shell=False` — so file-tool writes to `openspec/specs/` stay allowed.)

- [ ] **Step 6: Catch argument-glued redirections (`x>file`)**

dev-flow's `REDIR_RE` handles leading-operator forms (`>file`, `2>file`, `>>file`, `>|file`) but not an operator glued AFTER a word (`echo x>.gigacode/settings.json` → shlex token `x>.gigacode/settings.json`). Add an embedded-redirect rule.

Add this constant immediately after the existing `REDIR_RE = ...` line:
```python
# Operator glued after a word (`arg>file`, `arg2>>file`): shlex keeps it as one
# token because it is not a real shell. Capture the operand as a write target.
EMBED_REDIR_RE = re.compile(r"(?P<op>>{1,2})(?P<clobber>\|?)(?P<operand>[^>]*)$")
```

Replace `_split_redirects` with:
```python
def _split_redirects(tokens):
    """(positionals, out_targets): out_targets are files written via > >> n> >|
    — leading-operator OR glued after a word (`x>file`). Input redirects
    (< << n<) are consumed but never write-targets, so a stdin redirect cannot
    masquerade as a copy/move destination."""
    positionals, out_targets = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        m = REDIR_RE.match(t)
        if m:  # token starts with [fd]> / >> / >| / <
            operand = m.group(4)
            if not operand and i + 1 < len(tokens):
                operand = tokens[i + 1]
                i += 1
            if m.group(2).startswith(">") and operand:
                out_targets.append(operand)
            i += 1
            continue
        if ">" in t:  # operator glued after a word: `arg>file`
            em = EMBED_REDIR_RE.search(t)
            if em:
                operand = em.group("operand")
                if not operand and i + 1 < len(tokens):
                    operand = tokens[i + 1]
                    i += 1
                if operand:
                    out_targets.append(operand)
                prefix = t[:em.start()].rstrip("0123456789")  # drop trailing fd digits
                if prefix:
                    positionals.append(prefix)
                i += 1
                continue
        positionals.append(t)
        i += 1
    return positionals, out_targets
```

- [ ] **Step 7: Add Phase-4 engine tests to `test_gates.py`**

In `test_git_guard()` (after the existing checks, before the function ends), add:
```python
    # --- Phase 4: engine hardening (ported from dev-flow) ---
    # CRITICAL regression: file-tool write to openspec/specs stays ALLOWED
    # (create-once split — governed by gate_spec_bootstrap, not git_guard).
    check("gg_file_specs_allowed_p4",
          gate.run({"tool_input": {"file_path": "openspec/specs/new-cap/spec.md"}})["decision"] == "allow")
    # shell write to specs still blocks
    check("gg_shell_specs_block_p4",
          gate.run({"tool_input": {"command": "echo x > openspec/specs/cap/spec.md"}})["decision"] == "block")
    # absolute / nested .gigacode (component-regex, not start-anchored glob)
    check("gg_abs_gigacode",
          gate.run({"tool_input": {"file_path": "/workspace/proj/modules/analytics/.gigacode/hooks/router.py"}})["decision"] == "block")
    # .git deletion by absolute and traversal path
    check("gg_rm_abs_dotgit",
          gate.run({"tool_input": {"command": "rm -rf /workspace/proj/.git"}})["decision"] == "block")
    check("gg_rm_traversal_dotgit",
          gate.run({"tool_input": {"command": "rm -rf ../../.git"}})["decision"] == "block")
    # fd-prefixed and argument-glued redirections to an enforcement path
    check("gg_fd_redirect",
          gate.run({"tool_input": {"command": "printf err 2>.gigacode/settings.json"}})["decision"] == "block")
    check("gg_glued_redirect",
          gate.run({"tool_input": {"command": "echo x>.gigacode/settings.json"}})["decision"] == "block")
    # unicode separator and command-substitution bypasses
    check("gg_nbsp_reset",
          gate.run({"tool_input": {"command": "git reset --hard"}})["decision"] == "block")
    check("gg_subst_reset",
          gate.run({"tool_input": {"command": "x=$(git reset --hard)"}})["decision"] == "block")
```

- [ ] **Step 8: Run the gate tests — fix the implementation (not the tests) until green**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_gates.py | tail -1
```
Expected: `All <N> gate checks passed` (N = previous 60 + 9 new = 69), no failures. These checks are the security spec — if a check fails, fix `git_guard.py`, never weaken the check. If a check itself looks wrong, STOP and report.

- [ ] **Step 9: Run the router suite (unchanged, must stay green) and both smoke checks**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_router.py | tail -1
cd modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -1 && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -1; cd ../..
```
Expected: `All 28 router checks passed`; `Analytics module smoke check passed.` twice.

- [ ] **Step 10: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/.gigacode/hooks/gates/git_guard.py modules/analytics/scripts/test_gates.py
git commit -m "Port hardened git_guard engine, preserve openspec create-once split

Closes PR #2 findings: absolute/nested .gigacode self-protect (#1), .git
deletion via absolute/traversal path (#12), fd/glued redirections (#2,#13);
adds Unicode/substitution/eval/PS/dd/find defenses from dev-flow.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Four git-semantics fixes (clean / tee / restore / checkout)

These bugs exist in BOTH analytics and dev-flow. The `git restore`/`checkout` short-flag fixes need original-case tokens (`-S` ≠ `-s`), so this task first stops lowercasing the `rest` token list in `inspect_command`, then fixes each verb. All existing long-flag checks remain correct (git long flags are lowercase as typed; `-d`/`-D` are already both listed).

**Files:**
- Modify: `modules/analytics/.gigacode/hooks/gates/git_guard.py`
- Test: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Stop lowercasing destructive-verb arguments**

In `inspect_command`, replace:
```python
                rest = [_sq(t).lower() for t in leaf[idx + 1:]]
```
with:
```python
                rest = [_sq(t) for t in leaf[idx + 1:]]  # original case: -S != -s, -W != -w
```
(`sub` stays lowercased on the line above.)

- [ ] **Step 2: Fix `git clean` flag parsing (#5)**

In `git_destructive`, replace:
```python
    if sub == "clean":
        combined = "".join(t.lstrip("-") for t in rest if t.startswith("-"))
        # -n (dry-run) overrides force: previewing what -f would delete is safe.
        if "f" in combined and "n" not in combined:
            return "Blocked destructive `git clean -f`."
```
with:
```python
    if sub == "clean":
        # Parse flags exactly: short clusters are single-dash alpha runs; long
        # flags whole. An option VALUE (--exclude=node_modules) must not leak its
        # letters into flag detection. -n (dry-run) overrides -f (preview is safe).
        short = "".join(t[1:] for t in rest if re.match(r"^-[A-Za-z]+$", t))
        longs = [t for t in rest if t.startswith("--")]
        dry = ("n" in short) or ("--dry-run" in longs)
        force = ("f" in short) or ("--force" in longs)
        if force and not dry:
            return "Blocked destructive `git clean -f`."
```

- [ ] **Step 3: Fix `git restore` default-worktree (#8) and `git checkout -f/--force` (#11)**

In `git_destructive`, replace:
```python
    if sub == "checkout" and "--" in rest:
        return "Blocked `git checkout --` (discards working-tree edits)."
    if sub == "restore" and "--worktree" in rest:
        return "Blocked `git restore --worktree`."
```
with:
```python
    if sub == "checkout":
        if "--" in rest:
            return "Blocked `git checkout --` (discards working-tree edits)."
        if "--force" in rest or any(
                re.match(r"^-[A-Za-z]*f[A-Za-z]*$", t) and not t.startswith("--") for t in rest):
            return "Blocked `git checkout -f/--force` (discards working-tree edits)."
    if sub == "restore":
        # restore touches the working tree by default; only --staged/-S WITHOUT
        # --worktree/-W leaves the worktree intact.
        def _short(ch):  # case-sensitive short flag inside a cluster, e.g. -S / -SW
            return any(re.match(r"^-[A-Za-z]*" + ch + r"[A-Za-z]*$", t)
                       and not t.startswith("--") for t in rest)
        staged = ("--staged" in rest) or _short("S")
        worktree = ("--worktree" in rest) or _short("W")
        if worktree or not staged:
            return "Blocked `git restore` (discards working-tree edits)."
```

- [ ] **Step 4: Fix `tee` multi-output (#6)**

In `write_targets`, replace:
```python
    if prog in WRITE_VERBS and nonflag:
        targets.append(nonflag[-1])              # cp/mv/tee/install dest = last
```
with:
```python
    if prog == "tee":
        targets.extend(nonflag)                  # tee writes EVERY file operand
    elif prog in WRITE_VERBS and nonflag:
        targets.append(nonflag[-1])              # cp/mv/install dest = last
```

- [ ] **Step 5: Add tests to `test_gates.py`**

In `test_git_guard()`, after the Task-1 block, add:
```python
    # --- Phase 4: git-semantics fixes ---
    check("gg_clean_exclude_blocks",
          gate.run({"tool_input": {"command": "git clean -fd --exclude=node_modules"}})["decision"] == "block")
    check("gg_clean_dryrun_allows",
          gate.run({"tool_input": {"command": "git clean -fdn"}})["decision"] == "allow")
    check("gg_tee_multi_output",
          gate.run({"tool_input": {"command": "tee .gigacode/hooks/router.py /tmp/out"}})["decision"] == "block")
    check("gg_restore_default_blocks",
          gate.run({"tool_input": {"command": "git restore README.md"}})["decision"] == "block")
    check("gg_restore_staged_allows",
          gate.run({"tool_input": {"command": "git restore --staged README.md"}})["decision"] == "allow")
    check("gg_checkout_force_blocks",
          gate.run({"tool_input": {"command": "git checkout -f main"}})["decision"] == "block")
    check("gg_checkout_plain_allows",
          gate.run({"tool_input": {"command": "git checkout my-feature"}})["decision"] == "allow")
```

- [ ] **Step 6: Run tests — fix implementation until green**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_gates.py | tail -1
```
Expected: `All <N> gate checks passed` (N = 69 + 7 = 76), no failures. Tests are the spec.

- [ ] **Step 7: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/.gigacode/hooks/gates/git_guard.py modules/analytics/scripts/test_gates.py
git commit -m "Fix git clean/tee/restore/checkout destructive-command gaps

Closes PR #2 findings #5 (clean --exclude false dry-run), #6 (tee multi-output),
#8 (git restore default worktree), #11 (git checkout -f/--force). Same bugs exist
in dev-flow — back-port tracked separately.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Route NotebookEdit through the safety gates (#4)

The gates already extract `notebook_path` (git_guard after Task 1; gate_spec_bootstrap via `_lib`), but the router is never invoked for `NotebookEdit`, so those writes bypass the PreToolUse safety routes. Add `NotebookEdit` to the settings matcher and to the file-tool PreToolUse routes.

**Files:**
- Modify: `modules/analytics/.gigacode/settings.json`
- Modify: `modules/analytics/.gigacode/hooks/router.config.json`
- Test: `modules/analytics/scripts/test_router.py`

- [ ] **Step 1: Extend the settings PreToolUse matcher**

In `modules/analytics/.gigacode/settings.json`, in the `"PreToolUse"` router hook entry, replace:
```json
        "matcher": "^(Bash|Shell|WriteFile|Edit)$",
```
with:
```json
        "matcher": "^(Bash|Shell|WriteFile|Edit|NotebookEdit)$",
```
(Leave the two `serena-hooks` PreToolUse entries unchanged.)

- [ ] **Step 2: Extend the file-tool PreToolUse routes in router.config.json**

In `modules/analytics/.gigacode/hooks/router.config.json`, the `git_guard` and `gate_spec_bootstrap` PreToolUse routes use `"tool_pattern": "^(WriteFile|Edit)$"`. Change BOTH to:
```json
      "tool_pattern": "^(WriteFile|Edit|NotebookEdit)$",
```
Leave the `git_guard` `^(Bash|Shell)$` route and the `PostToolUse` `^(WriteFile|Edit)$` route unchanged (the format gates self-filter by path; notebooks are not final artifacts).

- [ ] **Step 3: Add NotebookEdit routing tests to `test_router.py`**

In `test_routing()`, after the existing `rt_tool_anchored` check, add:
```python
        check("rt_notebookedit_routes",
              sb.run({"hook_event_name": "PreToolUse",
                      "tool_name": "NotebookEdit"})["decision"] == "block")
```
and update the route fixture in that test so the PreToolUse route pattern includes NotebookEdit. Replace:
```python
            {"event": "PreToolUse", "tool_pattern": "^(WriteFile|Edit)$",
             "gates": ["fixture_block"]},
```
with:
```python
            {"event": "PreToolUse", "tool_pattern": "^(WriteFile|Edit|NotebookEdit)$",
             "gates": ["fixture_block"]},
```

In `test_real_config()`, after the gate-existence loop, add a wiring assertion:
```python
        pre_file_routes = [r for r in config.get("routes", [])
                           if r.get("event") == "PreToolUse"
                           and set(r.get("gates", [])) & {"git_guard", "gate_spec_bootstrap"}
                           and "WriteFile" in (r.get("tool_pattern") or "")]
        for r in pre_file_routes:
            check(f"rt_notebookedit_wired:{','.join(r['gates'])}",
                  "NotebookEdit" in (r.get("tool_pattern") or ""),
                  r.get("tool_pattern"))
```

- [ ] **Step 4: Run router tests + validate JSON + both smoke checks**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python -m json.tool modules/analytics/.gigacode/settings.json >/dev/null && echo "settings OK"
python -m json.tool modules/analytics/.gigacode/hooks/router.config.json >/dev/null && echo "config OK"
python modules/analytics/scripts/test_router.py | tail -1
cd modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -1 && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -1; cd ../..
```
Expected: `settings OK`, `config OK`, `All <N> router checks passed` (N = 28 + 1 + the wired routes, ~30), both smoke success lines.

- [ ] **Step 5: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/.gigacode/settings.json modules/analytics/.gigacode/hooks/router.config.json modules/analytics/scripts/test_router.py
git commit -m "Route NotebookEdit through git_guard and gate_spec_bootstrap

Closes PR #2 finding #4: NotebookEdit writes bypassed the safety-critical
PreToolUse routes (the gates already handle notebook_path).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Stop gate requires final artifacts for `complete` runs (#9)

A manifest marked `complete` with the template default `produced.final: []` currently passes the Stop gate (nothing to validate). The skill/command require generating the `analytics/`+`architecture/` tree and recording produced files before close.

**Files:**
- Modify: `modules/analytics/.gigacode/hooks/gates/validate_run_output.py`
- Test: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Require non-empty `produced.final` when status is `complete`**

In `validate_run_output.py`, in `check_feature`, replace:
```python
    if status == "complete":
        produced = manifest.get("produced", {})
        if not isinstance(produced, dict):
            produced = {}
        for group in ("technical", "final"):
            for rel in missing_files(root_dir, produced.get(group, []) or []):
                issues.append(f"{name}: заявленный файл отсутствует: {rel}")
```
with:
```python
    if status == "complete":
        produced = manifest.get("produced", {})
        if not isinstance(produced, dict):
            produced = {}
        final = produced.get("final", [])
        if not (isinstance(final, (list, tuple))
                and any(isinstance(x, str) and x for x in final)):
            issues.append(f"{name}: статус complete, но produced.final пуст "
                          "(финальное дерево не сгенерировано/не записано)")
        for group in ("technical", "final"):
            for rel in missing_files(root_dir, produced.get(group, []) or []):
                issues.append(f"{name}: заявленный файл отсутствует: {rel}")
```

- [ ] **Step 2: Add tests to `test_gates.py`**

In `test_validate_run_output()`, after the `vr_complete_ok` check, add:
```python
        # complete with empty produced.final must NOT pass (finals required)
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": []}))
        check("vr_complete_empty_final",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
```

- [ ] **Step 3: Run gate tests + both smoke checks**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_gates.py | tail -1
cd modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -1 && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -1; cd ../..
```
Expected: `All <N> gate checks passed` (N = 76 + 1 = 77); both smoke success lines.

- [ ] **Step 4: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/.gigacode/hooks/gates/validate_run_output.py modules/analytics/scripts/test_gates.py
git commit -m "Require produced.final for complete runs in Stop gate

Closes PR #2 finding #9: a manifest marked complete with empty produced.final
bypassed final-artifact validation.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Full verification + push + back-port note

**Files:** none committed (verification + push).

- [ ] **Step 1: Run every offline suite**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics
python scripts/test_router.py | tail -1
python scripts/test_gates.py | tail -1
python scripts/test_module_map.py | tail -1
```
Expected: router ~30, gates 77, module-map 9 — all `... checks passed`.

- [ ] **Step 2: Both smoke checks end-to-end**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -1 && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -1; cd ../../..
```
Expected: `Analytics module smoke check passed.` twice.

- [ ] **Step 3: Confirm the create-once split end-to-end (the highest-risk invariant)**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python -c "import sys; sys.path.insert(0,'modules/analytics/.gigacode/hooks/gates'); import git_guard as g; \
print('file specs ALLOW:', g.run({'tool_input':{'file_path':'openspec/specs/cap/spec.md'}})['decision']); \
print('shell specs BLOCK:', g.run({'tool_input':{'command':'echo x > openspec/specs/cap/spec.md'}})['decision']); \
print('notebook gigacode BLOCK:', g.run({'tool_input':{'notebook_path':'.gigacode/hooks/router.py'}})['decision'])"
```
Expected: `file specs ALLOW: allow`, `shell specs BLOCK: block`, `notebook gigacode BLOCK: block`.

- [ ] **Step 4: Push to update PR #2**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git push 2>&1 | tail -2
git log --oneline 441e2c1..HEAD
```
Expected: push succeeds; the Task 1–4 commits listed.

- [ ] **Step 5: Record the dev-flow back-port follow-up**

These findings also affect dev-flow's `git_guard` (`#5` clean, `#6` tee, `#8` restore, `#11` checkout) and router (`#3` additionalContext). They are NOT fixed by this analytics-scoped plan. Note them for the dev-flow track (PR #1) — the four git-semantics fixes in Task 2 port over verbatim; `#3` needs the shared GigaCode runtime probe first.

---

## Self-Review Notes

- **Finding coverage:** #1/#2/#12/#13 → Task 1 (engine port); #5/#6/#8/#11 → Task 2; #4 → Task 3; #9 → Task 4; #10 → covered today by relative paths, and the Task-1 component-regex port removes the absolute-path false-block class for git_guard (gate_final_format's own relativization is noted but left out of scope as it does not misbehave under the relative paths the flow actually emits — flagged for the runtime-probe pass). #3 + the dev-flow back-port are explicitly deferred with reasons. The SQL-in-ddl/dml finding is declined (format gate ≠ bootstrap policy).
- **Highest-risk invariant guarded explicitly:** `gg_file_specs_allowed_p4` (Task 1) and Task 5 Step 3 prove file-tool writes to `openspec/specs/` stay allowed after the port — without this, the Phase-2 documentation agent could no longer write the capability spec.
- **Case-sensitivity:** Task 2 Step 1 removes the `.lower()` on `rest` so `-S`(--staged) ≠ `-s`(--source) and `-W` ≠ `-w`; existing long-flag and `-d/-D` checks remain correct (git long flags are lowercase as typed; `-D` was already enumerated).
- **No new gates, no router engine change:** only data (settings/config matchers) + gate logic. `router.py`, `_lib.py`, agents, skill, command, rules, openspec, templates untouched.
- **Tests are the spec:** each task instructs the implementer to fix the implementation until the concrete bypass tests pass (and to stop+report if a test looks wrong), because these are security-critical and the reference edits cannot be executed at planning time.
- **Placeholder scan:** all edits are exact old→new pairs or full functions; the only `<...>` tokens are illustrative paths inside test data / messages.
