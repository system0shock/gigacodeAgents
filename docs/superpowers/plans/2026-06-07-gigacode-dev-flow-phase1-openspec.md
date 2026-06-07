# GigaCode Dev Flow — Phase 1 (OpenSpec Adoption) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GigaCode developer template (which is copied into external dev repos) adopt the OpenSpec spec-driven format so that agent-produced specs follow one machine-validatable structure (`openspec validate`), fixing the "files not per open-spec" problem at the template level.

**Architecture:** OpenSpec (`@fission-ai/openspec` v1.4.1) is adopted as the spec engine. We generate its native Qwen Code integration, remap `.qwen/` → `.gigacode/`, and bake the resulting skills/commands plus `openspec/config.yaml` into the template. The existing `development-flow` skill and `/develop-feature` `/fix-bug` commands are updated so their authoritative spec lives in `openspec/changes/<id>/` while human run-notes stay under `docs/development/<task-slug>/`. Smoke checks and README are extended. This phase does NOT build the hook router or quality gates (Phases 3–4) and does NOT touch MCP (Phases 2, 5).

**Tech Stack:** GigaCode (Qwen Code fork), Node.js (for the `openspec` CLI), Python 3 (existing hooks), Bash + PowerShell smoke checks, Markdown/TOML config.

**Base branch:** `feature/gigacode-developer-template` (the worktree at `.worktrees/developer-template` holds the built template). All Phase 1 work happens on a new branch off it.

**Reference spec:** `docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md` (commit `28b01d9` on `master`).

---

## Open Item To Resolve During Execution (Task 2)

OpenSpec generates Qwen custom commands as **`.toml`** files (`description` + `prompt` fields), but the existing template ships commands as **`.md`** (`develop-feature.md`, `fix-bug.md`). It is not yet confirmed which format GigaCode actually loads from `.gigacode/commands/`. Task 2 verifies this against GigaCode and picks one format for the whole template. Do not assume — test. If GigaCode is unavailable in the execution environment, record the finding as "unverified" and default to keeping BOTH the generated `.toml` commands and the existing `.md` commands, noting the risk in the README.

---

## File Structure

Created in the template (committed):
- `openspec/config.yaml` — OpenSpec project config (schema: spec-driven).
- `.gigacode/skills/openspec-propose/SKILL.md` and 4 sibling openspec skills — generated, remapped from `.qwen/`.
- `.gigacode/commands/opsx-*.toml` (or `.md` per Task 2 decision) — generated opsx commands, remapped.
- `rules/openspec.md` — authoritative format reference for agents.

Modified in the template:
- `.gigacode/skills/development-flow/SKILL.md` — add OpenSpec backbone section.
- `.gigacode/commands/develop-feature.md`, `.gigacode/commands/fix-bug.md` — drive the OpenSpec cycle.
- `scripts/smoke-check.sh`, `scripts/smoke-check.ps1` — add OpenSpec assertions.
- `README.md` — prerequisite + workflow + remap note.

Not touched this phase: hooks (`*.py`), `settings.json` hook wiring, agents.

---

### Task 1: Isolated worktree, branch, and OpenSpec prerequisite

**Files:**
- None created in repo; environment setup only.

- [ ] **Step 1: Create a new branch + worktree off the developer-template branch**

```bash
git -C F:/Coding/gigacode_agents worktree add F:/Coding/gigacode_agents/.worktrees/dev-flow-enforcement -b feature/dev-flow-enforcement feature/gigacode-developer-template
```

- [ ] **Step 2: Bring the enforcement design doc onto this branch**

```bash
git -C F:/Coding/gigacode_agents/.worktrees/dev-flow-enforcement cherry-pick 28b01d9
```
Expected: the design doc appears at `docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md` in the worktree. If cherry-pick reports "already applied" or path conflicts, resolve by keeping the design doc and continue.

- [ ] **Step 3: Install the OpenSpec CLI globally and verify version**

