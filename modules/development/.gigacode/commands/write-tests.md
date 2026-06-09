---
description: Write JUnit 5 tests for one Java/Kotlin class or path.
---

Use the `junit-testing` skill.

Write tests for exactly this target:

{{args}}

Follow this sequence:

1. Read the class under test and its collaborators.
2. Read `reference/junit-rules.md`, `reference/mocking.md`, and `reference/assertions.md`.
3. Write JUnit 5 tests in the mirrored `src/test/...` path: success path, edge cases, error paths.
4. Run the tests via the Gradle/Maven wrapper when available; otherwise state the limitation.
5. Report covered behaviors and remaining risks.
