# GigaCode Dev-Flow Phase 6: Enforcement Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Every red-team payload below is a test; the tests are the authoritative spec.

**Goal:** Close the confirmed red-team bypasses in the GigaCode enforcement layer — the git_guard single-token parser (Theme 1), the unprotected `.gigacode/**` self-tampering surface and run_command RCE (Theme 2), the hollow flow guarantees (Theme 4), and fragile path matching (Theme 5).

**Architecture:** The fixes harden existing gates (`git_guard`, `gate_spec_structure`, `validate_development_output`, `gate_build`), the shared `_lib`, and `router.py`; one new shared helper (`git_changed_paths`) lets Stop gates derive triggers from the working tree instead of the agent's message text. No new gate files. Every `gates/*.py` must stay under 10,000 chars (auto-checked by test_router.py).

**Tech Stack:** Python 3 stdlib, the existing offline test harness (`check()` + explicit `SystemExit`, fixtures via `GIGACODE_ROOT`), Windows-primary (PowerShell + Git Bash).

**Source of truth:** `docs/superpowers/reviews/2026-06-11-enforcement-red-team.md` — exact payloads and per-finding fixes.

---

## Cross-cutting principles (apply in every task)

- **Tests are the spec.** Each task ships a payload matrix: destructive/tamper payloads that MUST block (or ask), AND benign controls that MUST still allow. Do not weaken a fix to pass; do not over-block (a benign control failing is a regression).
- **Self-protect blocks; protected-path asks.** Writes to enforcement-owned paths (`.gigacode/**`) BLOCK (fail-closed). Writes to `PROTECTED_PATHS` (CI/secrets/infra) ASK, as today.
- **Suites must stay green.** After every task: `python scripts/test_gates.py`, `python scripts/test_router.py`, and `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1` all pass ("All N ... passed" / "Smoke check passed"). Counts drift upward as checks are added — expect "all passed", not exact numbers.
- **git rules.** NEVER `git add -A`/`git add .` in this worktree (untracked user file `docs/Текстовый документ.txt` must never be committed; the new red-team report and this plan are also untracked — stage only explicit file lists). Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. From PowerShell use single-quoted here-strings `@'...'@` with the closing `'@` at column 0 and NO double quotes inside the message body.

---

### Task 1: git_guard hardening — wrappers, chaining, quoting, broadened git coverage, non-git destruction, protected/self-protect shell writes

**Files:**
- Modify: `.gigacode/hooks/gates/git_guard.py` (rewrite the detection core; keep the gate contract `run(event)->dict` and `main()` unchanged)
- Test: `scripts/test_router.py` (git_guard is exercised at subprocess level here and in smoke-check.ps1)
- Test: `scripts/smoke-check.ps1` (extend the git_guard assertion block)

This is the largest task. git_guard currently (a) only recognizes git when `tokens[0].lower()=='git'`, (b) compares flags by exact string against quote-bearing tokens (`shlex posix=False`), (c) covers only 5 subcommands, (d) ignores non-git destructive verbs, and (e) never inspects shell-redirection/copy targets for protected paths. Findings C1, plus highs: quoting bypass, `-f`/`+ref`, uncovered subcommands, non-git tools, shell-redirection protected-path evasion, and the `.gigacode/**` self-tamper (the shell half).

- [ ] **Step 1: Add the failing payload matrix to `scripts/test_router.py`**

Append a new numbered block before the final `print`. `run_router` is the existing subprocess helper; git_guard runs on the `^(Bash|Shell)$` and `^(WriteFile|Edit)$` PreToolUse routes (safety_critical). Use the Bash route for command payloads and a WriteFile payload for the self-protect file_path check.