```bash
npm install -g @fission-ai/openspec@1.4.1
openspec --version
```
Expected: prints `1.4.1`. On Windows the global shim is `openspec.cmd`/`openspec.ps1`; verify `openspec --version` works in the shell that will run later tasks.

- [ ] **Step 4: Confirm the working directory for all later tasks**

All subsequent file paths in this plan are relative to `F:/Coding/gigacode_agents/.worktrees/dev-flow-enforcement`. Confirm `.gigacode/` and `scripts/smoke-check.sh` exist there before proceeding.

---

### Task 2: Generate and remap the OpenSpec Qwen integration into the template

**Files:**
- Create: `openspec/config.yaml`
- Create: `.gigacode/skills/openspec-{propose,apply,archive,explore,sync-specs}/SKILL.md`
- Create: `.gigacode/commands/opsx-{propose,apply,archive,explore,sync}.toml`

- [ ] **Step 1: Generate the native Qwen integration in the worktree root**

```bash
openspec init --tools qwen --force
```
Expected output includes "Setup complete for Qwen Code" and creates `.qwen/skills/openspec-*/SKILL.md` (5 skills), `.qwen/commands/opsx-*.toml` (5 commands), and `openspec/config.yaml`.

- [ ] **Step 2: Verify the generated tree**

```bash
find .qwen openspec -type f | sort
```
Expected: 5 `.qwen/skills/openspec-*/SKILL.md`, 5 `.qwen/commands/opsx-*.toml`, and `openspec/config.yaml`.

- [ ] **Step 3: Remap the generated skills and commands from `.qwen/` to `.gigacode/`**

```bash
cp -r .qwen/skills/openspec-* .gigacode/skills/
mkdir -p .gigacode/commands
cp .qwen/commands/opsx-*.toml .gigacode/commands/
rm -rf .qwen
```
Expected: `.gigacode/skills/openspec-propose/SKILL.md` etc. exist; `.gigacode/commands/opsx-propose.toml` etc. exist; `.qwen/` is gone.

- [ ] **Step 4: Resolve the command-format open item (see top of plan)**

If GigaCode is available: copy the template into a throwaway GigaCode project, run `gigacode`, and check whether `/develop-feature` (`.md`) and `/opsx:propose` (`.toml`) both load.
- If only `.md` loads: convert each `opsx-*.toml` into an `.md` command. The `.md` form is `---\ndescription: <toml description value>\n---\n\n<toml prompt value with {{args}} substituted for the input>` and then `rm .gigacode/commands/opsx-*.toml`.
- If only `.toml` loads: convert `develop-feature.md`/`fix-bug.md` to `.toml` in Task 6 instead, and keep the generated `.toml` as-is here.
- If both load, or GigaCode is unavailable: keep both formats and record "command format unverified" for the README (Task 8).

Record the outcome in a scratch note you will reference in Task 8.

- [ ] **Step 5: Verify the OpenSpec CLI recognizes the project**

```bash
openspec list --specs
```
Expected: runs without error and reports no specs yet (empty), confirming `openspec/config.yaml` is valid and discovered.

- [ ] **Step 6: Commit**

```bash
git add openspec/config.yaml .gigacode/skills/openspec-* .gigacode/commands/
git commit -m "Add OpenSpec spec-driven integration to GigaCode template

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Seed `openspec/config.yaml` with template defaults

**Files:**
- Modify: `openspec/config.yaml`

- [ ] **Step 1: Replace the generated config body with template-appropriate guidance**

Write `openspec/config.yaml` to exactly:

```yaml
schema: spec-driven

# Project context shown to the AI when creating artifacts.
# Teams adopting this template should fill this in for their repository:
# tech stack, build/test commands, conventions, domain terms.
context: |
  This repository was set up from the GigaCode developer template.
  Replace this block with your project's tech stack, conventions, and
  domain knowledge. Code in the working tree is the source of truth.

