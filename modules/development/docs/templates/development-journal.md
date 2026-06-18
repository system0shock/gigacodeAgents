# Development Journal Template

Шаблон для `docs/development/<task-slug>/journal.md`. Результаты проверок
пишите в `verification.md`, сводку для ревьюера — в `pr-summary.md`.

## Context

- Task type: feature | bug | unclear
- Mode: plan-only | implement
- Task slug: lowercase-ascii-task-slug
- Source request: краткое описание исходного запроса
- Related tickets or docs: ссылки, номера задач или `absent`

Опишите исходный запрос, цель работы и ограничения. Пользовательские формулировки и выводы пишите на русском языке; технические идентификаторы оставляйте в исходном виде.

## Project Intelligence

- Analytics: present: <path or summary> | absent: <fallback used>
- Graphify: present: <path or summary> | absent: <fallback used>
- External context: present: <link or summary> | absent: <fallback used>

Зафиксируйте доступные источники понимания проекта. Если `Analytics` или `Graphify` отсутствуют, укажите `absent: <fallback used>`, например `absent: direct repository inspection and manual impact mapping`.

## Scope

### Included

- Перечислите подтвержденные изменения поведения, файлы, модули или пользовательские сценарии в рамках задачи.

### Excluded

- Перечислите явно исключенные изменения поведения, файлы, модули или пользовательские сценарии.

## Impact Map

- Entry points:
- Upstream callers:
- Downstream dependencies:
- Data boundaries:
- Configuration:
- Tests:
- Unknown areas:

Опишите затронутые участки и риски связей между ними. Пути, команды, имена пакетов, config keys и code symbols сохраняйте как технические идентификаторы.

## Plan

1. Опишите каждый шаг реализации или расследования в порядке выполнения.

## Verification Strategy

- Required commands:
- Manual checks:
- Skipped checks and reasons:

Укажите команды проверки, ручные проверки и причины для всего, что сознательно пропущено.

## Rollout and Rollback

- Rollout notes:
- Rollback notes:

Опишите, как изменение вводится в работу и как его откатить при проблемах.

## Implementation Notes

- Зафиксируйте ход реализации: что изменено, почему, отклонения от плана.

Заметки для ревью (changed areas, risk notes, follow-up tasks) пишите в `pr-summary.md`, а не здесь.
