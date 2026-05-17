# GigaCode Developer Template Design

## Goal

Create a Git-ready project template for developers who use the GigaCode CLI, a fork of Qwen Code, to deliver software changes through controlled enterprise workflows.

The developer template is analogous to the analyst template, but its primary job is not reverse documentation. Its job is to guide a developer from either a feature request or a bug report through context collection, project analysis, planning, safe implementation, verification, and PR-ready handoff.

The v1 template supports two explicit entry points:

- `/develop-feature`: plan or implement a new feature.
- `/fix-bug`: investigate, plan, or implement a bug fix.

Both commands use one shared project skill, `development-flow`, because feature work and bug fixes share the same enterprise engineering invariants: understand context first, protect the repository, avoid unsafe git operations, keep changes scoped, verify behavior, and produce reviewable artifacts.

Developer-facing workflow artifacts are Markdown in v1. A future version may switch these outputs to AsciiDoc if the project standard requires it.

The default interaction language is Russian. GigaCode should ask clarifying questions, explain blockers, summarize plans, and write developer workflow artifacts in Russian unless the user explicitly requests another language. Technical identifiers such as file names, command names, branch names, hook names, and code symbols stay ASCII/English.

## Source Requirements

The design is based on the existing analyst template concept in `docs/superpowers/specs/2026-05-17-gigacode-analyst-template-design.md` and the implementation plan in `docs/superpowers/plans/2026-05-17-gigacode-analyst-template.md`.

The developer workflow must preserve these shared assumptions:

- GigaCode follows Qwen Code-compatible project concepts, with project-local files under `.gigacode/`.
- Project skills, agents, hooks, commands, settings, rules, and templates are stored in git.
- The repository is the primary operating context.
- External systems are optional supporting context and must not be required for local smoke checks.
- Project safety rules must be enforceable by hooks and visible in repository documentation.

The developer workflow also introduces stronger enterprise safeguards because it can modify code, run tests, and prepare changes for delivery.

## Qwen Code Compatibility Baseline

GigaCode is treated as a fork of Qwen Code. File names, settings, frontmatter formats, and runtime semantics follow the official Qwen Code model where possible, with project paths renamed from `.qwen` to `.gigacode`.

The project template uses these concepts:

- Project settings equivalent to `.qwen/settings.json`.
- Project skills equivalent to `.qwen/skills/<skill-name>/SKILL.md`.
- Project subagents equivalent to `.qwen/agents/*.md`.
- Project custom commands equivalent to `.qwen/commands/*.md`.
- Command hooks configured through project settings.

For v1, assume the fork reads `.gigacode` directly. If the fork still expects `.qwen` internally, the template will need a compatibility layer or documented symlink/copy step.

## Repository Layout

```text
.gigacode/
  settings.json
  skills/
    development-flow/
      SKILL.md
  agents/
    dev-intake.md
    project-context.md
    code-map.md
    implementation-plan.md
    coder.md
    test-review.md
    pr-readiness.md
  hooks/
    git_guard.py
    preflight_check.py
    validate_development_output.py
  commands/
    develop-feature.md
    fix-bug.md
docs/
  development/
    .gitkeep
  templates/
    development-plan.md
rules/
  development-flow.md
  git-safety.md
  branch-naming.md
scripts/
  smoke-check.ps1
  smoke-check.sh
README.md
```

This layout intentionally mirrors the analyst template. The main differences are the developer-specific commands, stronger git hooks, and Markdown output templates.

## Runtime Modes

Both `/develop-feature` and `/fix-bug` support two modes.

### Plan-Only Mode

Plan-only mode performs analysis and produces a development plan without modifying source code.

It should:

1. Clarify the request type, scope, acceptance criteria, and constraints.
2. Collect project context, including analytics, Repomix output, Graphify output, and local docs when available.
3. Map relevant code paths and impacted components.
4. Identify risks, unknowns, test strategy, and rollout or rollback notes.
5. Write Markdown artifacts under `docs/development/<task-slug>/`.
6. Stop before editing code.

Plan-only mode is the default when the request is ambiguous, high-risk, or missing acceptance criteria.

### Implement Mode

