# GigaCode Analytics Module

This module provides a GigaCode project configuration for analysts who need to reverse-analyze one business feature and produce evidence-backed documentation.

The workflow is based on GigaCode project configuration semantics and the `.gigacode/` directory.

## What It Contains

- `.gigacode/settings.json` - project settings, permissions, and hook wiring.
- `.gigacode/skills/reverse-analysis/SKILL.md` - workflow rules for reverse analysis.
- `.gigacode/agents/` - five focused subagents for intake, code mapping, documentation, evidence review, and final review.
- `.gigacode/hooks/` - preflight and output validation hooks.
- `.gigacode/commands/reverse-analysis.md` - project slash command.
- `docs/templates/feature-analysis.adoc` - AsciiDoc output contract.
- `rules/` - shared rules for reverse analysis and branch names.

## Prerequisites

- GigaCode CLI installed as `gigacode`.
- Git.
- Python 3 available as `python`.
- Optional: Atlassian MCP configured by your team if Jira or Confluence access is needed.

This repository does not install MCP servers or store credentials.

## Windows Quick Start

```powershell
git clone <repo-url>
cd <repo>\modules\analytics
.\scripts\smoke-check.ps1
gigacode
```

Then run inside GigaCode:

```text
/reverse-analysis feature "Card Blocking" jira ABC-123
```

## Linux Quick Start

```bash
git clone <repo-url>
cd <repo>/modules/analytics
bash scripts/smoke-check.sh
gigacode
```

Then run inside GigaCode:

```text
/reverse-analysis feature "Card Blocking" jira ABC-123
```

## Code-Only Analysis

If Jira and Confluence are unavailable, say that explicitly:

```text
/reverse-analysis feature "Card Blocking" code-only, no Jira, no Confluence
```

The generated files must state that external context was not used.

## Expected Output

GigaCode should create AsciiDoc files under:

```text
docs/features/<feature-name>/
```

Required files:

- `overview.adoc`
- `flow.adoc`
- `integrations.adoc`
- `data.adoc`
- `questions.adoc`

## Workflow

1. Intake validates the feature name and source context.
2. Code mapping identifies entry points, files, flows, integrations, and gaps.
3. The analyst confirms scope.
4. Documentation is written as AsciiDoc.
5. Evidence and gap review checks unsupported claims.
6. Final review checks structure and terminology.
7. Hooks validate the request and output.

## Subagent Size Rule

Each subagent file should stay below 10,000 characters. Move reusable details into `rules/` or templates instead of expanding agent prompts.

## Adapting For A Team Repository

Copy or keep this module as the project root used by analysts. If your GigaCode fork expects `.gigacode/` in a different location, preserve the internal layout and adjust only the outer module path.
