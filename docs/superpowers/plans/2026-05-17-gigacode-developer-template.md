# GigaCode Developer Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Git-ready GigaCode project template for enterprise developer workflows that supports feature development and bug fixing in plan-only and implement modes.

**Architecture:** The repository is a self-contained project root. GigaCode discovers project settings, skills, agents, commands, and hooks under `.gigacode/`, while developer workflow artifacts are Markdown files under `docs/development/<task-slug>/`. Git safety is enforced both by workflow instructions and by hook scripts that block protected branches, destructive git operations, unsafe pushes, and protected infrastructure edits.

**Tech Stack:** GigaCode/Qwen Code-compatible JSON settings, Markdown skill/agent/command files with YAML frontmatter, Python 3 hook scripts, PowerShell and POSIX shell smoke checks, Markdown templates.

---

## File Structure

- Create `.gigacode/settings.json`: project settings, hook wiring, safe permissions, UI defaults.
- Create `.gigacode/skills/development-flow/SKILL.md`: shared workflow skill for feature and bug development.
- Create `.gigacode/agents/*.md`: seven focused subagents, each below 10,000 characters.
- Create `.gigacode/hooks/git_guard.py`: enterprise git and protected-path guard hook.
- Create `.gigacode/hooks/preflight_check.py`: validates developer workflow prompts.
- Create `.gigacode/hooks/validate_development_output.py`: validates Markdown artifacts and completion claims.
- Create `.gigacode/commands/develop-feature.md`: feature workflow slash command.
- Create `.gigacode/commands/fix-bug.md`: bug workflow slash command.
- Create `docs/templates/development-plan.md`: reusable Markdown artifact contract.
- Create `docs/development/.gitkeep`: keeps output directory in git.
- Create `rules/development-flow.md`: shared development workflow rules.
- Create `rules/git-safety.md`: protected branches, protected paths, and forbidden git operations.
- Create `rules/branch-naming.md`: enterprise-safe branch naming guidance.
- Create `scripts/smoke-check.ps1`: Windows smoke check.
- Create `scripts/smoke-check.sh`: Linux smoke check.
- Create or replace `README.md`: quick start and operating guide.
- Modify `.gitignore`: local/runtime ignores.

## Task 1: Repository Skeleton, Templates, and Rules

**Files:**
- Modify: `.gitignore`
- Create: `docs/development/.gitkeep`
- Create: `docs/templates/development-plan.md`
- Create: `rules/development-flow.md`
- Create: `rules/git-safety.md`
- Create: `rules/branch-naming.md`

- [ ] **Step 1: Create directories**

Run:

```powershell
New-Item -ItemType Directory -Force .gigacode, .gigacode\skills\development-flow, .gigacode\agents, .gigacode\hooks, .gigacode\commands, docs\development, docs\templates, rules, scripts | Out-Null
```

Expected: command exits `0`.

- [ ] **Step 2: Update `.gitignore`**

Write `.gitignore` with this content:

```gitignore
.env
.env.*
!.env.example
__pycache__/
*.pyc
.gigacode/tmp/
.gigacode/logs/
docs/development/*/tmp/
repomix-output.*
graphify-output/
```

- [ ] **Step 3: Create `docs/development/.gitkeep`**

Create an empty file:

```powershell
New-Item -ItemType File -Force docs\development\.gitkeep | Out-Null
```

- [ ] **Step 4: Create `docs/templates/development-plan.md`**

Write:

```markdown
# Development Task Template

## Context

- Task type:
- Mode:
- Task slug:
- Source request:
- Related tickets or docs:

## Project Intelligence

- Analytics:
- Repomix:
- Graphify:
- External context:

## Scope

### Included

- List confirmed in-scope behavior, files, modules, or user journeys.

### Excluded

- List explicitly out-of-scope behavior, files, modules, or user journeys.

## Impact Map

- Entry points:
- Upstream callers:
- Downstream dependencies:
- Data boundaries:
- Configuration:
- Tests:
- Unknown areas:

## Plan

1. Describe each implementation or investigation step in execution order.

## Verification Strategy

- Required commands:
- Manual checks:
- Skipped checks and reasons:

## Rollout and Rollback

- Rollout notes:
- Rollback notes:

## Review Notes

- Changed areas:
- Risk notes:
- Follow-up tasks:
```

- [ ] **Step 5: Create `rules/development-flow.md`**

Write:

```markdown
# Development Flow Rules

Use this workflow for feature development and bug fixing.

Operating modes:

- `plan-only`: analyze and write Markdown development artifacts without editing source code.
- `implement`: analyze, verify git safety, make scoped edits, verify behavior, and prepare PR-ready notes.

Required context order:

1. Read project analytics when present.
2. Use Repomix output when present.
3. Use Graphify output when present.
4. Fall back to direct repository inspection and manual impact mapping when optional tools are unavailable.
5. Confirm current behavior from live code before editing files.

Implementation invariants:

- Classify the request as feature, bug, or unclear.
- Ask for clarification when scope or safety is unclear.
- Map relevant code before editing.
- Protect existing user changes.
- Work on a safe task branch before source edits.
- Keep edits scoped to the request.
- Add or update tests proportionate to risk.
- Record verification evidence before claiming completion.
- Do not auto-commit or auto-push in v1.
```