```python
    # 17. git_guard hardening — destructive git through wrappers/chaining/quoting MUST block
    GUARD_BLOCK = [
        # chaining / wrappers / env-prefix / abs-path / .exe (finding C1)
        "cd repo && git reset --hard",
        "true; git reset --hard",
        "(git reset --hard)",
        "env GIT_DIR=.git git reset --hard",
        "GIT_DIR=x git push --force origin main",
        "bash -c \"git reset --hard\"",
        "/usr/bin/git reset --hard",
        "git.exe reset --hard",
        # quoting (posix=False kept quote chars)
        "git reset \"--hard\"",
        "git \"reset\" --hard",
        "git push \"--force\"",
        "git clean \"-f\" \"-d\"",
        # short force flag + plus-refspec
        "git push -f",
        "git push -f origin main",
        "git push origin +main",
        # uncovered destructive subcommands
        "git update-ref -d refs/heads/main",
        "git reflog expire --expire=now --all",
        "git gc --prune=now",
        "git checkout -- src/",
        "git restore --worktree .",
        "git push origin --mirror",
        "git worktree remove --force wt",
        "git stash clear",
        "git filter-branch --force --all",
        # non-git repo destruction (Windows-primary)
        "Remove-Item -Recurse -Force .git",
        "rm -r .git",
        "cmd /c rmdir /s /q .git",
    ]
    for cmd in GUARD_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"guard_block::{cmd[:38]}", result["decision"] == "block", (cmd, result))

    # 18. Shell writes to protected / openspec-truth / enforcement paths
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "echo x > .gigacode/hooks/gates/git_guard.py"}})
    check("guard_shell_self_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "cp evil openspec/specs/auth/spec.md"}})
    check("guard_shell_openspec_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "printf x >> .env"}})
    check("guard_shell_protected_ask", result["decision"] in ("ask", "block"), result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "echo x > .github/workflows/deploy.yml"}})
    check("guard_shell_ci_ask", result["decision"] in ("ask", "block"), result)

    # 19. WriteFile/Edit to enforcement-owned paths MUST block (self-protection)
    for p in (".gigacode/hooks/gates/git_guard.py", ".gigacode/hooks/router.config.json",
              ".gigacode/quality-gates.json", ".gigacode/settings.json"):
        result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": p}})
        check(f"guard_self::{p[-24:]}", result["decision"] == "block", (p, result))

    # 20. Benign controls MUST still allow (no over-blocking regressions)
    GUARD_ALLOW = [
        "git status --short", "git diff", "git log --oneline -5", "git fetch origin",
        "git add .", "git commit -m wip", "git push origin feature/x",
        "git checkout -b feature/new", "git checkout main", "git switch main",
        "git restore --staged file.kt", "git stash", "git stash pop",
        "git reset --soft HEAD~1", "git reset file.kt", "git clean -n",
        "echo hello", "ls -la", "cat README.md", "cp a.txt b.txt", "rm build/tmp.o",
    ]
    for cmd in GUARD_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"guard_allow::{cmd[:38]}", result["decision"] == "allow", (cmd, result))
    # benign source write still allowed
    result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": "src/Foo.kt"}})
    check("guard_allow_src_write", result["decision"] == "allow", result)
```

- [ ] **Step 2: Run to verify the new checks fail**

Run: `python scripts/test_router.py`
Expected: FAIL on the first `guard_block::` (current git_guard allows wrapped/quoted/uncovered payloads).

- [ ] **Step 3: Rewrite the detection core of `.gigacode/hooks/gates/git_guard.py`**

Keep `run_git`, `current_branch`, `is_protected_branch`, `command_from_event`, the `main()` and the gate contract. Replace tokenizing + detection with the segment/basename-aware version below and extend `run()`. Reference implementation — make ALL Step 1 tests pass; do not weaken, do not over-block:

