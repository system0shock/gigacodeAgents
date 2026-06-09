# Assertion Rules

## Digest

- Prefer AssertJ: `assertThat(actual).isEqualTo(expected)` - readable failures, rich collection support.
- Fallback when AssertJ is absent: JUnit 5 `Assertions` (`assertEquals`, `assertTrue` with message).
- Exceptions: `assertThrows(SpecificException.class, () -> ...)` and assert on the message/fields.
- Collections: `containsExactly`, `containsExactlyInAnyOrder`, `extracting` - not size+get(i) chains.
- Add `as("context")` descriptions when the assertion alone does not explain the failure.
- Never assert on a boolean blob (`assertTrue(a == b && c.contains(d))`) - split into separate assertions.

## AssertJ patterns

```java
assertThat(payment.status()).isEqualTo(Status.REJECTED);
assertThat(events).extracting(Event::type).containsExactly(CREATED, REJECTED);
assertThatThrownBy(() -> service.transfer(req))
    .isInstanceOf(InsufficientFundsException.class)
    .hasMessageContaining("acc-42");
```

## Kotlin notes

AssertJ works fine from Kotlin. If the project already uses Kotest assertions (`shouldBe`), follow the project convention - consistency beats preference.

## Grouping

Use `assertAll` (JUnit) or AssertJ soft assertions when several independent properties of one result must all be reported on a single failure.
