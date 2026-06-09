---
name: feature-development
description: MUST BE USED for Java/Kotlin development tasks - plan-first workflow with human approval, mandatory JUnit 5 tests, and deterministic hook validation.
---

# Feature Development

Use this skill when the user asks to implement, fix, refactor, or extend Java/Kotlin code.

## Operating Rules

1. Work on one task at a time.
2. Plan before code: write `docs/plans/<task-slug>.md` from `docs/templates/plan-template.md` with all sections from `rules/plan-format.md`.
3. The user approves the plan: `Status: approved` is set only after explicit user confirmation. Hooks gate `src/` edits on this.
4. Implement in small steps that keep the code compilable.
5. Every changed production class gets a JUnit 5 test, unless the plan states `no-tests: <reason>`.
6. Follow `reference/` rules for style, tests, mocks, and assertions - hooks enforce the deterministic subset.
7. Static checks always run; real build/lint/test runs are optional (`build-check: on` in the plan or `GIGACODE_DEV_RUN_BUILD=1`) and their absence is recorded as a limitation.
8. Use Serena MCP, `graphify`, and `repomix` as optional exploration accelerators; record the limitation when unavailable.
9. Do not edit build files without explicit user confirmation.
10. Update the plan when implementation deviates from it.

## Agent Flow

Use these project agents in order:

1. `dev-plan` - explore and write the plan.
2. User approves the plan.
3. `dev-implement` - production changes.
4. `dev-test` - JUnit 5 tests.
5. `dev-review` - final read-only review.

Stop for user approval after planning and before any `src/` edits.

## Validation

Hooks validate the flow deterministically: prompt completeness, plan format and approval, dangerous commands, per-file static checks, and a final Stop re-scan with test-existence enforcement.