Implement mode performs the full controlled development cycle.

It should:

1. Run all plan-only steps.
2. Verify git state and branch safety before editing files.
3. Require a safe feature or bugfix branch before source changes.
4. Apply scoped code changes.
5. Add or update tests proportionate to the change.
6. Run relevant verification commands.
7. Update development artifacts with implementation notes and test evidence.
8. Prepare a PR-ready summary.

Implement mode must not bypass branch protection or mutate unsafe repository state.

## Feature Flow

`/develop-feature` starts from a requested capability, business behavior, or technical improvement.

Required sequence:

1. Intake: feature name, goal, user-visible behavior, acceptance criteria, out-of-scope items, and target release constraints.
2. Context discovery: project analytics, existing feature docs, Repomix, Graphify, architecture docs, prior decisions, and related code.
3. Impact mapping: entry points, APIs, UI surfaces, services, data models, jobs, queues, events, integrations, configuration, and tests.
4. Plan: implementation steps, data changes, compatibility concerns, test strategy, rollout notes, and rollback notes.
5. Human checkpoint: stop before implementation if scope, acceptance criteria, or safety conditions are unclear.
6. Implementation: scoped edits only after git guard passes.
7. Verification: tests, lint, static checks, build, smoke checks, or targeted manual verification notes.
8. PR readiness: summary, changed areas, test evidence, risks, follow-up tasks, and reviewer notes.

## Bug Flow

`/fix-bug` starts from an observed failure, regression, incident, ticket, or test failure.

Required sequence:

1. Intake: symptom, expected behavior, actual behavior, reproduction steps, affected versions or environments, severity, and known workarounds.
2. Context discovery: project analytics, incident notes, existing docs, Repomix, Graphify, logs or stack traces provided by the user, and related code.
3. Reproduction plan: determine whether the bug can be reproduced locally, by test, by log analysis, or only from provided evidence.
4. Root-cause analysis: identify the failing path, affected code, data assumptions, dependency behavior, and regression source where possible.
5. Fix plan: minimal safe correction, tests that fail before the fix when feasible, regression coverage, rollout risks, and rollback notes.
6. Human checkpoint: stop before implementation if reproduction or impact is unclear.
7. Implementation: scoped fix only after git guard passes.
8. Verification: targeted regression tests first, then broader checks proportionate to blast radius.
9. PR readiness: root cause, fix summary, test evidence, risk notes, and follow-up monitoring suggestions.

## Required Context Sources

The developer flow must account for available project intelligence before planning or editing code.

### Project Analytics

If the repository contains analyst outputs, architecture notes, feature documentation, incident writeups, or similar project analytics, the workflow must read and summarize the relevant parts before planning implementation.

Examples:

- `docs/features/**`
- `docs/analysis/**`
- `docs/architecture/**`
- `docs/incidents/**`
- project-specific ADRs or decision records

If no analytics are found, the workflow records that limitation in the development artifacts.

### Repomix

If Repomix output exists in the repository, the workflow uses it as a compact repository snapshot. If the `repomix` command is available and project policy allows generating it, the workflow may recommend or run it depending on permissions.

Repomix is supporting context, not a substitute for inspecting the current files that will be modified. Before editing a file, the workflow must read the live file from the working tree.

If Repomix output is absent and the `repomix` command is unavailable or not allowed, the workflow falls back to direct repository inspection:

1. List repository files with fast local search such as `rg --files`.
2. Read project entry points, build files, package manifests, tests, and docs directly.
3. Use targeted search for feature names, bug symptoms, APIs, events, commands, and error messages.
4. Record in `context.md` that Repomix was unavailable and direct inspection was used.

Absence of Repomix must not block plan-only mode or implement mode. It only reduces the amount of precomputed repository context available to the workflow.

### Graphify

If Graphify output exists or the Graphify skill is available, the workflow uses it to understand repository structure, clusters, dependencies, and likely impact areas.

Graphify output is a navigation aid. Claims about current behavior still need confirmation from live code, tests, docs, or user-provided evidence.

If Graphify output and the Graphify skill are unavailable, the workflow falls back to manual impact mapping:

