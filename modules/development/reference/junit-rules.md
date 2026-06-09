# JUnit 5 Rules

## Digest

- Use JUnit 5 only: `org.junit.jupiter` imports. JUnit 4 (`org.junit.Test`, `junit.framework`) is blocked by hooks.
- Name tests after behavior: `` `should reject transfer when balance is too low` `` (Kotlin backticks) or `shouldRejectTransferWhenBalanceIsTooLow` (Java).
- Structure every test as Arrange-Act-Assert (or given-when-then), separated by blank lines.
- One behavior per test method; split multi-step scenarios.
- Use `@ParameterizedTest` with `@CsvSource`/`@MethodSource` for input matrices instead of copy-pasted tests.
- Group related cases with `@Nested` classes named after the scenario.
- No `@Disabled` without a reason string; no interdependent tests; no shared mutable state between tests.
- Every test must assert or verify something - a test without assertions is blocked by hooks.

## Naming and structure

Test class mirrors the production class: `CardService` -> `CardServiceTest` in the mirrored source-set path (`src/main/kotlin/...` -> `src/test/kotlin/...`).

Inside the class, order tests from the main success path to edge cases and errors. Use `@DisplayName` only when the method name cannot carry the full behavior description.

## Lifecycle

- Prefer `@BeforeEach` factory methods over field initializers with logic.
- Avoid `@TestInstance(PER_CLASS)` unless required by `@MethodSource`.
- Clean external state in `@AfterEach` only when the test actually creates it.

## Parameterized tests

- `@CsvSource` for short literal matrices, `@MethodSource` for objects.
- Name the parameters in the method signature so failures read well.

## Assertions

- Group related assertions with `assertAll` so all failures surface at once.
- Use `assertThrows` for exception paths and assert on the message or type.
- See `reference/assertions.md` for the assertion-library conventions.

## Test data

- Prefer builder functions or test factories over shared fixtures.
- Keep test data minimal: only the fields the behavior under test reads.
