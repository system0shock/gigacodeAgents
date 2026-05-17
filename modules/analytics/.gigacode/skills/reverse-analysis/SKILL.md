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