1. Identify entry points from routes, controllers, handlers, commands, jobs, tests, and package manifests.
2. Trace imports, call sites, configuration references, data models, and integration boundaries with repository search.
3. Build a small text map in `context.md` or `plan.md` that lists impacted modules, upstream callers, downstream dependencies, and unknown areas.
4. Record that Graphify was unavailable and manual mapping was used.

Absence of Graphify must not block plan-only mode or implement mode. It only means dependency and cluster analysis is derived from local inspection instead of a generated graph.

### Fallback Policy

The developer flow must be resilient when optional project-intelligence tools are missing.

Required behavior:

- If analytics are absent, continue with code, tests, local docs, and user-provided context.
- If Repomix is absent, use direct repository inspection.
- If Graphify is absent, use manual impact mapping.
- If both Repomix and Graphify are absent, perform a conservative code-map pass before planning and widen the verification strategy where risk is unclear.
- If optional context is unavailable, record the limitation in `context.md` and avoid unsupported claims.

### External Context

Jira, Confluence, issue trackers, logs, monitoring dashboards, and other external systems are optional supporting context. The template does not install or configure MCP servers in v1.

If MCP is available, the workflow may use it after confirming relevance. If MCP is unavailable, the workflow continues with code and user-provided context and records the limitation.

## Development Artifacts

Each task writes Markdown artifacts under:

```text
docs/development/<task-slug>/
```

Expected files:

```text
context.md
plan.md
implementation.md
verification.md
pr-summary.md
```

`context.md` records inputs, source context, analytics used, Repomix status, Graphify status, assumptions, and open questions.

`plan.md` records implementation steps, impacted files or modules, data and API considerations, test strategy, rollout notes, and rollback notes.

`implementation.md` records what changed, why it changed, and any important alternatives rejected during implementation.

`verification.md` records commands run, test results, failures investigated, skipped checks, and residual risk.

`pr-summary.md` records a reviewer-facing summary, changed areas, test evidence, risk notes, and follow-up tasks.

In plan-only mode, `implementation.md`, `verification.md`, and `pr-summary.md` may contain planned content and explicit "not executed" notes. They must not pretend that code was changed or tests were run.

Artifact prose is written in Russian by default. Keep technical paths, command output excerpts, branch names, class names, function names, and configuration keys unchanged.

## Skill Design

The single project skill is `development-flow`.

It defines these invariants:

- Classify every request as feature work, bug fix, or unclear.
- Ask for clarification when the request cannot be safely scoped.
- Use plan-only mode unless implement mode is explicit or clearly requested.
- Always inspect project analytics, Repomix, and Graphify when available.
- Treat code as the source of current implementation truth.
- Treat external tickets and docs as supporting context that may be stale.
- Map relevant code before editing.
- Protect user changes in the working tree.
- Use a safe branch before implementation.
- Keep changes narrowly scoped to the request.
- Add or update tests proportionate to risk.
- Record verification evidence before claiming completion.
- Never invent successful checks, commits, pushes, or deployment status.
- Communicate with the user in Russian by default and write workflow artifacts in Russian unless the user asks for another language.

The skill must also define the difference between feature and bug flows so the shared workflow does not erase their different goals.

## Agent Design

The template includes seven project subagents.

- `dev-intake`: clarifies task type, mode, scope, acceptance criteria, constraints, and missing inputs.
- `project-context`: finds and summarizes analytics, Repomix output, Graphify output, docs, external context, and project rules.
- `code-map`: maps entry points, dependencies, changed areas, tests, configuration, integrations, queues, events, and data boundaries.
- `implementation-plan`: writes the development plan, risk assessment, test strategy, rollout notes, and rollback notes.
- `coder`: performs scoped implementation in implement mode after git guard approval.
- `test-review`: runs or analyzes checks, investigates failures, and records verification evidence.
- `pr-readiness`: prepares reviewer-facing summary, changed files, test evidence, residual risks, and follow-up tasks.

Agents should use conservative permission defaults. Context, mapping, planning, test-review, and PR-readiness agents are read-oriented unless they are writing task artifacts under `docs/development/<task-slug>/`.

