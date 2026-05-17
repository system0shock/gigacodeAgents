# GigaCode Analyst Template Design

## Goal

Create a Git-ready project template for analysts who use the GigaCode CLI, a fork of Qwen Code. The template must be usable on Windows and Linux, must follow Qwen Code configuration semantics, and must replace user-facing `qwen` naming with `gigacode`.

The first version is a self-contained analytics module. Analysts clone the repository, open `modules/analytics/`, run `gigacode`, and use the included project-level skills, agents, hooks, commands, and rules. Future modules can be added next to it, such as `modules/development/` and `modules/nt/`.

Final analyst-facing documentation produced by the workflow must be written in AsciiDoc.

## Source Requirements

The design is based on `core_docs/gigacode_reverse_analysis_brief.pdf` and `core_docs/gigacode_reverse_analysis_detailed_reworked.pdf`.

Additional subagent design inspiration may be taken from `https://github.com/VoltAgent/awesome-claude-code-subagents`. That repository is a Claude Code subagent catalog, so it is a reference for role boundaries, specialization patterns, and prompt structure only. Any reused idea must be adapted to GigaCode/Qwen Code frontmatter, tool naming, and project layout.

The v1 workflow must support reverse analysis of one business feature at a time:

1. Collect feature scope and external context when available.
2. Map relevant code before writing documentation.
3. Ask the human to confirm scope before drafting.
4. Produce documentation with explicit evidence, gaps, assumptions, and open questions.
5. Validate output before treating it as usable.

## Qwen Code Compatibility Baseline

GigaCode is treated as a fork of Qwen Code. File names, settings, frontmatter formats, and runtime semantics follow the official Qwen Code documentation, with project paths renamed from `.qwen` to `.gigacode`.

The project template uses these Qwen Code concepts:

- Project settings equivalent to `.qwen/settings.json`.
- Project skills equivalent to `.qwen/skills/<skill-name>/SKILL.md`.
- Project subagents equivalent to `.qwen/agents/*.md`.
- Project custom commands equivalent to `.qwen/commands/*.md`.
- Hooks configured through project settings and executed as command hooks.

If the fork still expects `.qwen` internally, the template will need a compatibility layer or documented symlink/copy step. For v1, assume the fork reads `.gigacode` directly.

## Repository Layout

```text
modules/
  analytics/
    .gigacode/
      settings.json
      skills/
        reverse-analysis/
          SKILL.md
      agents/
        intake-scope.md
        code-mapping.md
        documentation.md
        evidence-gap.md
        review.md
      hooks/
        preflight_check.py
        validate_output.py
      commands/
        reverse-analysis.md
    docs/
      features/
        .gitkeep
      templates/
        feature-analysis.adoc
    rules/
      reverse-analysis.md
      branch-naming.md
    scripts/
      smoke-check.ps1
      smoke-check.sh
    README.md
```

## Runtime Workflow

The analyst starts from `modules/analytics/` and runs `gigacode`.

The primary entry point is the project custom command `/reverse-analysis`. The command instructs GigaCode to use the `reverse-analysis` skill, gather the feature name and source context, and produce documentation under `docs/features/<feature-name>/`.

The workflow has this sequence:

1. Intake and preflight: validate the feature name, external context status, target directory, rules, and branch guidance.
2. Context collection: use Jira/Confluence only if Atlassian MCP is already installed and available.
3. Code mapping: identify entry points, relevant files, integrations, dependencies, and unclear areas.
4. Human scope confirmation: stop before drafting and ask the analyst to confirm the scope.
5. Documentation drafting: create the feature documentation files from confirmed facts.
6. Evidence and gap review: separate confirmed facts from assumptions and open questions.
7. Final review: check template compliance, terminology, and unsupported claims.
8. Output validation: run the validation hook logic before considering the result complete.

## Skill Design

The single project skill is `reverse-analysis`.

It defines these invariants:

- Analyze one business feature, not the whole system.
- Code is the primary source for current implementation.
- Jira and Confluence are supporting context and may be stale.
- Unsupported claims go to assumptions or open questions, not the main factual narrative.
- Ask the analyst instead of inventing missing context.
- Map code before writing documentation.
- Keep evidence visible enough for review.

The skill also defines the expected documentation structure:

```text
docs/features/<feature-name>/
  overview.adoc
  flow.adoc
  integrations.adoc
  data.adoc
  questions.adoc
```

