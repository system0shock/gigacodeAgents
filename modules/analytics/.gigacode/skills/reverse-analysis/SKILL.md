---
name: reverse-analysis
description: MUST BE USED for the one-time reverse-analysis bootstrap of one business feature — technical AsciiDoc, an OpenSpec capability spec, and the corporate analytics/architecture tree, all with explicit evidence.
---

# Reverse Analysis

Use this skill when the analyst asks to investigate, document, explain, or
reverse-analyze a business feature. Reverse analysis is a **one-time bootstrap
per feature**: it creates the documentation baseline from existing code. After
the bootstrap, documentation evolves through the OpenSpec change lifecycle
(a separate flow, out of scope here).

## Operating rules

1. Analyze one business feature, not the whole repository.
2. Code is the source of truth; Jira/Confluence are supporting context that may
   be stale. If Atlassian MCP is unavailable, continue with code + user context
   and state that limitation.
3. Map code before drafting prose.
4. Stop for analyst scope confirmation after code mapping.
5. Never present unsupported claims as facts.
6. Final analyst deliverables are AsciiDoc, in Russian.
7. Derivation discipline: code -> technical docs -> spec -> final tree. Fixes
   flow up; content flows down. Evidence review happens on the technical layer
   before any derivation.

## Two-layer output

**Technical (working) layer** — `docs/features/<feature>/`: `overview.adoc`,
`flow.adoc`, `integrations.adoc`, `data.adoc`, `questions.adoc` (Russian, with
evidence labels), plus `journal.md` and `manifest.json`. Each `.adoc` carries a
metadata header (`:feature:`, `:run-date:`, `:code-commit:`). Frozen after the
run. `questions.adoc` has no final-tree counterpart by design.

**Final (corporate) layer** — generated at the repo root: `analytics/` +
`architecture/` (see `docs/templates/feature-analysis.adoc` and
`rules/reverse-analysis.md`). Files `UpperCamelCase`, directories `kebab-case`.

The capability spec is `openspec/specs/<capability>/spec.md` — current truth,
written once per new capability (see `rules/openspec.md`).

## Evidence labels

`Источник: код|jira|confluence|пользователь`,
`Статус: предположение|открытый вопрос`.

## Agents

Three project agents — intake is handled by the main session (no intake agent):

- `code-mapping` — code map for the confirmed scope (Serena -> `rg`, module map).
- `documentation` — technical docs -> spec -> final tree.
- `verifier` — evidence review (step 5) and derivation verification (step 8).

## Pipeline and manifest lifecycle

`docs/features/<feature>/manifest.json` tracks status
`scoping -> draft -> confirmed -> complete`:

1. **Launch** `/reverse-analysis "<feature>"`; preflight validates the request.
2. **Intake in the main session**: record scope (feature, included/excluded,
   sources, known systems) in `journal.md`; create `manifest.json` at `scoping`
   (copy `docs/templates/manifest.json`).
3. **Code mapping** (`code-mapping` agent) -> map in `journal.md`.
   **Stop: analyst confirms scope.**
4. **Technical draft** (`documentation` agent) -> the 5 `.adoc` files; set
   status `draft`.
5. **Evidence review** (`verifier`, Mode 1) on the technical layer; fixes land
   there; set status `confirmed`.
6. **Spec extraction** (`documentation` agent) ->
   `openspec/specs/<capability>/spec.md`; `openspec validate --specs --strict`
   must pass.
7. **Final generation** (`documentation` agent) -> `analytics/` + `architecture/`.
8. **Derivation verification** (`verifier`, Mode 2): final <-> spec <->
   technical, structural completeness.
9. **Close**: finalize `manifest.json` (`produced`, status `complete`); append
   final-artifact links to the technical docs' headers; freeze the technical
   layer.