The `coder` agent may edit source files only in implement mode and only after branch safety passes. It must not commit, push, rewrite history, edit protected deployment settings, or overwrite unrelated user changes.

Each subagent file and each subagent role description must stay below 10,000 characters. This is a hard v1 constraint, not a guideline.

If an agent needs more detail, move reusable material into `rules/`, `docs/templates/`, or command-level workflow text. The agent file should keep only role, trigger conditions, inputs, outputs, constraints, and handoff expectations.

Smoke checks must fail if any `.gigacode/agents/*.md` file exceeds 10,000 characters.

## Enterprise Git Safety

Git safety is a hard requirement for v1.

The developer template must assume enterprise repositories with protected branches, shared environments, deployment automation, compliance requirements, and partially dirty working trees.

### Protected Branches

The workflow must block implementation and commits on protected branches, including:

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

Projects may extend this list in `rules/git-safety.md` or `.gigacode/settings.json`.

### Required Pre-Edit Checks

Before editing code in implement mode, the workflow must run or require equivalent checks:

```text
git status --short
git branch --show-current
git rev-list --left-right --count HEAD...@{u}
```

If upstream is not configured, the workflow should record that fact and avoid claims about sync status.

If the current branch is protected, implementation must stop and instruct the user to create a safe task branch.

If the working tree has existing changes, the workflow must identify them before editing and avoid overwriting them. If existing changes overlap with the task, the workflow asks for direction.

### Forbidden Operations

The workflow must block or require explicit human confirmation for operations that can damage repository history, discard work, or affect shared infrastructure.

Forbidden by default:

- `git reset --hard`
- `git clean -fd` or stronger variants
- `git checkout -- <path>`
- `git restore <path>` when it would discard uncommitted work
- `git rebase` on shared or protected branches
- `git push --force` or `git push --force-with-lease`
- deleting local or remote branches
- changing remote URLs
- modifying git hooks that enforce project policy
- committing directly to protected branches
- pushing directly to protected branches

Also protected by default:

- CI/CD workflow files
- deployment manifests
- infrastructure-as-code directories
- environment files
- secrets or credential files
- production, staging, UAT, and shared test-stand configuration

Changes to these areas require a separate explicit confirmation that names the files and explains the risk.

### Commit Policy

The template prepares code for review but does not auto-commit by default.

If a project enables commit support later, hooks must enforce:

- no commits on protected branches;
- no commits with dirty unrelated changes mixed into the index;
- no commits without recorded verification status;
- no commits that include secrets or local environment files;
- no commits that include generated temporary artifacts unless explicitly allowed.

For v1, PR readiness means "ready for the human or CI workflow to turn into a PR", not "the agent has committed and pushed".

## Hooks

The template includes three hook scripts.

### `git_guard.py`

`git_guard.py` is the central safety hook.

It should:

- detect current branch;
- match protected branch patterns;
- inspect working tree state;
- detect staged unrelated changes when possible;
- inspect incoming shell commands for unsafe git operations;
- block direct commits or pushes to protected branches;
- block destructive git commands by default;
- block edits to protected infrastructure paths unless explicitly confirmed;
- return a clear reason and remediation step when blocking.

This hook should run before tool execution for shell commands and before file edits when supported by GigaCode/Qwen hook semantics. If hook semantics cannot intercept a specific operation, the same rules must still be embedded in skill and agent instructions.

### `preflight_check.py`

`preflight_check.py` validates developer workflow prompts.

It should:

- ignore unrelated prompts;
- detect `/develop-feature` and `/fix-bug`;
- require task name or summary;
- identify requested mode or default to plan-only;
- require feature acceptance criteria for feature work when implement mode is requested;
- require symptom, expected behavior, actual behavior, or reproduction evidence for bug work when implement mode is requested;
- require safe branch confirmation before implement mode edits;
- remind the workflow to inspect analytics, Repomix, and Graphify when available;
- remind the workflow to use documented fallbacks when Repomix or Graphify are unavailable.

### `validate_development_output.py`

`validate_development_output.py` validates completion claims and Markdown artifacts.

It should:

