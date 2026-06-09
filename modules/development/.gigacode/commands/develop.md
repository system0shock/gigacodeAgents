---
description: Run the plan-first development flow for one Java/Kotlin task.
---

Use the `feature-development` skill.

Develop exactly one task from these user arguments:

{{args}}

Follow this sequence:

1. Run `dev-plan` to explore the code and write `docs/plans/<task-slug>.md` with all required sections.
2. Present the plan and ask me to approve it. Set `Status: approved` only after my explicit confirmation.
3. Run `dev-implement` to execute the plan in small compilable steps.
4. Run `dev-test` to cover every changed production class with JUnit 5 tests.
5. Run `dev-review` for the final read-only review and fix its blocking findings.
6. Compile and run tests via the Gradle/Maven wrapper when available; otherwise state the limitation.
7. Report changed files, test status, and plan deviations before claiming completion.
