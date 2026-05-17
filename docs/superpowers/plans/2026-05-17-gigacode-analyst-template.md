# GigaCode Analyst Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Git-ready GigaCode project template for analysts performing reverse analysis of one business feature at a time.

**Architecture:** The repository contains a self-contained analytics module at `modules/analytics/`. GigaCode discovers project settings, skills, agents, commands, and hooks under `modules/analytics/.gigacode/` when analysts run it from that module, while analyst outputs are Russian-language AsciiDoc files under `modules/analytics/docs/features/<feature-name>/`.

**Tech Stack:** GigaCode/Qwen Code-compatible JSON settings, Markdown skill/agent/command files with YAML frontmatter, Python 3 hook scripts, PowerShell and POSIX shell smoke checks, AsciiDoc templates.

---

## File Structure

- Create `modules/analytics/.gigacode/settings.json`: project settings, hook wiring, safe permissions, optional `repomix`/`graphify` permissions, UI defaults.
- Create `modules/analytics/.gigacode/skills/reverse-analysis/SKILL.md`: one workflow skill for reverse analysis.
- Create `modules/analytics/.gigacode/agents/*.md`: five focused subagents, each below 10,000 characters.
- Create `modules/analytics/.gigacode/hooks/preflight_check.py`: validates reverse-analysis prompt input from hook JSON.
- Create `modules/analytics/.gigacode/hooks/validate_output.py`: validates generated AsciiDoc output from repo state and hook JSON.
- Create `modules/analytics/.gigacode/commands/reverse-analysis.md`: project slash command prompt.
- Create `modules/analytics/docs/templates/feature-analysis.adoc`: reusable AsciiDoc output contract.
- Create `modules/analytics/docs/features/.gitkeep`: keeps output directory in git.
- Create `modules/analytics/rules/reverse-analysis.md`: shared workflow rules.
- Create `modules/analytics/rules/branch-naming.md`: branch naming guidance.
- Create `modules/analytics/scripts/smoke-check.ps1`: Windows smoke check.
- Create `modules/analytics/scripts/smoke-check.sh`: Linux smoke check.
- Create `modules/analytics/README.md`: analytics quick start and operating guide.
- Create `README.md`: repository-level module index.
- Create `.gitignore`: local/runtime ignores.

All task paths below are relative to `modules/analytics/` unless the path is explicitly `README.md` or `.gitignore` at repository root.

## Task 1: Repository Skeleton and Static Rules

**Files:**
- Create: `.gitignore`
- Create: `docs/features/.gitkeep`
- Create: `docs/templates/feature-analysis.adoc`
- Create: `rules/reverse-analysis.md`
- Create: `rules/branch-naming.md`

- [ ] **Step 1: Create directories and static files**

Create the directories:

```powershell
New-Item -ItemType Directory -Force .gigacode, docs\features, docs\templates, rules, scripts | Out-Null
```

Create `.gitignore` with local/runtime ignores:

```gitignore
.env
.env.*
!.env.example
__pycache__/
*.pyc
.gigacode/tmp/
.gigacode/logs/
docs/features/*/tmp/
```

Create `docs/features/.gitkeep` as an empty file.

Create `docs/templates/feature-analysis.adoc`:

```asciidoc
= Feature Reverse Analysis Template
:toc:
:sectnums:

== Scope

Feature name::
  <feature name>

Included::
  <confirmed included scope>

Excluded::
  <confirmed excluded scope>

Sources::
  * Code: <files or modules>
  * Jira: <ticket or "not used">
  * Confluence: <page or "not used">
  * User input: <prompt or clarification>

== Evidence Rules

Every factual statement must be backed by at least one source. Unsupported statements belong in assumptions or open questions.
```

Create `rules/reverse-analysis.md`:

```markdown
# Reverse Analysis Rules

Reverse analysis is performed for one business feature at a time.

Source priority:
1. Code is the source of current implementation truth.
2. Jira is requirements context and may be stale.
3. Confluence is architecture context and may be stale.
4. User input is accepted scope context and must be labeled.

Workflow invariants:
- Map code before drafting documentation.
- Ask before inventing missing context.
- Put unsupported statements in assumptions or questions.
- Use AsciiDoc for final analyst deliverables.
- Save feature outputs under `docs/features/<feature-name>/`.
```

Create `rules/branch-naming.md`:

```markdown
# Branch Naming Rules

Recommended branch format:

`analysis/<feature-slug>`

Examples:
- `analysis/card-blocking`
- `analysis/payment-retry`

Use lowercase ASCII, digits, and hyphens. Avoid spaces and ticket-only branch names.
```

- [ ] **Step 2: Verify skeleton**

Run:

```powershell
Test-Path docs\templates\feature-analysis.adoc
Test-Path rules\reverse-analysis.md
Test-Path rules\branch-naming.md
```

Expected: all three commands print `True`.

- [ ] **Step 3: Commit skeleton**