- verify expected `docs/development/<task-slug>/` files exist when the workflow claims completion;
- block unsupported claims that tests passed without recorded commands;
- block placeholders such as `TODO`, `TBD`, and `FIXME` in final artifacts;
- verify plan-only artifacts do not claim implementation happened;
- verify implement-mode artifacts include git state, changed files, and verification evidence;
- verify that any skipped checks are explicitly listed with reasons.

## Settings

`.gigacode/settings.json` should include only project-safe defaults:

- hook definitions for preflight, git guard, and output validation;
- permission rules that deny destructive git operations by default;
- permission rules that protect secrets, local env files, and shared environment configuration;
- conservative edit defaults;
- UI defaults suitable for developers, such as citations, line numbers, and compact shell output;
- optional MCP allowlist guidance if project names are known later.

The settings file must not include secrets, personal paths, mandatory MCP credentials, deployment tokens, or environment-specific commands.

## Commands

### `/develop-feature`

The command starts the feature workflow.

Expected user input:

- feature name or short summary;
- requested mode, if not plan-only;
- acceptance criteria or business behavior;
- constraints, related tickets, docs, or known affected areas.

The command must instruct GigaCode to use the `development-flow` skill and follow the feature sequence.

### `/fix-bug`

The command starts the bug workflow.

Expected user input:

- bug summary;
- expected behavior;
- actual behavior;
- reproduction steps or evidence when available;
- affected environment, version, or release when known;
- requested mode, if not plan-only.

The command must instruct GigaCode to use the `development-flow` skill and follow the bug sequence.

## Smoke Checks

The repository includes lightweight checks for both target operating systems:

- `scripts/smoke-check.ps1` for Windows PowerShell.
- `scripts/smoke-check.sh` for Linux shells.

The checks verify:

- expected files exist;
- `.gigacode/settings.json` is valid JSON;
- command and agent files have frontmatter;
- each subagent file stays below 10,000 characters;
- hook scripts execute with sample JSON;
- `git_guard.py` blocks protected branch commit scenarios in dry-run samples;
- Markdown templates exist and do not contain unresolved placeholders.

Smoke checks must not require GigaCode, Repomix, Graphify, Atlassian MCP, network access, or enterprise credentials.

## README Requirements

The README must explain:

- what the developer template is for;
- that the workflow communicates and writes developer artifacts in Russian by default;
- the difference between `/develop-feature` and `/fix-bug`;
- the difference between plan-only and implement modes;
- Windows and Linux prerequisites;
- how to run smoke checks;
- expected Markdown outputs under `docs/development/<task-slug>/`;
- how analytics, Repomix, and Graphify are used when available;
- how the workflow falls back when Repomix or Graphify are unavailable;
- MCP responsibility and limitations;
- enterprise git safety rules;
- why the template does not auto-commit or auto-push by default;
- how to adapt protected branch and protected path rules for a real team repository.

## Out of Scope for v1

- Installing or configuring Repomix.
- Installing or configuring Graphify.
- Installing or configuring Atlassian or issue-tracker MCP.
- Automatically committing changes.
- Automatically pushing branches.
- Automatically opening pull requests.
- Running deployment commands.
- Modifying production, staging, UAT, or shared test-stand configuration without explicit human confirmation.
- Guaranteeing compatibility with a fork that has not implemented `.gigacode` path discovery.

## Success Criteria

The v1 is successful when:

- The repository contains a complete `.gigacode` project configuration for developer workflows.
- `/develop-feature` and `/fix-bug` are available as explicit project commands.
- Both commands support plan-only and implement modes.
- The workflow uses Russian by default for user interaction and Markdown development artifacts.
- The workflow inspects analytics, Repomix, and Graphify when available.
- The workflow has explicit fallbacks for missing analytics, Repomix, and Graphify.
- Developer artifacts are Markdown files under `docs/development/<task-slug>/`.
- Git guardrails block protected branches, destructive history operations, direct protected-branch commits, and dangerous pushes.
- The template does not auto-commit or auto-push by default.
- Hook scripts can be smoke-tested without enterprise credentials.
- README explains safe enterprise operation clearly enough for a real team repository.
- Every project subagent file and role description stays below 10,000 characters.