# Per-artifact rules enforced as constraints on generated artifacts.
rules:
  proposal:
    - Tie every change to an observed need; no speculative scope.
  spec:
    - Every requirement MUST have at least one scenario with WHEN/THEN.
  tasks:
    - Break work into small, independently committable steps.
```

- [ ] **Step 2: Verify config still parses**

```bash
openspec list --specs
```
Expected: runs without error (empty spec list).

- [ ] **Step 3: Commit**

```bash
git add openspec/config.yaml
git commit -m "Seed OpenSpec config with template defaults

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Add `rules/openspec.md` — authoritative format reference

**Files:**
- Create: `rules/openspec.md`

- [ ] **Step 1: Write the rules file**

Write `rules/openspec.md` to exactly:

```markdown
# OpenSpec Format Rules

GigaCode developer workflows manage their authoritative specifications with
OpenSpec. Agents MUST follow these conventions. Human-facing run notes still go
under `docs/development/<task-slug>/`; the authoritative, validatable spec lives
under `openspec/`.

## Directory layout

```
openspec/
  config.yaml
  specs/<capability>/spec.md        # current truth, per capability
  changes/<change-id>/
    proposal.md                     # why + what
    design.md                       # how
    tasks.md                        # implementation checklist
    specs/<capability>/spec.md      # delta for this change
  changes/archive/                  # completed changes
```

## Spec requirement format

Every requirement MUST have at least one scenario. Use these literal headers:

```markdown
## ADDED Requirements

### Requirement: Short imperative name
The system SHALL ...

#### Scenario: Named scenario
- **WHEN** <condition>
- **THEN** <expected outcome>
```

In a change's delta spec, the top-level section is one of:
`## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`,
`## RENAMED Requirements`.

## Change artifacts

- `proposal.md` sections: `## Why`, `## What Changes`, `## Capabilities`
  (`### New Capabilities`, `### Modified Capabilities`), `## Impact`.
- `design.md` sections: `## Context`, `## Goals / Non-Goals`, `## Decisions`,
  `## Risks / Trade-offs`.
- `tasks.md`: numbered task groups (`## 1. Group`) with `- [ ]` checkbox items.

## Validation

A change is not "ready" until `openspec validate <change-id> --strict` passes.
Run `openspec validate --specs` to validate current-truth specs. Treat a
non-zero exit as a blocking failure; fix the structure, do not bypass it.

## Lifecycle

1. `/opsx:propose "<idea>"` — create the change and all artifacts.
2. `/opsx:apply` — implement the tasks.
3. `/opsx:archive` — move the completed change to `changes/archive/` and update
   `openspec/specs/`.
```

- [ ] **Step 2: Verify the embedded fenced examples are intact**

Run: `grep -c "WHEN" rules/openspec.md`
Expected: at least `1`.

- [ ] **Step 3: Commit**

```bash
git add rules/openspec.md
git commit -m "Add OpenSpec format rules reference

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Update `development-flow` SKILL.md with the OpenSpec backbone

**Files:**
- Modify: `.gigacode/skills/development-flow/SKILL.md`

- [ ] **Step 1: Replace the "Output Files" section**

Find the section starting at `## Output Files` (line ~77) through the end of its list (the line `Plan-only artifacts must clearly state when implementation or verification was not executed.`) and replace the whole section with:

```markdown
## Specs and Output Files

Authoritative specifications use OpenSpec under `openspec/` (see
`rules/openspec.md`). Drive specs through the change lifecycle:

1. Create or continue a change with `/opsx:propose "<idea>"` (or `openspec new
   change "<id>"`). This produces `openspec/changes/<change-id>/` with
   `proposal.md`, `design.md`, `tasks.md`, and delta specs.
2. Keep the authoritative requirement/scenario detail in the change's spec
   delta, not in free-form notes.
3. A change is not ready for implementation until
   `openspec validate <change-id> --strict` passes.

Human-facing run notes remain Markdown under `docs/development/<task-slug>/`:

- `context.md`
- `plan.md`
- `implementation.md`
- `verification.md`
- `pr-summary.md`

Run notes summarize and link to the OpenSpec change; they do not replace it.
Plan-only artifacts must clearly state when implementation or verification was
not executed.
```