- [ ] **Step 6: Create `rules/git-safety.md`**

Write:

```markdown
# Git Safety Rules

Protected branch patterns:

- `main`
- `master`
- `develop`
- `development`
- `release`
- `release/*`
- `hotfix/*`
- `production`
- `prod`
- `staging`
- `uat`

Forbidden git operations by default:

- `git reset --hard`
- `git clean -fd`
- `git clean -ffd`
- `git checkout -- <path>`
- `git restore <path>` when it discards uncommitted work
- `git push --force`
- `git push --force-with-lease`
- deleting local or remote branches
- changing remote URLs
- committing directly to protected branches
- pushing directly to protected branches

Protected paths:

- `.github/workflows/**`
- `.gitlab-ci.yml`
- `Jenkinsfile`
- `ci/**`
- `deploy/**`
- `deployment/**`
- `k8s/**`
- `helm/**`
- `terraform/**`
- `infra/**`
- `.env`
- `.env.*`
- `secrets/**`
- `config/prod/**`
- `config/production/**`
- `config/staging/**`
- `config/uat/**`

Changes to protected paths require explicit human confirmation that names the files and explains the risk.
```

- [ ] **Step 7: Create `rules/branch-naming.md`**

Write:

```markdown
# Branch Naming Rules

Recommended branch formats:

- `feature/<task-slug>`
- `bugfix/<task-slug>`
- `fix/<task-slug>`

Examples:

- `feature/payment-retry`
- `bugfix/card-blocking-timeout`
- `fix/null-customer-status`

Use lowercase ASCII, digits, and hyphens. Avoid spaces, ticket-only branch names, and names that look like protected branches.
```

- [ ] **Step 8: Verify skeleton**

Run:

```powershell
Test-Path docs\templates\development-plan.md
Test-Path rules\development-flow.md
Test-Path rules\git-safety.md
Test-Path rules\branch-naming.md
```

Expected: all commands print `True`.

- [ ] **Step 9: Commit skeleton**

Run:

```powershell
git add .gitignore docs/development/.gitkeep docs/templates/development-plan.md rules/development-flow.md rules/git-safety.md rules/branch-naming.md
git commit -m "Add developer template skeleton"
```

Expected: commit succeeds on a non-protected implementation branch.

## Task 2: Settings, Skill, and Commands

**Files:**
- Create: `.gigacode/settings.json`
- Create: `.gigacode/skills/development-flow/SKILL.md`
- Create: `.gigacode/commands/develop-feature.md`
- Create: `.gigacode/commands/fix-bug.md`

- [ ] **Step 1: Write `.gigacode/settings.json`**

Create:

```json
{
  "ui": {
    "showCitations": true,
    "showLineNumbers": true,
    "hideTips": true,
    "shellOutputMaxLines": 30
  },
  "permissions": {
    "allow": [
      "Read",
      "Bash(git status*)",
      "Bash(git branch*)",
      "Bash(git diff*)",
      "Bash(git log*)",
      "Bash(git rev-list*)",
      "Bash(rg*)",
      "Bash(python .gigacode/hooks/*)",
      "Edit(docs/development/**)"
    ],
    "ask": [
      "Edit",
      "Bash(git add*)",
      "Bash(git commit*)",
      "Bash(mvn*)",
      "Bash(npm*)",
      "Bash(pytest*)",
      "Bash(gradle*)",
      "Bash(cargo*)"
    ],
    "deny": [
      "Read(.env)",
      "Read(.env.*)",
      "Bash(git reset --hard*)",
      "Bash(git clean -fd*)",
      "Bash(git clean -ffd*)",
      "Bash(git push --force*)",
      "Bash(git push --force-with-lease*)",
      "Bash(git remote set-url*)",
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
          {
            "type": "command",
            "command": "python .gigacode/hooks/preflight_check.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python .gigacode/hooks/git_guard.py"
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
            "command": "python .gigacode/hooks/validate_development_output.py"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Write `.gigacode/skills/development-flow/SKILL.md`**

Create:

```markdown
---
name: development-flow
description: MUST BE USED for GigaCode developer workflows that plan or implement features and bug fixes with enterprise git safety, project context, verification, and PR-ready Markdown artifacts.
---

# Development Flow

Use this skill when the developer asks to plan, implement, fix, debug, or prepare a code change.

## Modes

- `plan-only`: analyze, map impact, and write Markdown artifacts without editing source code.
- `implement`: run the full plan-only flow, pass git safety checks, make scoped edits, verify behavior, and prepare PR-ready notes.

Default to `plan-only` when the requested mode is unclear, high-risk, or missing acceptance criteria.

## Request Types

- Feature work starts from a desired capability, behavior, or technical improvement.
- Bug work starts from an observed failure, regression, incident, error, failing test, or mismatch between expected and actual behavior.
- If the request type is unclear, ask before planning implementation.

## Required Context

Before planning or editing:

1. Read project analytics when present.
2. Use Repomix output when present.
3. Use Graphify output or the Graphify skill when present.
4. If Repomix is absent, inspect the repository directly with file listing and targeted search.
5. If Graphify is absent, build a manual impact map from entry points, imports, call sites, tests, and configuration.
6. Confirm current behavior from live files before editing.

Record missing optional context in `docs/development/<task-slug>/context.md`.

## Git Safety

Before source edits in implement mode:

1. Run `git status --short`.
2. Run `git branch --show-current`.
3. Run `git rev-list --left-right --count HEAD...@{u}` when upstream exists.
4. Stop on protected branches.
5. Stop when unrelated user changes overlap with planned edits.
6. Do not commit or push by default.

Never run destructive git operations, force pushes, branch deletion, or remote URL changes unless the user gives explicit instruction outside the normal workflow.

## Feature Flow

1. Clarify feature goal, acceptance criteria, included scope, excluded scope, and constraints.
2. Collect project context.
3. Map impact.
4. Write plan and verification strategy.
5. Stop for clarification if scope or safety is unclear.
6. In implement mode, edit only after git guard passes.
7. Verify behavior.
8. Write PR-ready notes.

## Bug Flow

1. Clarify symptom, expected behavior, actual behavior, reproduction steps, affected environment, severity, and workarounds.
2. Collect project context.
3. Plan reproduction.
4. Identify likely root cause.
5. Write fix plan and regression strategy.
6. Stop for clarification if reproduction or impact is unclear.
7. In implement mode, edit only after git guard passes.
8. Verify the regression fix first, then broader checks.
9. Write PR-ready notes.

## Output Files

Write Markdown artifacts under `docs/development/<task-slug>/`:

- `context.md`
- `plan.md`
- `implementation.md`
- `verification.md`
- `pr-summary.md`

Plan-only artifacts must clearly state when implementation or verification was not executed.

## Agents

Use these project agents when appropriate:

1. `dev-intake`
2. `project-context`
3. `code-map`
4. `implementation-plan`
5. `coder`
6. `test-review`
7. `pr-readiness`

Each agent file and role description must remain below 10,000 characters.
```

- [ ] **Step 3: Write `.gigacode/commands/develop-feature.md`**

Create:

```markdown
---
description: Plan or implement a feature through the enterprise developer workflow.
---

Use the `development-flow` skill.

Run the feature workflow for these user arguments:

{{args}}

Follow this sequence:

1. Identify mode: `plan-only` unless implement mode is explicit.
2. Clarify feature goal, acceptance criteria, included scope, excluded scope, and constraints.
3. Inspect analytics, Repomix, and Graphify when available.
4. Use documented fallbacks when optional context is unavailable.
5. Map impacted code before planning edits.
6. In implement mode, run git safety checks before editing source files.
7. Produce Markdown artifacts under `docs/development/<task-slug>/`.
8. Record verification evidence before claiming completion.
9. Do not auto-commit or auto-push.
```

- [ ] **Step 4: Write `.gigacode/commands/fix-bug.md`**

Create:

```markdown
---
description: Investigate, plan, or implement a bug fix through the enterprise developer workflow.
---

Use the `development-flow` skill.

Run the bug workflow for these user arguments:

{{args}}

Follow this sequence:

1. Identify mode: `plan-only` unless implement mode is explicit.
2. Clarify symptom, expected behavior, actual behavior, reproduction evidence, affected environment, severity, and workarounds.
3. Inspect analytics, Repomix, and Graphify when available.
4. Use documented fallbacks when optional context is unavailable.
5. Map impacted code and likely failing paths before planning edits.
6. In implement mode, run git safety checks before editing source files.
7. Prefer regression evidence before making the fix when feasible.
8. Produce Markdown artifacts under `docs/development/<task-slug>/`.
9. Record verification evidence before claiming completion.
10. Do not auto-commit or auto-push.
```

- [ ] **Step 5: Verify settings and frontmatter**

Run:

```powershell
python -m json.tool .gigacode/settings.json
Select-String .gigacode/skills/development-flow/SKILL.md -Pattern '^---$'
Select-String .gigacode/commands/develop-feature.md -Pattern '^---$'
Select-String .gigacode/commands/fix-bug.md -Pattern '^---$'
```

Expected: JSON validation exits `0`; each Markdown file has two frontmatter boundary lines.

- [ ] **Step 6: Commit settings, skill, and commands**

Run:

```powershell
git add .gigacode/settings.json .gigacode/skills/development-flow/SKILL.md .gigacode/commands/develop-feature.md .gigacode/commands/fix-bug.md
git commit -m "Add developer workflow skill and commands"
```

Expected: commit succeeds on a non-protected implementation branch.

## Task 3: Project Subagents

**Files:**
- Create: `.gigacode/agents/dev-intake.md`
- Create: `.gigacode/agents/project-context.md`
- Create: `.gigacode/agents/code-map.md`
- Create: `.gigacode/agents/implementation-plan.md`
- Create: `.gigacode/agents/coder.md`
- Create: `.gigacode/agents/test-review.md`
- Create: `.gigacode/agents/pr-readiness.md`

- [ ] **Step 1: Create `.gigacode/agents/dev-intake.md`**

Write:

```markdown
---
name: dev-intake
description: MUST BE USED at the start of developer workflows to classify feature versus bug work, determine plan-only versus implement mode, and identify missing scope or safety inputs.
model: inherit
approvalMode: plan
---

# Dev Intake Agent

Clarify the request before planning or implementation.

Inputs:

- User request.
- Requested command: `/develop-feature` or `/fix-bug`.
- Any ticket, log, document, or acceptance criteria provided by the user.

Outputs:

- Task type: `feature`, `bug`, or `unclear`.
- Mode: `plan-only` or `implement`.
- Task slug using lowercase ASCII, digits, and hyphens.
- Included scope and excluded scope.
- Missing inputs.
- Safety blockers.

Feature intake requires goal, behavior, acceptance criteria, and constraints.

Bug intake requires symptom, expected behavior, actual behavior, reproduction evidence or reason it is unavailable, affected environment when known, and severity when known.

Default to `plan-only` if scope, mode, or safety is unclear.

Do not edit source files. Do not commit. Do not push.
```

- [ ] **Step 2: Create `.gigacode/agents/project-context.md`**

Write:

```markdown
---
name: project-context
description: MUST BE USED before planning developer changes to collect analytics, Repomix, Graphify, local docs, and external context when available, with explicit fallbacks when optional tools are missing.
model: inherit
approvalMode: plan
---

# Project Context Agent

Collect project intelligence before implementation planning.

Look for:

- `docs/features/**`
- `docs/analysis/**`
- `docs/architecture/**`
- `docs/incidents/**`
- ADRs or decision records
- Repomix output files
- Graphify output directories or reports
- README and build files
- related tickets or external context provided by the user

Fallbacks:

- If analytics are absent, continue with code, tests, local docs, and user-provided context.
- If Repomix is absent, use direct repository inspection with file listing and targeted search.
- If Graphify is absent, use manual impact mapping from entry points, imports, call sites, tests, and configuration.

Output a concise context summary for `docs/development/<task-slug>/context.md`:

- Sources used.
- Sources unavailable.
- Relevant facts.
- Assumptions.
- Open questions.
- Risk areas.

Do not edit source files. Do not commit. Do not push.
```

- [ ] **Step 3: Create `.gigacode/agents/code-map.md`**

Write:

```markdown
---
name: code-map
description: MUST BE USED before source edits to map impacted code, tests, integrations, data boundaries, and unknown areas for a feature or bug workflow.
model: inherit
approvalMode: plan
---

# Code Map Agent

Map the implementation surface before editing.

Inputs:

- Intake summary.
- Project context summary.
- User-provided evidence.
- Live repository files.

Map:

- Entry points.
- Routes, controllers, handlers, commands, jobs, or UI surfaces.
- Upstream callers.
- Downstream dependencies.
- APIs, queues, events, integrations, and storage.
- Configuration and environment assumptions.
- Existing tests.
- Missing or unclear coverage.

Use live files for final confirmation even when Repomix or Graphify are available.

Output a compact impact map with file paths and reasons each area matters.

Do not edit source files. Do not commit. Do not push.
```

- [ ] **Step 4: Create `.gigacode/agents/implementation-plan.md`**

Write:

```markdown
---
name: implementation-plan
description: MUST BE USED after context and code mapping to produce a scoped implementation plan, test strategy, rollout notes, rollback notes, and human checkpoints.
model: inherit
approvalMode: plan
---

# Implementation Plan Agent

Create the task plan after intake, context discovery, and code mapping.

Output for `docs/development/<task-slug>/plan.md`:

- Summary.
- Scope.
- Impacted files or modules.
- Step-by-step implementation plan.
- Test strategy.
- Rollout notes.
- Rollback notes.
- Risks.
- Open questions.

Feature plans must connect steps to acceptance criteria.

Bug plans must connect steps to symptom, root-cause hypothesis, and regression coverage.

If implement mode is requested, include the required pre-edit git checks:

- `git status --short`
- `git branch --show-current`
- `git rev-list --left-right --count HEAD...@{u}` when upstream exists

Do not edit source files. Do not commit. Do not push.
```

- [ ] **Step 5: Create `.gigacode/agents/coder.md`**

Write:

```markdown
---
name: coder
description: MUST BE USED only in implement mode after git safety passes to make scoped code changes for an approved feature plan or bug fix plan.
model: inherit
approvalMode: plan
---

# Coder Agent

Implement scoped changes only after git guard approval.

Before editing:

- Confirm implement mode.
- Confirm current branch is not protected.
- Confirm working tree changes do not overlap with planned edits.
- Read live files from the working tree.

Rules:

- Keep changes scoped to the approved plan.
- Do not overwrite unrelated user changes.
- Do not edit protected infrastructure paths without explicit human confirmation.
- Do not commit.
- Do not push.
- Do not rewrite history.
- Do not run deployment commands.

Outputs:

- Changed files.
- Rationale for each change.
- Notes for tests that should be run by `test-review`.
```

- [ ] **Step 6: Create `.gigacode/agents/test-review.md`**

Write:

```markdown
---
name: test-review
description: MUST BE USED after planning or implementation to select, run, or analyze verification commands and record evidence without inventing passing results.
model: inherit
approvalMode: plan
---

# Test Review Agent

Verify the plan or implementation.

For plan-only mode:

- Recommend verification commands.
- Explain what each command proves.
- List checks that still need execution.

For implement mode:

- Run targeted tests first.
- Run broader checks proportionate to risk.
- Investigate failures before summarizing.
- Record skipped checks with reasons.

Output for `docs/development/<task-slug>/verification.md`:

- Commands run.
- Exit status.
- Important output summary.
- Failures and investigation.
- Skipped checks and reasons.
- Residual risk.

Do not claim tests passed unless command output proves it.
Do not commit. Do not push.
```

- [ ] **Step 7: Create `.gigacode/agents/pr-readiness.md`**

Write:

```markdown
---
name: pr-readiness
description: MUST BE USED at the end of developer workflows to prepare reviewer-facing Markdown notes, changed-area summaries, verification evidence, and residual risk.
model: inherit
approvalMode: plan
---

# PR Readiness Agent

Prepare final handoff notes without committing or pushing.

Output for `docs/development/<task-slug>/pr-summary.md`:

- Summary.
- Task type and mode.
- Changed areas.
- Behavior change.
- Test evidence.
- Skipped checks.
- Risk notes.
- Rollback notes.
- Follow-up tasks.

For bug fixes, include root cause and regression evidence when known.

For features, include acceptance criteria coverage.

Do not invent commits, pushes, PR URLs, CI status, or deployment status.
Do not commit. Do not push.
```

- [ ] **Step 8: Verify subagent character limits**

Run:

```powershell
Get-ChildItem .gigacode/agents/*.md | ForEach-Object { if ((Get-Content $_ -Raw).Length -ge 10000) { throw "$($_.Name) exceeds 10000 characters" } else { "$($_.Name) OK" } }
```

Expected: every agent prints `OK`.

- [ ] **Step 9: Commit agents**

Run:

```powershell
git add .gigacode/agents
git commit -m "Add developer workflow subagents"
```

Expected: commit succeeds on a non-protected implementation branch.

## Task 4: Enterprise Git Guard Hook

**Files:**
- Create: `.gigacode/hooks/git_guard.py`

- [ ] **Step 1: Write `.gigacode/hooks/git_guard.py`**

Create:

```python
#!/usr/bin/env python3
import fnmatch
import json
import os
import re
import subprocess
import sys

PROTECTED_BRANCHES = [
    "main",
    "master",
    "develop",
    "development",
    "release",
    "release/*",
    "hotfix/*",
    "production",
    "prod",
    "staging",
    "uat",
]

PROTECTED_PATHS = [
    ".github/workflows/**",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    "ci/**",
    "deploy/**",
    "deployment/**",
    "k8s/**",
    "helm/**",
    "terraform/**",
    "infra/**",
    ".env",
    ".env.*",
    "secrets/**",
    "config/prod/**",
    "config/production/**",
    "config/staging/**",
    "config/uat/**",
]

DESTRUCTIVE_PATTERNS = [
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[^\s]*f",
    r"\bgit\s+push\b.*\s--force\b",
    r"\bgit\s+push\b.*\s--force-with-lease\b",
    r"\bgit\s+remote\s+set-url\b",
    r"\bgit\s+branch\s+-D\b",
    r"\bgit\s+push\b.*\s--delete\b",
]

PROTECTED_BRANCH_WRITE_PATTERNS = [
    r"\bgit\s+commit\b",
    r"\bgit\s+push\b",
]


def respond(decision, reason=""):
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload))


def run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=os.getcwd(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def current_branch():
    return run_git(["branch", "--show-current"])


def is_protected_branch(branch):
    if not branch:
        return False
    return any(fnmatch.fnmatch(branch, pattern) for pattern in PROTECTED_BRANCHES)


def command_from_event(event):
    for key in ("command", "tool_input", "input"):
        value = event.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            command = value.get("command") or value.get("cmd")
            if isinstance(command, str):
                return command
    return ""


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


def protected_path(path):
    if not path:
        return False
    normalized = path.replace("\\", "/").lstrip("./")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in PROTECTED_PATHS)


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("allow")
        return

    command = command_from_event(event)
    file_path = path_from_event(event)
    branch = current_branch()

    if command:
        lowered = command.lower()
        for pattern in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, lowered):
                respond("block", "Blocked destructive git operation. Use an explicit human-approved recovery workflow.")
                return
        if is_protected_branch(branch):
            for pattern in PROTECTED_BRANCH_WRITE_PATTERNS:
                if re.search(pattern, lowered):
                    respond("block", f"Blocked git write operation on protected branch '{branch}'. Create a feature or bugfix branch first.")
                    return

    if protected_path(file_path):
        respond("ask", f"Protected path '{file_path}' requires explicit confirmation with risk explanation.")
        return

    respond("allow")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run:

```powershell
python -m py_compile .gigacode/hooks/git_guard.py
```

Expected: exits `0`.

- [ ] **Step 3: Verify destructive command blocking**

Run:

```powershell
'{"command":"git reset --hard HEAD"}' | python .gigacode/hooks/git_guard.py
```

Expected: JSON contains `"decision": "block"`.

- [ ] **Step 4: Verify protected path confirmation**

Run:

```powershell
'{"path":".github/workflows/deploy.yml"}' | python .gigacode/hooks/git_guard.py
```

Expected: JSON contains `"decision": "ask"`.

- [ ] **Step 5: Commit git guard**

Run:

```powershell
git add .gigacode/hooks/git_guard.py
git commit -m "Add enterprise git guard hook"
```

Expected: commit succeeds on a non-protected implementation branch.

## Task 5: Preflight and Output Validation Hooks

**Files:**
- Create: `.gigacode/hooks/preflight_check.py`
- Create: `.gigacode/hooks/validate_development_output.py`

- [ ] **Step 1: Write `.gigacode/hooks/preflight_check.py`**

Create:

```python
#!/usr/bin/env python3
import json
import re
import sys


def respond(decision, reason=""):
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload))


def prompt_from_event(event):
    for key in ("prompt", "message", "user_prompt"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def has_any(text, words):
    lowered = text.lower()
    return any(word in lowered for word in words)


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("allow")
        return

    prompt = prompt_from_event(event)
    lowered = prompt.lower()

    if "/develop-feature" not in lowered and "/fix-bug" not in lowered:
        respond("allow")
        return

    if len(prompt.strip().split()) < 3:
        respond("ask", "Provide a task name or short summary.")
        return

    implement_mode = has_any(lowered, [" implement", " implementation", "реализ", "исправь", "сделай"])

    if "/develop-feature" in lowered and implement_mode:
        if not has_any(lowered, ["acceptance", "criteria", "критер", "поведение", "behavior"]):
            respond("ask", "Implement mode for feature work requires acceptance criteria or expected behavior.")
            return

    if "/fix-bug" in lowered and implement_mode:
        if not has_any(lowered, ["expected", "actual", "repro", "symptom", "ожид", "факт", "воспро", "симптом", "stack", "trace", "error"]):
            respond("ask", "Implement mode for bug work requires symptom, expected/actual behavior, reproduction evidence, or error details.")
            return

    reminder = "Inspect analytics, Repomix, and Graphify when available; use documented fallbacks when they are unavailable."
    respond("allow", reminder)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `.gigacode/hooks/validate_development_output.py`**

Create:

```python
#!/usr/bin/env python3
import json
import os
import re
import sys

REQUIRED_FILES = [
    "context.md",
    "plan.md",
    "implementation.md",
    "verification.md",
    "pr-summary.md",
]

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)
TASK_DIR_RE = re.compile(r"docs/development/([a-z0-9][a-z0-9-]*)/?")


def respond(decision, reason=""):
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload))


def last_message(event):
    for key in ("last_assistant_message", "message", "response"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def find_task_dir(message):
    match = TASK_DIR_RE.search(message.replace("\\", "/"))
    if not match:
        return ""
    return os.path.join("docs", "development", match.group(1))


def read_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("allow")
        return

    message = last_message(event)
    if "docs/development/" not in message.replace("\\", "/"):
        respond("allow")
        return

    task_dir = find_task_dir(message)
    if not task_dir:
        respond("block", "Completion mentions docs/development but no valid task directory was found.")
        return

    missing = [name for name in REQUIRED_FILES if not os.path.exists(os.path.join(task_dir, name))]
    if missing:
        respond("block", f"Missing development artifact files: {', '.join(missing)}")
        return

    for name in REQUIRED_FILES:
        path = os.path.join(task_dir, name)
        content = read_file(path)
        if PLACEHOLDER_RE.search(content):
            respond("block", f"Placeholder marker found in {path}.")
            return

    verification = read_file(os.path.join(task_dir, "verification.md")).lower()
    if "passed" in message.lower() and "command" not in verification and "exit" not in verification:
        respond("block", "Completion claims passing checks without recorded verification command evidence.")
        return

    respond("allow")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify hook syntax**

Run:

```powershell
python -m py_compile .gigacode/hooks/preflight_check.py
python -m py_compile .gigacode/hooks/validate_development_output.py
```

Expected: both commands exit `0`.

- [ ] **Step 4: Verify preflight allows complete plan-only feature prompt**

Run:

```powershell
'{"prompt":"/develop-feature plan-only payment retry"}' | python .gigacode/hooks/preflight_check.py
```

Expected: JSON contains `"decision": "allow"`.

- [ ] **Step 5: Verify preflight asks for missing implement acceptance criteria**

Run:

```powershell
'{"prompt":"/develop-feature implement payment retry"}' | python .gigacode/hooks/preflight_check.py
```

Expected: JSON contains `"decision": "ask"`.

- [ ] **Step 6: Verify validation blocks missing artifact directory**

Run:

```powershell
'{"last_assistant_message":"Complete in docs/development/sample-task/"}' | python .gigacode/hooks/validate_development_output.py
```

Expected: JSON contains `"decision": "block"` until sample artifact files exist.

- [ ] **Step 7: Commit validation hooks**

Run:

```powershell
git add .gigacode/hooks/preflight_check.py .gigacode/hooks/validate_development_output.py
git commit -m "Add developer workflow validation hooks"
```

Expected: commit succeeds on a non-protected implementation branch.

## Task 6: Smoke Checks and README

**Files:**
- Create: `scripts/smoke-check.ps1`
- Create: `scripts/smoke-check.sh`
- Create or replace: `README.md`

- [ ] **Step 1: Write `scripts/smoke-check.ps1`**

Create:

```powershell
$ErrorActionPreference = "Stop"

$required = @(
  ".gigacode/settings.json",
  ".gigacode/skills/development-flow/SKILL.md",
  ".gigacode/commands/develop-feature.md",
  ".gigacode/commands/fix-bug.md",
  ".gigacode/hooks/git_guard.py",
  ".gigacode/hooks/preflight_check.py",
  ".gigacode/hooks/validate_development_output.py",
  "docs/templates/development-plan.md",
  "rules/development-flow.md",
  "rules/git-safety.md",
  "rules/branch-naming.md"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
}

python -m json.tool .gigacode/settings.json | Out-Null

Get-ChildItem .gigacode/agents/*.md | ForEach-Object {
  $content = Get-Content $_ -Raw
  if ($content.Length -ge 10000) {
    throw "$($_.Name) exceeds 10000 characters"
  }
  if (-not ($content -match "(?s)^---.*---")) {
    throw "$($_.Name) missing frontmatter"
  }
}

$block = '{"command":"git reset --hard HEAD"}' | python .gigacode/hooks/git_guard.py
if ($block -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block reset --hard"
}

$ask = '{"path":".github/workflows/deploy.yml"}' | python .gigacode/hooks/git_guard.py
if ($ask -notmatch '"decision":\s*"ask"') {
  throw "git_guard did not ask on protected path"
}

$feature = '{"prompt":"/develop-feature plan-only payment retry"}' | python .gigacode/hooks/preflight_check.py
if ($feature -notmatch '"decision":\s*"allow"') {
  throw "preflight did not allow complete plan-only feature prompt"
}

$missing = '{"last_assistant_message":"Complete in docs/development/sample-task/"}' | python .gigacode/hooks/validate_development_output.py
if ($missing -notmatch '"decision":\s*"block"') {
  throw "validate_development_output did not block missing artifacts"
}

Write-Host "Smoke check passed"
```

- [ ] **Step 2: Write `scripts/smoke-check.sh`**

Create:

```bash
#!/usr/bin/env bash
set -euo pipefail

required=(
  ".gigacode/settings.json"
  ".gigacode/skills/development-flow/SKILL.md"
  ".gigacode/commands/develop-feature.md"
  ".gigacode/commands/fix-bug.md"
  ".gigacode/hooks/git_guard.py"
  ".gigacode/hooks/preflight_check.py"
  ".gigacode/hooks/validate_development_output.py"
  "docs/templates/development-plan.md"
  "rules/development-flow.md"
  "rules/git-safety.md"
  "rules/branch-naming.md"
)

for path in "${required[@]}"; do
  test -f "$path" || { echo "Missing required file: $path" >&2; exit 1; }
done

python -m json.tool .gigacode/settings.json >/dev/null

for path in .gigacode/agents/*.md; do
  chars="$(wc -m < "$path")"
  if [ "$chars" -ge 10000 ]; then
    echo "$path exceeds 10000 characters" >&2
    exit 1
  fi
  grep -q '^---$' "$path" || { echo "$path missing frontmatter" >&2; exit 1; }
done

block="$(printf '%s' '{"command":"git reset --hard HEAD"}' | python .gigacode/hooks/git_guard.py)"
printf '%s' "$block" | grep -q '"decision": "block"'

ask="$(printf '%s' '{"path":".github/workflows/deploy.yml"}' | python .gigacode/hooks/git_guard.py)"
printf '%s' "$ask" | grep -q '"decision": "ask"'

feature="$(printf '%s' '{"prompt":"/develop-feature plan-only payment retry"}' | python .gigacode/hooks/preflight_check.py)"
printf '%s' "$feature" | grep -q '"decision": "allow"'

missing="$(printf '%s' '{"last_assistant_message":"Complete in docs/development/sample-task/"}' | python .gigacode/hooks/validate_development_output.py)"
printf '%s' "$missing" | grep -q '"decision": "block"'

echo "Smoke check passed"
```

- [ ] **Step 3: Write `README.md`**

Create:

```markdown
# GigaCode Developer Template

This repository is a GigaCode project template for enterprise developer workflows.

It provides two project commands:

- `/develop-feature`: plan or implement a feature.
- `/fix-bug`: investigate, plan, or implement a bug fix.

Both commands use the `development-flow` skill and support two modes:

- `plan-only`: produce Markdown development artifacts without source edits.
- `implement`: plan, pass git safety checks, make scoped edits, verify behavior, and prepare PR-ready notes.

## Prerequisites

- GigaCode CLI
- Git
- Python 3
- PowerShell on Windows
- Bash for Linux-compatible smoke checks

## Quick Start

Run from the repository root:

```powershell
gigacode
```

Feature example:

```text
/develop-feature plan-only payment retry with acceptance criteria: retry failed provider calls once after transient timeout
```

Bug example:

```text
/fix-bug plan-only card blocking timeout expected: user sees final status actual: request hangs after provider timeout
```

## Outputs

Developer artifacts are Markdown files under:

```text
docs/development/<task-slug>/
```

Expected files:

- `context.md`
- `plan.md`
- `implementation.md`
- `verification.md`
- `pr-summary.md`

## Project Intelligence

The workflow uses project analytics, Repomix, and Graphify when available.

Fallbacks:

- If analytics are absent, it continues with code, tests, local docs, and user-provided context.
- If Repomix is absent, it uses direct repository inspection.
- If Graphify is absent, it uses manual impact mapping.

## Enterprise Git Safety

The template blocks implementation and git writes on protected branches such as `main`, `master`, `develop`, `release/*`, `hotfix/*`, `production`, `staging`, and `uat`.

The template blocks destructive git operations by default, including `git reset --hard`, forced pushes, branch deletion, remote URL changes, and direct protected-branch commits.

The template does not auto-commit or auto-push in v1. PR readiness means the workflow prepares reviewer-facing notes and verification evidence for a human or CI workflow.

## Smoke Checks

Windows:

```powershell
.\scripts\smoke-check.ps1
```

Linux-compatible shell:

```bash
bash scripts/smoke-check.sh
```

Smoke checks do not require GigaCode, Repomix, Graphify, MCP servers, network access, or enterprise credentials.

## Adapting for a Team

Update `rules/git-safety.md` for team-specific protected branches and protected paths.

Update `.gigacode/settings.json` only with project-safe defaults. Do not store secrets, tokens, personal paths, or environment-specific credentials in this repository.
```

- [ ] **Step 4: Run smoke checks**

Run:

```powershell
.\scripts\smoke-check.ps1
bash scripts/smoke-check.sh
```

Expected: both print `Smoke check passed` and exit `0`.

- [ ] **Step 5: Commit smoke checks and README**

Run:

```powershell
git add scripts/smoke-check.ps1 scripts/smoke-check.sh README.md
git commit -m "Add developer template smoke checks and README"
```

Expected: commit succeeds on a non-protected implementation branch.

## Task 7: Final Verification and Polish

**Files:**
- Verify all repository files.
- Modify only files that fail verification.

- [ ] **Step 1: Run final repository checks**

Run:

```powershell
git status --short
python -m json.tool .gigacode/settings.json
.\scripts\smoke-check.ps1
bash scripts/smoke-check.sh
Get-ChildItem .gigacode/agents/*.md | ForEach-Object { if ((Get-Content $_ -Raw).Length -ge 10000) { throw "$($_.Name) exceeds 10000 characters" } }
```

Expected:

- JSON validation exits `0`.
- Windows smoke check passes.
- Bash smoke check passes.
- No agent exceeds 10,000 characters.
- `git status --short` shows only intended changes or known untracked source documents.

- [ ] **Step 2: Inspect required behavior coverage**

Run:

```powershell
rg -n "develop-feature|fix-bug|plan-only|implement|Repomix|Graphify|fallback|protected branch|reset --hard|auto-commit|auto-push|10,000" .gigacode docs rules README.md scripts
```

Expected: output shows the developer commands, both modes, Repomix and Graphify fallbacks, enterprise git safety, no auto-commit or auto-push policy, and 10,000-character subagent limit.

- [ ] **Step 3: Commit final polish if needed**

If Step 1 or Step 2 required edits, run:

```powershell
git add .gigacode docs rules scripts README.md .gitignore
git commit -m "Polish developer template"
```

Expected: commit succeeds on a non-protected implementation branch.

If no edits were required, do not create an empty commit.

## Self-Review

Spec coverage:

- `.gigacode` project configuration is covered by Tasks 2, 3, 4, and 5.
- `/develop-feature` and `/fix-bug` are covered by Task 2.
- Plan-only and implement modes are covered by Tasks 2, 3, 5, and 6.
- Markdown artifacts are covered by Tasks 1, 5, and 6.
- Analytics, Repomix, Graphify, and fallbacks are covered by Tasks 1, 2, 3, and 6.
- Enterprise git safety is covered by Tasks 1, 2, 4, and 6.
- Protected branch and destructive git blocking are covered by Tasks 1, 2, 4, 6, and 7.
- No auto-commit or auto-push behavior is covered by Tasks 2, 3, 4, and 6.
- Subagent 10,000-character limit is covered by Tasks 3, 6, and 7.
- Smoke checks are covered by Tasks 6 and 7.

Placeholder scan:

- The plan intentionally mentions forbidden output markers only as validator examples.
- There are no unresolved implementation placeholders.

Execution notes:

- Before executing this plan, create or switch to a safe non-protected implementation branch such as `feature/gigacode-developer-template`.
- Do not execute this plan directly on `main`, `master`, `develop`, `release/*`, `hotfix/*`, `production`, `staging`, or `uat`.