```python
PROTECTED_PATHS = [
    "**/.github/workflows/**", ".github/workflows/**",
    ".gitlab-ci.yml", "**/Jenkinsfile", "Jenkinsfile",
    "ci/**", "**/ci/**", "deploy/**", "deployment/**", "k8s/**", "helm/**",
    "terraform/**", "**/terraform/**", "infra/**", "**/infra/**",
    ".env", ".env.*", "**/.env", "**/.env.*", "secrets/**", "**/secrets/**",
    "config/prod/**", "config/production/**", "config/staging/**", "config/uat/**",
]
# Enforcement-owned: writes here BLOCK (fail-closed) — the layer must not be
# editable by the agent it constrains.
SELF_PROTECT = [".gigacode/**", ".gigacode"]
# openspec truth (mirror of gate_spec_structure.DENY_RE) for shell-write checks.
OPENSPEC_TRUTH_RE = re.compile(r"(^|/)openspec/(specs|changes/archive)/", re.IGNORECASE)

PREFIX_WRAPPERS = {"env", "nice", "ionice", "time", "stdbuf", "nohup",
                   "sudo", "doas", "timeout", "xargs"}
DASH_C_WRAPPERS = {"bash", "sh", "zsh", "dash", "ash", "ksh",
                   "cmd", "command", "powershell", "pwsh"}
DESTRUCTIVE_VERBS = {"rm", "rmdir", "del", "erase", "remove-item", "ri", "rd",
                     "truncate", "shred"}
WRITE_VERBS = {"cp", "mv", "copy", "move", "copy-item", "cpi", "move-item",
               "mi", "tee", "install", "rename-item", "rni"}
SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _norm(path):
    p = str(path).replace("\\", "/")
    p = os.path.normpath(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _strip_quotes(tok):
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    return tok


def _prog(tok):
    base = os.path.basename(_strip_quotes(tok).replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


def tokenize(command):
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return [_strip_quotes(t) for t in command.split()]


def to_segments(tokens):
    segs, cur = [], []
    for t in tokens:
        if t in SEPARATORS:
            if cur:
                segs.append(cur); cur = []
        else:
            cur.append(t.strip("()"))
    if cur:
        segs.append([t for t in cur if t])
    return [s for s in segs if s]


def peel(seg):
    """Drop env-assignments and wrappers; return list of leaf token-lists."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        if ENV_ASSIGN_RE.match(tok):
            i += 1; continue
        prog = _prog(tok)
        if prog in PREFIX_WRAPPERS:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1
            continue
        if prog in DASH_C_WRAPPERS:
            k = i + 1
            while k < len(seg) and seg[k].lower() not in ("-c", "-command", "/c"):
                k += 1
            rest = seg[k + 1:] if k < len(seg) else []
            if len(rest) == 1 and " " in rest[0]:
                return to_leaves(tokenize(rest[0]))
            return to_leaves_from_segments([rest]) if rest else []
        break
    return [seg[i:]] if seg[i:] else []


def to_leaves_from_segments(segs):
    leaves = []
    for s in segs:
        leaves.extend(peel(s))
    return leaves


def to_leaves(tokens):
    return to_leaves_from_segments(to_segments(tokens))


# --- git destructive coverage (broadened) ---
DESTRUCTIVE_SUBCMDS = {"update-ref", "reflog", "gc", "filter-branch", "filter-repo"}


def git_destructive(sub, rest):
    if sub == "reset" and "--hard" in rest:
        return "Blocked `git reset --hard`."
    if sub == "clean":
        combined = "".join(t.lstrip("-") for t in rest if t.startswith("-"))
        if "f" in combined and "d" in combined:
            return "Blocked destructive `git clean -fd`."
    if sub == "push":
        if any(t == "-f" or t.startswith("--force") for t in rest):
            return "Blocked force push."
        if "--delete" in rest or "--mirror" in rest:
            return "Blocked remote ref deletion / mirror push."
        if any(re.match(r"^[:+][^:\s]+$", t) for t in rest):
            return "Blocked force/delete by refspec."
    if sub == "branch" and any(t in ("-d", "-D", "--delete") for t in rest):
        return "Blocked local branch deletion."
    if sub == "remote" and rest[:1] == ["set-url"]:
        return "Blocked remote URL change."
    if sub in DESTRUCTIVE_SUBCMDS:
        return f"Blocked potentially irreversible `git {sub}`."
    if sub == "checkout" and "--" in rest:
        return "Blocked `git checkout --` (discards working-tree edits)."
    if sub == "restore" and "--worktree" in rest:
        return "Blocked `git restore --worktree` (discards working-tree edits)."
    if sub == "worktree" and rest[:1] == ["remove"]:
        return "Blocked `git worktree remove`."
    if sub == "stash" and rest[:1] == ["clear"]:
        return "Blocked `git stash clear`."
    return ""
```

Then a per-segment inspector and an updated `run()` (reference; adjust to pass tests):

