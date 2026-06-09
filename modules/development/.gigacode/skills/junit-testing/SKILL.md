---
name: junit-testing
description: MUST BE USED when the user asks to write or improve unit tests for Java/Kotlin code without a full development task.
---

# JUnit Testing

Use this skill for standalone test-writing requests (`/write-tests`).

## Operating Rules

1. Read `reference/junit-rules.md`, `reference/mocking.md`, and `reference/assertions.md` before writing tests.
2. JUnit 5 only (`org.junit.jupiter`); JUnit 4 imports are blocked by hooks.
3. Place tests in the mirrored source-set path: `src/main/kotlin/...Foo.kt` -> `src/test/kotlin/...FooTest.kt`.
4. Name tests after behavior; structure as Arrange-Act-Assert; one behavior per test.
5. Every test must assert or verify - assertion-free tests are blocked.
6. MockK for Kotlin, Mockito for Java; mock boundaries, prefer fakes for repositories.
7. Use `@ParameterizedTest` for input matrices and `@Nested` for grouping scenarios.
8. Run the tests via the Gradle/Maven wrapper when available (`reference/build-tools.md`); otherwise state the limitation.

## Scope

- Read the class under test and its collaborators before writing.
- Cover the main success path, edge cases, and error paths of the requested class only.
- Do not change production code; if it is untestable, report why and what minimal refactoring would help.
