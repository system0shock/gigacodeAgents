# GigaCode Developer Template

This repository is a GigaCode project template for enterprise developer workflows.

The default workflow language is Russian. GigaCode asks clarifying questions, explains blockers, and writes Markdown development artifacts in Russian unless the user asks for another language. Technical identifiers such as file paths, commands, branch names, hook names, code symbols, package names, and raw command output stay unchanged.

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

The template blocks destructive git operations by default, including `git reset --hard`, destructive `git clean` variants, forced pushes, branch deletion, remote URL changes, and direct protected-branch commits.

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
