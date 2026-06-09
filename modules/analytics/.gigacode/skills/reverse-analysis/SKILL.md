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
7. After the analyst confirms scope, record it in `docs/scopes/<feature-slug>.md` with the line `Статус: подтвержден` and the line `Каталог результата: docs/features/<feature-slug>/` before drafting.
8. Do not present unsupported claims as facts.
9. Write final analyst deliverables in AsciiDoc.
10. Write all final analyst deliverables in Russian.
11. Before drafting, check `docs/examples/` for a user-provided style reference and existing `docs/features/` entries for repo-level consistency. Match their structure and terminology when present.

## Required Output Files

Create these files under `docs/features/<feature-name>/`:

- `overview.adoc`
- `flow.adoc`
- `integrations.adoc`
- `data.adoc`
- `questions.adoc`

## Evidence Labels

Canonical labels are Russian (see `rules/reverse-analysis.md`); English forms are accepted aliases:

- `Источник: код` (alias `Source: code`)
- `Источник: jira` (alias `Source: jira`)
- `Источник: confluence` (alias `Source: confluence`)
- `Источник: пользователь` (alias `Source: user`)
- `Статус: предположение` (alias `Status: assumption`)
- `Статус: открытый вопрос` (alias `Status: open question`)

The output validation hook requires at least one evidence label in every content file and a status label in `questions.adoc`.

## Agent Flow

Use these project agents when appropriate:

1. `intake-scope`
2. `code-mapping`
3. `documentation`
4. `review`

Stop for analyst confirmation after code mapping and before final drafting, then record the confirmed scope in `docs/scopes/`.