```powershell
git add .gitignore docs/features/.gitkeep docs/templates/feature-analysis.adoc rules/reverse-analysis.md rules/branch-naming.md
git commit -m "Add analyst template skeleton"
```

## Task 2: GigaCode Settings, Skill, and Command

**Files:**
- Create: `.gigacode/settings.json`
- Create: `.gigacode/skills/reverse-analysis/SKILL.md`
- Create: `.gigacode/commands/reverse-analysis.md`

- [ ] **Step 1: Write project settings**

Create `.gigacode/settings.json`:

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
      "Bash(python .gigacode/hooks/*)",
      "Edit(docs/features/**)"
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
          {
            "type": "command",
            "command": "python .gigacode/hooks/preflight_check.py"
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
            "command": "python .gigacode/hooks/validate_output.py"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Write reverse-analysis skill**

Create `.gigacode/skills/reverse-analysis/SKILL.md`:

```markdown
---
name: reverse-analysis
description: MUST BE USED for reverse analysis of one business feature into AsciiDoc documentation with explicit evidence, assumptions, gaps, and open questions.
---

# Reverse Analysis

Use this skill when the analyst asks to investigate, document, explain, or reverse-analyze a business feature.

## Operating Rules

1. Analyze one business feature, not the whole repository.
2. Treat code as the source of current implementation truth.
3. Treat Jira and Confluence as supporting context that may be stale.
4. If Atlassian MCP is unavailable, continue with code and user-provided context, and state that limitation.
5. Map code before drafting documentation.
6. Ask the analyst to confirm scope before creating final feature files.
7. Do not present unsupported claims as facts.
8. Write final analyst deliverables in AsciiDoc.

## Required Output Files

Create these files under `docs/features/<feature-name>/`:

- `overview.adoc`
- `flow.adoc`
- `integrations.adoc`
- `data.adoc`
- `questions.adoc`

## Evidence Labels

Use these labels inside AsciiDoc sections:

- `Source: code`
- `Source: jira`
- `Source: confluence`
- `Source: user`
- `Status: assumption`
- `Status: open question`

## Agent Flow

Use these project agents when appropriate:

1. `intake-scope`
2. `code-mapping`
3. `documentation`
4. `evidence-gap`
5. `review`

Stop for analyst confirmation after code mapping and before final drafting.
```

- [ ] **Step 3: Write project command**

Create `.gigacode/commands/reverse-analysis.md`:

```markdown
---
description: Run reverse analysis for one business feature and produce AsciiDoc documentation.
---

Use the `reverse-analysis` skill.

Analyze exactly one business feature from these user arguments:

{{args}}

Follow this sequence:

1. Run intake and identify missing inputs.
2. Use Jira/Confluence only if Atlassian MCP is available.
3. Map relevant code before writing documentation.
4. Ask me to confirm scope before drafting final files.
5. Produce AsciiDoc files under `docs/features/<feature-name>/`.
6. Separate facts, assumptions, gaps, contradictions, and open questions.
7. Validate the output before claiming completion.
```

- [ ] **Step 4: Verify JSON and frontmatter**

Run:

```powershell
python -m json.tool .gigacode/settings.json
Select-String .gigacode/skills/reverse-analysis/SKILL.md -Pattern '^---$'
Select-String .gigacode/commands/reverse-analysis.md -Pattern '^---$'
```

Expected: JSON prints formatted settings, and each Markdown file has two `---` frontmatter boundary lines.

- [ ] **Step 5: Commit settings, skill, and command**

```powershell
git add .gigacode/settings.json .gigacode/skills/reverse-analysis/SKILL.md .gigacode/commands/reverse-analysis.md
git commit -m "Add GigaCode reverse analysis skill"
```

## Task 3: Project Subagents

**Files:**
- Create: `.gigacode/agents/intake-scope.md`
- Create: `.gigacode/agents/code-mapping.md`
- Create: `.gigacode/agents/documentation.md`
- Create: `.gigacode/agents/evidence-gap.md`
- Create: `.gigacode/agents/review.md`

- [ ] **Step 1: Create five agent files**

Each file must use Qwen Code-style YAML frontmatter adapted under `.gigacode/agents/`. Keep each file under 10,000 characters.

Use this frontmatter pattern:

```markdown
---
name: agent-name
description: Focused description of when this agent MUST BE USED.
model: inherit
approvalMode: plan
---
```

Required role bodies:

- `intake-scope`: clarify feature name, included scope, excluded scope, Jira/Confluence status, target output path, and unanswered questions.
- `code-mapping`: optionally use `repomix` and `graphify` when available, read repository structure, identify entry points, relevant files, call chains, integrations, events, queues, APIs, data stores, and uncertain paths.
- `documentation`: after scope confirmation, write AsciiDoc files under `docs/features/<feature-name>/` using only confirmed facts and labeled assumptions.
- `evidence-gap`: inspect generated AsciiDoc for unsupported claims, contradictions, and missing evidence labels.
- `review`: check final structure, terminology, AsciiDoc consistency, and rule compliance without adding new facts.

- [ ] **Step 2: Verify character limits**

Run:

```powershell
Get-ChildItem .gigacode/agents/*.md | ForEach-Object { "{0} {1}" -f $_.Name, (Get-Content $_ -Raw).Length }
```

Expected: every count is below `10000`.

- [ ] **Step 3: Commit agents**

```powershell
git add .gigacode/agents
git commit -m "Add reverse analysis subagents"
```

## Task 4: Hook Scripts

**Files:**
- Create: `.gigacode/hooks/preflight_check.py`
- Create: `.gigacode/hooks/validate_output.py`

- [ ] **Step 1: Implement preflight hook**

Create `.gigacode/hooks/preflight_check.py` as a stdin JSON command hook. It should:

- Ignore prompts unrelated to reverse analysis.
- Require a feature name for reverse-analysis prompts.
- Require Jira/Confluence context or an explicit code-only statement.
- Return JSON with `decision: "ask"` for missing inputs.
- Return JSON with `decision: "allow"` for complete inputs.

- [ ] **Step 2: Implement output validation hook**

Create `.gigacode/hooks/validate_output.py` as a stdin JSON command hook. It should:

- Inspect the last assistant message and repository state.
- Ignore turns that do not mention reverse-analysis completion or `docs/features/`.
- Validate `.adoc` files when a feature output directory is present.
- Block completion if required files or sections are missing.
- Block completion if generated files contain `TODO`, `TBD`, or `FIXME`.

- [ ] **Step 3: Verify hooks with sample JSON**

Run:

```powershell
'{"prompt":"reverse-analysis feature Card Blocking jira ABC-123"}' | python .gigacode/hooks/preflight_check.py
'{"prompt":"hello"}' | python .gigacode/hooks/preflight_check.py
'{"last_assistant_message":"Reverse analysis complete in docs/features/card-blocking/"}' | python .gigacode/hooks/validate_output.py
```

Expected:

- First command returns `allow`.
- Second command returns `allow`.
- Third command returns `block` until sample output files exist.

- [ ] **Step 4: Commit hooks**

```powershell
git add .gigacode/hooks/preflight_check.py .gigacode/hooks/validate_output.py
git commit -m "Add reverse analysis hooks"
```

## Task 5: Smoke Checks and README

**Files:**
- Create: `scripts/smoke-check.ps1`
- Create: `scripts/smoke-check.sh`
- Create: `README.md`

- [ ] **Step 1: Implement smoke checks**

Both scripts should verify:

- Required files exist.
- `.gigacode/settings.json` is valid JSON.
- Agent files are below 10,000 characters.
- Hook scripts return valid JSON for sample inputs.
- Output template is AsciiDoc.

- [ ] **Step 2: Write README**

README must include:

- Purpose.
- Windows quick start.
- Linux quick start.
- Prerequisites: `gigacode`, Git, Python 3.
- Smoke check commands.
- Example `/reverse-analysis` invocation.
- Output file list using `.adoc`.
- Atlassian MCP policy: users install it themselves.
- Adaptation notes for real repositories.

- [ ] **Step 3: Run smoke checks**

Run on Windows:

```powershell
.\scripts\smoke-check.ps1
```

Run Linux-compatible check if shell is available:

```powershell
bash scripts/smoke-check.sh
```

Expected: both print success and exit `0`.

- [ ] **Step 4: Commit docs and checks**

```powershell
git add scripts/smoke-check.ps1 scripts/smoke-check.sh README.md
git commit -m "Add smoke checks and README"
```

## Task 6: Final Verification

**Files:**
- Verify all repository files.

- [ ] **Step 1: Run full status and checks**

```powershell
git status --short
python -m json.tool .gigacode/settings.json
.\scripts\smoke-check.ps1
bash scripts/smoke-check.sh
```

Expected:

- `git status --short` only shows intentionally untracked `core_docs/` if not committed.
- JSON validation succeeds.
- Both smoke checks pass.

- [ ] **Step 2: Inspect source references**

Confirm the README and rules mention:

- GigaCode, not Qwen in user-facing commands.
- AsciiDoc outputs.
- MCP self-install policy.
- One-feature scope.
- Subagent files below 10,000 characters.

- [ ] **Step 3: Commit final adjustments**

If Task 6 required edits:

```powershell
git add .
git commit -m "Polish analyst template"
```

If no edits were required, do not create an empty commit.

## Self-Review

Spec coverage:

- `.gigacode` project configuration is covered by Tasks 2, 3, and 4.
- AsciiDoc output is covered by Tasks 1, 2, 4, and 5.
- Five subagents are covered by Task 3.
- Two hooks are covered by Task 4.
- Windows/Linux support is covered by Task 5.
- README quick start is covered by Task 5.
- MCP self-install policy is covered by Tasks 2 and 5.
- Subagent length limit is covered by Tasks 3 and 5.

Placeholder scan:

- The plan intentionally mentions forbidden output markers `TODO`, `TBD`, and `FIXME` only as validator inputs.
- There are no unresolved implementation placeholders.