```python
def write_targets(tokens):
    """Paths a segment writes to: redirection > / >> targets and copy/move dests."""
    targets, i = [], 0
    prog = _prog(tokens[0]) if tokens else ""
    while i < len(tokens):
        t = tokens[i]
        if t in (">", ">>") and i + 1 < len(tokens):
            targets.append(_strip_quotes(tokens[i + 1])); i += 2; continue
        if t.startswith(">") and len(t) > 1:
            targets.append(_strip_quotes(t.lstrip(">"))); i += 1; continue
        i += 1
    if prog in WRITE_VERBS:
        args = [a for a in tokens[1:] if not a.startswith("-")]
        if args:
            targets.append(_strip_quotes(args[-1]))  # destination
    return [_norm(p) for p in targets if p]


def classify_path(path):
    """Returns 'block' (self/openspec-truth), 'ask' (protected), or '' """
    p = _norm(path)
    if any(fnmatch.fnmatch(p, pat) or p == pat.rstrip("/*") for pat in SELF_PROTECT):
        return "block"
    if OPENSPEC_TRUTH_RE.search(p):
        return "block"
    if any(fnmatch.fnmatch(p, pat) for pat in PROTECTED_PATHS):
        return "ask"
    return ""


def inspect_command(command):
    for leaf in to_leaves(tokenize(command)):
        if not leaf:
            continue
        prog = _prog(leaf[0])
        if prog == "git":
            sub_idx = git_subcommand_index_from_leaf(leaf)
            if sub_idx >= 0:
                sub = _strip_quotes(leaf[sub_idx]).lower()
                rest = [_strip_quotes(t).lower() for t in leaf[sub_idx + 1:]]
                reason = git_destructive(sub, rest)
                if reason:
                    return "block", reason
        elif prog in DESTRUCTIVE_VERBS:
            joined = " ".join(_norm(_strip_quotes(t)) for t in leaf[1:])
            if ".git" in joined.split() or any(p == ".git" or p.startswith(".git/")
                                               for p in [_norm(t) for t in leaf[1:]]):
                return "block", "Blocked deletion of the git repository (.git)."
        worst = ""
        for tgt in write_targets(leaf):
            c = classify_path(tgt)
            if c == "block":
                return "block", f"Blocked shell write to enforcement/openspec path '{tgt}'."
            if c == "ask":
                worst = "ask"
        if worst == "ask":
            return "ask", "Shell write to a protected path requires explicit confirmation."
    return "", ""
```

`git_subcommand_index_from_leaf` is the existing `git_subcommand_index` adapted to a single leaf whose `[0]` is already a git program (basename-matched) — i.e. start scanning at index 1 skipping `GIT_GLOBAL_VALUE_FLAGS`. Keep `is_branch_write` but route it through the leaf parser so wrapped `commit`/`push`/`rebase` on protected branches are still caught.

Updated `run()`:

```python
def run(event):
    command = command_from_event(event)
    file_path = path_from_event(event)  # normalize via _norm inside path_from_event

    if command:
        decision, reason = inspect_command(command)
        if decision == "block":
            return {"decision": "block", "reason": reason + " Use an explicit human-approved recovery workflow."}
        branch = current_branch()
        if is_protected_branch(branch) and is_branch_write(command):
            return {"decision": "block", "reason": f"Blocked git write on protected branch '{branch}'. Use a feature/bugfix branch."}
        if decision == "ask":
            return {"decision": "ask", "reason": reason}

    if file_path:
        cls = classify_path(file_path)
        if cls == "block":
            return {"decision": "block", "reason": f"Write to enforcement-owned path '{file_path}' is blocked. Edit enforcement files via an out-of-band human workflow."}
        if cls == "ask" or protected_path(file_path):
            return {"decision": "ask", "reason": f"Protected path '{file_path}' requires explicit confirmation with risk explanation."}

    return {"decision": "allow"}
```

Update `path_from_event`/`protected_path` to normalize via `_norm` (collapse `//`, `..`, `./`). Keep the file < 10,000 chars — if tight, drop comments, not coverage.

- [ ] **Step 4: Run tests to verify pass**

Run: `python scripts/test_router.py`
Expected: all `guard_block::`, `guard_self::`, `guard_shell_*`, and `guard_allow::` checks pass; final "All N router checks passed".