All generated feature files must be valid AsciiDoc. Markdown headings, tables, and fenced code blocks should be avoided in generated analyst artifacts unless they are inside literal examples where Markdown syntax is being discussed.

## Agent Design

The template includes five project subagents:

- `intake-scope`: clarifies feature boundaries, included and excluded scope, Jira/Confluence availability, and known unknowns.
- `code-mapping`: maps entry points, call chains, relevant files, dependencies, integrations, APIs, queues, events, and data boundaries.
- `documentation`: writes the feature documentation using only confirmed scope, code facts, external context, and explicit assumptions.
- `evidence-gap`: checks claims against sources, builds evidence notes, and identifies contradictions and missing data.
- `review`: checks final structure, terminology, style, and unsupported claims without adding new facts.

Agents should use conservative permission defaults. Review and evidence agents should be read-oriented. Documentation may edit the `docs/features/<feature-name>/` output directory when the user has approved scope.

Each subagent file should stay below 10,000 characters. If instructions approach that limit, move reusable details into `rules/` or templates and keep the agent prompt focused on role, inputs, outputs, and constraints.

When drafting the subagent files, use the VoltAgent catalog as an additional source for proven subagent role patterns. Do not copy large prompts verbatim; extract only relevant structural ideas such as focused descriptions, single responsibility, clear deliverables, and explicit tool boundaries.

## Hooks

The template includes two hook scripts.

`preflight_check.py` validates incoming reverse-analysis requests. It should detect whether the prompt includes a feature name, a Jira/Confluence reference or explicit refusal, and enough target-output context. If input is incomplete, it should return a blocking response with concrete questions.

`validate_output.py` validates generated AsciiDoc documentation. It should check for expected `.adoc` files, required sections, open questions, missing evidence markers, and unfinished placeholders such as `TODO`, `TBD`, or `FIXME`.

Hook wiring belongs in `.gigacode/settings.json` using the same hook event and command-hook semantics as Qwen Code. The preflight hook should run on prompt submission. The validation hook should run near response completion or before/after writes, depending on the available GigaCode hook behavior inherited from Qwen Code.

## Settings

`.gigacode/settings.json` should include only project-safe defaults:

- Hook definitions for preflight and validation.
- Permission rules that protect secrets and destructive shell operations.
- UI defaults suitable for analysts, such as citations and line numbers enabled.
- Optional MCP allowlist guidance if project names are known later.

The settings file must not include secrets, personal paths, or mandatory Atlassian MCP credentials.

## MCP Policy

Atlassian MCP is not installed or configured by this repository in v1. Analysts or administrators install MCP themselves.

The template documents how the workflow behaves:

- If Atlassian MCP is available, use it to fetch Jira and Confluence context.
- If Atlassian MCP is unavailable, continue only with code and user-provided context.
- If no Jira/Confluence context is used, explicitly state that limitation in the output.

## Smoke Checks

The analytics module includes lightweight checks for both target operating systems:

- `modules/analytics/scripts/smoke-check.ps1` for Windows PowerShell.
- `modules/analytics/scripts/smoke-check.sh` for Linux shells.

The checks verify repository structure, JSON validity, expected files, YAML frontmatter presence, and direct hook-script execution. They do not require `gigacode` or Atlassian MCP to be installed.

## README Requirements

The README must explain:

- What the template is for.
- Windows and Linux prerequisites.
- How to clone and start using the project.
- How to run smoke checks.
- How to invoke `/reverse-analysis`.
- Expected inputs and outputs.
- That generated analyst deliverables are AsciiDoc files under `docs/features/<feature-name>/`.
- MCP responsibility and limitations.
- How to adapt the template for a real team repository.

## Out of Scope for v1

- Installing or configuring Atlassian MCP.
- Copying the template into arbitrary existing repositories.
- Building a package manager, installer, or global user-scope setup.
- CI integration.
- Automatic branch creation or pull request creation.
- Guaranteed compatibility with a fork that has not implemented `.gigacode` path discovery.

## Success Criteria

The v1 is successful when:

- The repository contains a complete `.gigacode` project configuration.
- A user can inspect all skills, agents, hooks, settings, commands, and rules in git.
- The README provides a two-command style quick start after prerequisites are installed.
- Smoke checks pass on Windows and Linux-compatible shell environments.
- Generated AsciiDoc documentation workflow is constrained to one feature and separates facts, assumptions, gaps, and questions.
- Project subagent files stay below 10,000 characters unless a future design explicitly justifies a larger file.
