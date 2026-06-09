# Java Style

## Digest

- Immutability first: `final` fields, records for value types, unmodifiable collections.
- Constructor injection for dependencies; no field injection.
- SLF4J logging only - `System.out.print*` and `printStackTrace` are blocked by hooks.
- Exceptions: never swallow; wrap with context and rethrow specific types.
- `Optional` for return values only - not for fields or parameters.
- No wildcard imports.
- Keep methods short and single-purpose; extract private methods aggressively.

## Types and structure

- Records for immutable data carriers when the language level allows; otherwise final classes with final fields.
- Interfaces for behavior contracts; avoid abstract base classes for sharing code.
- Visibility as tight as possible: package-private by default, public only for the API surface.

## Collections and streams

- Return `List`/`Map`/`Set` interfaces, instantiate immutable copies (`List.copyOf`).
- Streams for transformation pipelines; classic loops when mutation or early exit is clearer.

## Error handling

- Validate arguments early (`Objects.requireNonNull`, guard clauses).
- Custom exceptions per domain failure mode; carry identifiers in the message.
- Log or rethrow - never both; never `catch (Exception ignored)`.

## Logging

- `private static final Logger log = LoggerFactory.getLogger(Foo.class);`
- Parameterized messages: `log.info("payment {} rejected: {}", id, reason);`
- No sensitive data (tokens, card numbers) in logs.
