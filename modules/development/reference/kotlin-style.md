# Kotlin Style

## Digest

- `val` over `var`; immutable data structures by default.
- Never use `!!` - hooks block it in production code. Use `requireNotNull`, `checkNotNull`, `?:` or restructure.
- No `println` or `printStackTrace` in production code - use SLF4J logging.
- Data classes for DTOs and value types; sealed classes/interfaces for closed hierarchies.
- Expression bodies for single-expression functions.
- No wildcard imports.
- Structured concurrency only: no `GlobalScope`; scope coroutines to the owning component.
- Keep functions small; extract when a function does more than one thing.

## Null safety

Model absence with nullable types at boundaries and convert to non-null as early as possible. Prefer `?.let`, `?:` and early returns over nested null checks. `lateinit` only for framework-injected fields.

## Classes and functions

- Constructor injection for dependencies; avoid service locators.
- Default parameter values instead of telescoping overloads.
- Extension functions for adapting foreign types, not for core domain logic.

## Collections

- Prefer read-only `List`/`Map`/`Set` types in signatures.
- Chain stdlib operators (`map`, `filter`, `groupBy`) but extract a named function when a chain exceeds ~3 steps.

## Coroutines

- Suspend functions must not block threads; wrap blocking IO in `withContext(Dispatchers.IO)`.
- Propagate cancellation; never swallow `CancellationException`.

## Errors and logging

- Throw specific exceptions with context; do not catch-and-ignore.
- SLF4J (`private val log = LoggerFactory.getLogger(...)` or KotlinLogging); parameterized messages, no string concatenation.