- [ ] **Step 2: Verify the skill file is still under 10,000 characters**

Run: `wc -m .gigacode/skills/development-flow/SKILL.md`
Expected: a number below `10000`.

- [ ] **Step 3: Commit**

```bash
git add .gigacode/skills/development-flow/SKILL.md
git commit -m "Wire development-flow skill to OpenSpec backbone

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Update `/develop-feature` and `/fix-bug` to drive the OpenSpec cycle

**Files:**
- Modify: `.gigacode/commands/develop-feature.md`
- Modify: `.gigacode/commands/fix-bug.md`

- [ ] **Step 1: Update `develop-feature.md`**

Replace step `8.` line (`8. Produce Markdown artifacts under \`docs/development/<task-slug>/\`.`) with these two lines, renumbering the rest:

```markdown
8. Create or continue an OpenSpec change with `/opsx:propose`; keep the
   authoritative spec under `openspec/changes/<change-id>/` and validate it with
   `openspec validate <change-id> --strict`.
9. Produce human run notes under `docs/development/<task-slug>/` that link to the
   OpenSpec change.
```
Then renumber the remaining two original items (`Record verification evidence…`, `Do not auto-commit…`) to `10.` and `11.`.

- [ ] **Step 2: Apply the same change to `fix-bug.md`**

Open `.gigacode/commands/fix-bug.md`. Find its artifact-production step (the line instructing to produce Markdown artifacts under `docs/development/<task-slug>/`) and replace it with the same two steps from Step 1 (OpenSpec change first, then linked run notes), renumbering subsequent steps consistently.

- [ ] **Step 3: Verify both commands still have valid frontmatter**

Run: `grep -c '^---$' .gigacode/commands/develop-feature.md .gigacode/commands/fix-bug.md`
Expected: each file reports `2`.

- [ ] **Step 4: Commit**

