# План: card-blocking-limit

Status: approved

## Goal

Добавить лимит на количество блокировок карты за сутки.

## Scope

- Входит: проверка лимита в CardBlockingService, новая настройка лимита.
- Не входит: изменение UI и нотификаций.

## Steps

1. Добавить параметр лимита в конфигурацию CardBlockingProperties.
2. Добавить проверку лимита в CardBlockingService.block().
3. Покрыть новую ветку тестами CardBlockingServiceTest.

## Affected files

- src/main/kotlin/com/example/card/CardBlockingService.kt
- src/main/kotlin/com/example/card/CardBlockingProperties.kt
- src/test/kotlin/com/example/card/CardBlockingServiceTest.kt

## Verification

Юнит-тесты JUnit 5 на превышение лимита, граничное значение и обычный путь.

## Risks

- Гонка при параллельных блокировках: лимит проверяется и инкрементируется атомарно в репозитории.
