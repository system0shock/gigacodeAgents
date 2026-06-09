# Mocking Rules

## Digest

- Kotlin: MockK. Java: Mockito (with `mockito-kotlin` in mixed codebases).
- Mock collaborators (ports, repositories, clients) - never the class under test, never value objects.
- Prefer fakes (in-memory implementations) over mocks for repositories and stores.
- Verify behavior, not implementation: `verify` only when the interaction IS the contract (e.g. "sends notification").
- Avoid relaxed/lenient mocks; stub exactly what the test needs.
- Reset nothing: create fresh mocks per test via `@BeforeEach` or test-scoped variables.

## What to mock

Mock at architectural boundaries: external services, time (`Clock`), randomness, persistence ports. Inside the domain, use real objects - if wiring them is painful, the design needs fixing, not more mocks.

## MockK (Kotlin)

- `mockk<PaymentPort>()` with explicit `every { ... } returns ...` stubs.
- `coEvery`/`coVerify` for suspend functions.
- `confirmVerified(mock)` only when the full interaction set is the contract.
- Avoid `relaxed = true`; it hides missing stubs.

## Mockito (Java)

- `@ExtendWith(MockitoExtension.class)` with `@Mock`/`@InjectMocks` or explicit `Mockito.mock(...)`.
- `when(...).thenReturn(...)` for stubs; `verifyNoMoreInteractions` sparingly.
- Use `ArgumentCaptor` to assert on complex arguments instead of deep `eq()` trees.

## Anti-patterns

- Mock returning a mock returning a mock - flatten the design instead.
- Verifying getters or pure functions.
- Stubbing the same call differently across one test.