```bash
git add .gigacode/commands/develop-feature.md .gigacode/commands/fix-bug.md
git commit -m "Drive develop-feature and fix-bug through OpenSpec cycle

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Extend smoke checks with OpenSpec assertions

**Files:**
- Modify: `scripts/smoke-check.sh`
- Modify: `scripts/smoke-check.ps1`

- [ ] **Step 1: Add required-file checks and an OpenSpec validation check to `smoke-check.sh`**

In `scripts/smoke-check.sh`, add these entries to the `required=(` array (after `"rules/branch-naming.md"`):

```bash
  "openspec/config.yaml"
  "rules/openspec.md"
  ".gigacode/skills/openspec-propose/SKILL.md"
```

Then, immediately before the final success line, add:

```bash
if command -v openspec >/dev/null 2>&1; then
  openspec list --specs >/dev/null
  echo "openspec config valid"
else
  echo "SKIP: openspec CLI not installed; spec validation not run" >&2
fi
```

- [ ] **Step 2: Run the bash smoke check**

Run: `bash scripts/smoke-check.sh`
Expected: exits 0. If `openspec` is installed it prints `openspec config valid`; otherwise it prints the SKIP line and still exits 0.

- [ ] **Step 3: Mirror the changes in `smoke-check.ps1`**

In `scripts/smoke-check.ps1`, add the same three paths to the `$required = @(` array (after `"rules/branch-naming.md"`):

```powershell
  "openspec/config.yaml",
  "rules/openspec.md",
  ".gigacode/skills/openspec-propose/SKILL.md"
```

Then, immediately before `Write-Host "Smoke check passed"`, add:

```powershell
if (Get-Command openspec -ErrorAction SilentlyContinue) {
  openspec list --specs | Out-Null
  Write-Host "openspec config valid"
} else {
  Write-Warning "SKIP: openspec CLI not installed; spec validation not run"
}
```

- [ ] **Step 4: Run the PowerShell smoke check**

Run: `pwsh scripts/smoke-check.ps1` (or `powershell -File scripts/smoke-check.ps1`)
Expected: prints `Smoke check passed`; the openspec line is "valid" or a SKIP warning.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke-check.sh scripts/smoke-check.ps1
git commit -m "Smoke-check OpenSpec integration with offline skip

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add an "OpenSpec specifications" section**

Append to `README.md` a section with exactly this content (translate to Russian to match the README's language if the rest of the file is Russian):

```markdown
## OpenSpec specifications

This template manages authoritative specs with OpenSpec.

Prerequisite (once per machine):

    npm install -g @fission-ai/openspec@1.4.1

The template ships the GigaCode-adapted OpenSpec skills and commands under
`.gigacode/` and an `openspec/config.yaml`. If you re-generate them, run
`openspec init --tools qwen --force` and move `.qwen/skills/openspec-*` and
`.qwen/commands/opsx-*` into `.gigacode/`.

Workflow:

1. `/opsx:propose "<idea>"` — create a change under `openspec/changes/<id>/`.
2. Fill artifacts; run `openspec validate <id> --strict`.
3. `/opsx:apply` to implement, `/opsx:archive` when done.

Format rules are in `rules/openspec.md`. Human run notes stay under
`docs/development/<task-slug>/` and link to the OpenSpec change.
```

- [ ] **Step 2: If Task 2 left the command format unverified, add a note**

If the Task 2 scratch note says the command format is unverified, add one line under the section: "Note: GigaCode command file format (`.toml` vs `.md`) for the `opsx-*` commands is unverified; both are shipped. Verify against your GigaCode build."

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document OpenSpec setup and workflow in README

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: End-to-end OpenSpec cycle verification

**Files:**
- None committed in the template; this task proves the format gate works and is recorded as evidence.

- [ ] **Step 1: Create a throwaway change and a valid spec delta**

```bash
openspec new change verify-openspec-setup
```
Expected: creates `openspec/changes/verify-openspec-setup/` with scaffold artifacts.

- [ ] **Step 2: Write a minimal valid delta spec**

Create `openspec/changes/verify-openspec-setup/specs/sample/spec.md` with:

```markdown
## ADDED Requirements

### Requirement: Sample requirement
The system SHALL prove OpenSpec validation works.

#### Scenario: Validation passes
- **WHEN** the spec is well formed
- **THEN** openspec validate reports success
```

- [ ] **Step 3: Validate — expect PASS**

Run: `openspec validate verify-openspec-setup --strict`
Expected: exits 0 / reports valid. Record the output.

- [ ] **Step 4: Break the spec and re-validate — expect FAIL**

Delete the `#### Scenario:` block from the spec file (leaving a requirement with no scenario), then run:
`openspec validate verify-openspec-setup --strict`
Expected: non-zero exit / reports the missing-scenario error. This proves the gate that Phase 4 will enforce. Record the output.

- [ ] **Step 5: Remove the throwaway change (do not commit it)**

```bash
rm -rf openspec/changes/verify-openspec-setup
git status --short
```
Expected: no `openspec/changes/verify-openspec-setup` left; nothing to commit from this task.

- [ ] **Step 6: Final full smoke check**

Run: `bash scripts/smoke-check.sh`
Expected: exits 0.

---

## Self-Review Notes

- **Spec coverage:** This plan covers the OpenSpec-format portions of the
  enforcement design (Phase 1 only): `openspec/` structure, `openspec validate`
  as the future gate engine, Qwen→GigaCode remap, and the residual
  command-generation compatibility check. Hook router (Phase 3), quality gates
  including `gate_spec_structure` (Phase 4), and MCP (Phases 2, 5) are
  intentionally out of scope here.
- **No auto-commit of runtime work:** Task 9 verification artifacts are removed,
  not committed, consistent with the template's no-auto-commit stance.
- **Offline safety:** smoke checks skip-with-record when the `openspec` CLI is
  absent, preserving the "smoke checks need no network/credentials" invariant.
```