- [ ] **Step 5: Extend `scripts/smoke-check.ps1` git_guard block**

After the existing `$configBypass` assertion, add two representative end-to-end checks (match the file's `python .gigacode/hooks/gates/git_guard.py` piping style + `throw` on miss):

```powershell
$wrapBypass = '{"tool_input":{"command":"cd . && git reset --hard HEAD~5"}}' | python .gigacode/hooks/gates/git_guard.py
if ($wrapBypass -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block chained git reset --hard"
}
$selfEdit = '{"tool_name":"WriteFile","tool_input":{"file_path":".gigacode/hooks/gates/git_guard.py"}}' | python .gigacode/hooks/gates/git_guard.py
if ($selfEdit -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block self-edit of enforcement file"
}
```

- [ ] **Step 6: Run both suites + smoke**

Run: `python scripts/test_router.py`, `python scripts/test_gates.py`, `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1`
Expected: all pass; "Smoke check passed".

- [ ] **Step 7: Commit**

```bash
git add .gigacode/hooks/gates/git_guard.py scripts/test_router.py scripts/smoke-check.ps1
git commit -m "Harden git_guard: wrappers, chaining, quoting, broadened coverage, shell-write path enforcement, .gigacode self-protect"
```

---

### Task 2: Path normalization & case-insensitivity for the spec/existing-code gates

**Files:**
- Modify: `.gigacode/hooks/gates/_lib.py` (`path_from_event` normalizes)
- Modify: `.gigacode/hooks/gates/gate_spec_structure.py` (`DENY_RE`/`CHANGE_RE` case-insensitive)
- Test: `scripts/test_gates.py`

Findings: case-variant (`OpenSpec/Specs`), redundant separator (`openspec//specs`), dot-dot traversal (`openspec/changes/../specs`) all bypass `DENY_RE`.

- [ ] **Step 1: Add failing checks to `test_gates.py` `test_spec_structure()`**

After the existing `ss_pre_specs_block` check, add:

```python
        for variant in ("OpenSpec/Specs/payments/spec.md",
                        "openspec//specs/payments/spec.md",
                        "openspec/changes/../specs/payments/spec.md",
                        "./openspec/specs/payments/spec.md"):
            result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": variant}})
            check(f"ss_pre_variant::{variant[:30]}", result["decision"] == "block", (variant, result))
        # benign nearby path still allowed
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/changes/my-change/proposal.md"}})
        check("ss_pre_change_still_allow", result["decision"] == "allow", result)
```

- [ ] **Step 2: Run → FAIL** (`python scripts/test_gates.py`): variants currently allowed.

- [ ] **Step 3: Normalize in `_lib.path_from_event`**

Replace each `return value.replace("\\", "/")` in `path_from_event` (both the top-level loop and the tool_input loop) with a normalized form:

```python
def _norm_path(value):
    p = value.replace("\\", "/")
    p = os.path.normpath(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p
```
and `return _norm_path(value)`. `os.path.normpath` collapses `//`, `/./`, and resolves `..` so `openspec/changes/../specs/x` becomes `openspec/specs/x`.

- [ ] **Step 4: Case-insensitive deny in `gate_spec_structure.py`**

Line 18-19:
```python
DENY_RE = re.compile(r"(^|/)openspec/(specs|changes/archive)/", re.IGNORECASE)
CHANGE_RE = re.compile(r"(^|/)openspec/changes/([A-Za-z0-9][A-Za-z0-9._-]*)/", re.IGNORECASE)
```

- [ ] **Step 5: Run → PASS** (`test_gates.py`), then `test_router.py` and smoke ps1 — all green. (gate_existing_code reads the same `_lib.path_from_event`, so it inherits normalization; confirm its tests still pass.)

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/gates/_lib.py .gigacode/hooks/gates/gate_spec_structure.py scripts/test_gates.py
git commit -m "Normalize and case-fold paths before spec write-deny matching"
```

---

### Task 3: Harden `_lib.run_command` exe resolution + harness deny backstop for `.gigacode`

**Files:**
- Modify: `.gigacode/hooks/gates/_lib.py` (`run_command` exe resolution)
- Modify: `.gigacode/settings.json` (`permissions.deny`)
- Test: `scripts/test_gates.py` (`test_lib`)

Finding (critic-surfaced, confirmed high): `run_command` does `shutil.which(tokens[0]) or shutil.which(tokens[0], path=root())` then falls back to `os.path.join(root(), tokens[0])` — a planted `gradlew.bat` at repo root is executed inside the gate process (RCE), and `exit 0` makes lint/build pass. Fix: resolve a bare command name ONLY against the trusted system PATH; never elevate a repo-relative file to an executable. Explicit `./x`/absolute paths remain allowed.

- [ ] **Step 1: Add failing checks to `test_gates.py` `test_lib()`**

```python
    with fixture_root() as fix:
        # planted repo-root script must NOT be auto-resolved as a bare command
        with open(os.path.join(fix, "gradlew.bat"), "w", encoding="utf-8") as h:
            h.write("@echo off\nexit /b 0\n")
        rc, tail = lib.run_command("gradlew", 5)
        check("lib_no_reporoot_exe", rc == -1, (rc, tail))
        # explicit relative path still resolves
        with open(os.path.join(fix, "ok.bat"), "w", encoding="utf-8") as h:
            h.write("@echo off\nexit /b 0\n")
        rc, tail = lib.run_command("./ok.bat", 5)
        check("lib_explicit_relpath_runs", rc == 0, (rc, tail))
```

- [ ] **Step 2: Run → FAIL** (`test_gates.py`): bare `gradlew` currently resolves to the planted file (rc 0).

- [ ] **Step 3: Fix `run_command` exe resolution in `_lib.py`**

Replace the resolution block:
```python
    exe = shutil.which(tokens[0]) or shutil.which(tokens[0], path=root())
    if not exe:
        candidate = os.path.join(root(), tokens[0])
        if os.path.exists(candidate):
            exe = candidate
        else:
            return -1, f"command not found: {tokens[0]}"
```
with:
```python
    name = tokens[0]
    is_explicit = name.startswith((".", "/", "\\")) or os.path.isabs(name) \
        or ("/" in name) or ("\\" in name)
    if is_explicit:
        # explicit path: resolve relative to root(), allow it
        candidate = name if os.path.isabs(name) else os.path.join(root(), name)
        exe = candidate if os.path.exists(candidate) else shutil.which(name)
    else:
        # bare name: ONLY the trusted system PATH — never the repo root, so a
        # planted gradlew.bat/mvnw at repo root cannot be elevated to an exe.
        exe = shutil.which(name)
    if not exe:
        return -1, f"command not found: {name}"
```

- [ ] **Step 4: Harness deny backstop in `settings.json`**

Add to `permissions.deny` (so the host BLOCKS, not merely asks, edits to enforcement files even if a gate is somehow bypassed):
```json
    "Edit(.gigacode/**)",
    "Write(.gigacode/**)",
    "Edit(.gigacode/settings.json)",
    "Edit(.gigacode/quality-gates.json)"
```
(Append inside the existing `deny` array; keep JSON valid.)

- [ ] **Step 5: Run all suites + smoke + JSON validity**

`python -m json.tool .gigacode/settings.json`, `python scripts/test_gates.py`, `python scripts/test_router.py`, `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1` — all pass.

- [ ] **Step 6: Commit**

```bash
git add .gigacode/hooks/gates/_lib.py .gigacode/settings.json scripts/test_gates.py
git commit -m "Resolve bare gate commands only on system PATH; deny .gigacode writes at the harness level"
```

---

### Task 4: Distrust the Stop block-budget state file

**Files:**
- Modify: `.gigacode/hooks/router.py` (`load_state`, `apply_stop_budget`)
- Test: `scripts/test_router.py`

Finding: `router-state.json` is agent-writable and pre-seeding `{"stop:default": 99}` makes the first real Stop block degrade to allow (count 100 > budget 2 on the first block).

- [ ] **Step 1: Add a failing check to `test_router.py`**

Use the existing `temp_hooks_copy()` to get an isolated state dir, pre-seed the state file, then assert the first block still blocks.

```python
    # 21. Pre-seeded budget counter must NOT pre-exhaust the budget
    tmp4, tmp_router4, _ = temp_hooks_copy()
    state_path = os.path.join(tmp4, "logs", "router-state.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump({"stop:t-seed": 99}, handle)
    payload = {"last_assistant_message": "Complete in docs/development/sample-task/", "session_id": "t-seed"}
    result = run_router("Stop", payload, router=tmp_router4)
    check("budget_preseed_still_blocks", result["decision"] == "block", result)
    shutil.rmtree(tmp4, ignore_errors=True)
```
(Note: `temp_hooks_copy` copies `.gigacode/hooks`; the state path is `hooks/../logs` per router.py `LOGS_DIR`. Verify the actual STATE_PATH location in the temp copy and seed the right file — adjust the path in the test to match `router.py`'s `STATE_PATH` resolved against the temp hooks dir.)

- [ ] **Step 2: Run → FAIL** (first block degrades to allow).

- [ ] **Step 3: Clamp in `router.py`**

In `load_state`, sanitize values; in `apply_stop_budget`, cap the prior count at the budget so a seeded huge value cannot pre-exhaust:

```python
def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # distrust agent-writable counters: keep only sane small ints
    return {k: v for k, v in raw.items() if isinstance(v, int) and 0 <= v <= 1000}
```
and in `apply_stop_budget`, replace `count = state.get(key, 0) + 1` with:
```python
    budget = config.get("stop_block_budget", 2)
    count = min(state.get(key, 0), budget) + 1
```
(move the `budget` lookup above the count computation). Now a seeded 99 clamps to `min(99, 2) + 1 = 3`; the first genuine block still blocks (3 > 2 is False on the first block → wait: count becomes 3 immediately). Adjust: clamp prior to `budget - 1` so the FIRST block after a reset always blocks — `count = min(state.get(key, 0), budget - 1) + 1` → `min(99,1)+1 = 2`, and `2 > 2` is False → block; the genuine third consecutive still degrades. Verify against the existing `stop_budget_*` checks so real degradation after 2 honest blocks is preserved.

- [ ] **Step 4: Run → PASS**, and confirm existing `stop_budget_first_block`/`second_block`/`third_degrades`/`reset`/`restart` checks all still pass.

- [ ] **Step 5: Commit**

```bash
git add .gigacode/hooks/router.py scripts/test_router.py
git commit -m "Clamp the Stop block-budget counter so a pre-seeded state file cannot pre-exhaust it"
```

---

### Task 5: Flow integrity — derive Stop triggers from the working tree and require an OpenSpec change when code changed

**Files:**
- Modify: `.gigacode/hooks/gates/_lib.py` (add `git_changed_paths`)
- Modify: `.gigacode/hooks/gates/gate_spec_structure.py` (Stop branch)
- Modify: `.gigacode/hooks/gates/validate_development_output.py` (trigger from disk)
- Modify: `.gigacode/hooks/gates/gate_build.py` (trigger from working tree)
- Test: `scripts/test_gates.py`

Findings: every Stop guarantee is unlocked by NOT naming `docs/development/`/`openspec/changes` in the final message; and nothing forces an OpenSpec change to exist when code ships. Fix: trigger from `git status --porcelain` (real changed files), not message text; and block at Stop when code-bearing files changed but no active change exists.

- [ ] **Step 1: Add `git_changed_paths` to `_lib.py`**

```python
def git_changed_paths():
    """Tracked+untracked changed paths (forward-slash, repo-relative), or []."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root(), text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    paths = []
    for line in proc.stdout.splitlines():
        p = line[3:].strip().strip('"')
        if " -> " in p:  # rename
            p = p.split(" -> ", 1)[1]
        if p:
            paths.append(p.replace("\\", "/"))
    return paths


CODE_SUFFIXES = (".kt", ".kts", ".java", ".py", ".ts", ".tsx", ".js", ".jsx",
                 ".go", ".rs", ".cs", ".scala")


def changed_code_files():
    return [p for p in git_changed_paths()
            if p.endswith(CODE_SUFFIXES)
            and not p.startswith(("openspec/", "docs/", ".gigacode/"))]
```

- [ ] **Step 2: Add failing checks to `test_gates.py`**

These need a git repo fixture with a staged code change and no active change. Reuse the `init_git` helper from `test_existing_code` (git init + add). Add a `test_flow_integrity()` and call it from `main()`:

```python
def test_flow_integrity():
    gate = load_gate("gate_spec_structure")
    with fixture_root() as fix:
        # a changed code file with NO active openspec change -> Stop must block
        srcdir = os.path.join(fix, "src"); os.makedirs(srcdir)
        with open(os.path.join(srcdir, "Foo.kt"), "w", encoding="utf-8") as h:
            h.write("class Foo\n")
        init_git(fix)  # git init + add -A so Foo.kt is a tracked change
        # message does NOT mention the trigger paths
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "Done."})
        check("fi_code_without_change_blocks", result["decision"] == "block", result)
    with fixture_root() as fix:
        # no code change at all -> Stop allows (no false block)
        init_git(fix)
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "Done."})
        check("fi_no_change_allows", result["decision"] == "allow", result)
```
(`init_git` runs `git init` + `git add -A` inside the TEMP FIXTURE — that is fine; the `git add -A` ban applies only to the real worktree, never to throwaway fixture repos.)

- [ ] **Step 3: Run → FAIL** (Stop currently allows when the message omits the trigger).

- [ ] **Step 4: Rewrite the `gate_spec_structure.py` Stop branch**

Replace the message-text gate with a working-tree gate, and add the require-a-change rule:

```python
    if name == "Stop":
        code_changed = bool(_lib.changed_code_files())
        changes = active_changes()
        if code_changed and not changes:
            return {"decision": "block", "reason": (
                "Stop blocked: production code changed but no openspec/changes/<id>/ "
                "exists. Create and validate an OpenSpec change before finishing "
                "(see rules/openspec.md).")}
        if not changes:
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
```

- [ ] **Step 5: Trigger `validate_development_output` and `gate_build` from the working tree**

`validate_development_output.py`: replace the `if "docs/development/" not in message...: allow` short-circuit so the gate runs whenever there are changed code files OR a `docs/development/<slug>/` dir exists on disk; resolve the task dir from disk (scan `docs/development/*/`) instead of only from the message. Keep the placeholder/evidence checks. If there are no changes and no dev dir, allow (no false block).

`gate_build.py`: replace the PR-readiness message check
```python
    message = _lib.message_from_event(event).replace("\\", "/")
    if "docs/development/" not in message and "openspec/changes" not in message:
        return {"decision": "allow"}
```
with a working-tree trigger:
```python
    if not _lib.changed_code_files():
        return {"decision": "allow"}
```
(so the build runs whenever code actually changed, regardless of message phrasing). Keep the existing empty-command silent-allow and timeout handling.

- [ ] **Step 6: Run all suites + smoke**

`python scripts/test_gates.py`, `python scripts/test_router.py`, `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1` — all green. Pay attention to existing Stop tests in test_router.py (`stop_missing_artifacts_block` etc.): they drive the router at subprocess level in the REAL worktree, where `git status` reflects actual changes — if a test depends on message-text triggering, update it to the new working-tree behavior or scope it with a fixture. Adjust tests, not the security intent.

- [ ] **Step 7: Commit**

```bash
git add .gigacode/hooks/gates/_lib.py .gigacode/hooks/gates/gate_spec_structure.py .gigacode/hooks/gates/validate_development_output.py .gigacode/hooks/gates/gate_build.py scripts/test_gates.py
git commit -m "Derive Stop-gate triggers from the working tree and require an OpenSpec change when code changed"
```

---

### Task 6: Final hardening review

Controller-level (not an implementation task): dispatch a final reviewer over the whole Phase 6 diff (from the commit before Task 1 to HEAD), re-checking each closed finding against `docs/superpowers/reviews/2026-06-11-enforcement-red-team.md` (does the payload now block? any new over-block regression? any gate over 10k chars?), then run the full offline verification:

- `python scripts/test_gates.py`
- `python scripts/test_router.py`
- `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1`
- `bash scripts/smoke-check.sh`

Apply APPROVED-with-recommendations fixes inline; commit. Note in the commit/PR which red-team findings remain open by design (advisory-only gates, env-var inheritance requiring host compromise, harness auto-approve of "ask") so the residual surface is documented.
