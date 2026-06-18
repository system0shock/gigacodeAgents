# Модуль аналитики GigaCode

Проектная конфигурация GigaCode для аналитиков: одноразовый обратный анализ
(reverse-analysis) одной бизнес-функции по существующему коду с явными
источниками доказательств. Результат двухслойный — замороженный технический
снимок плюс корпоративное дерево документации и спецификация OpenSpec.

Итоговые документы аналитика пишутся на русском. Технические идентификаторы
(пути, команды, имена символов и хуков) не переводятся.

🚀 **Быстрый старт** (обе флоу, обе ОС): [`../../QUICK_START.md`](../../QUICK_START.md) ·
монорепозиторий: [`../../README.md`](../../README.md).

📖 **Подробное руководство** (быстрый старт, требуемый софт, разбор процесса и
архитектуры, словарь терминов): [`docs/flow-overview.md`](docs/flow-overview.md).

🔒 **Модель защиты и остаточные риски** (что enforcement гарантирует, а что
остаётся за `settings.json` + ревью): [`docs/enforcement-limitations.md`](docs/enforcement-limitations.md).

## Состав модуля

- `.gigacode/settings.json` — настройки проекта, разрешения, hooks, mcpServers.
- `.gigacode/skills/reverse-analysis/SKILL.md` — 9-шаговый процесс reverse-analysis.
- `.gigacode/agents/` — три субагента: `code-mapping`, `documentation`, `verifier`
  (intake выполняется в основной сессии, отдельного агента нет).
- `.gigacode/hooks/` — единый роутер и гейты качества.
- `.gigacode/commands/reverse-analysis.md` — проектная slash-команда.
- `openspec/` — `config.yaml` и `specs/` (спека как текущая истина).
- `docs/templates/` — шаблон техдока (`feature-analysis.adoc`) и `manifest.json`.
- `rules/` — правила анализа, OpenSpec и именования веток.
- `scripts/build_module_map.py` — карта модулей из графа Graphify.

## Требования

- GigaCode CLI (команда `gigacode`).
- Git, Python 3 (в PATH как `python3`, `python` или Windows-лаунчер `py`).
- Node.js — среда выполнения GigaCode; также запускает лаунчер хуков (`node .gigacode/hooks/run-hook.cjs`), который автоматически находит Python на любой ОС.
- PowerShell (Windows) / Bash (Linux) для smoke-проверок.
- Опционально: Serena MCP — семантический поиск кода (нужен `uv`).
- Опционально: Graphify — карта модулей.
- Опционально: Context7 MCP — свежая документация библиотек (нужен Node.js 18+).
- Опционально: Atlassian MCP — Jira/Confluence (настраивает команда).

Репозиторий не устанавливает MCP-серверы и не хранит учётные данные. Любой
опциональный инструмент можно не ставить — для каждого есть фолбэк.

## Быстрый старт

Windows:

```powershell
cd <repo>\modules\analytics
.\scripts\smoke-check.ps1
gigacode
```

Linux:

```bash
cd <repo>/modules/analytics
bash scripts/smoke-check.sh
gigacode
```

Затем в GigaCode:

```text
/reverse-analysis feature "Card Blocking" jira ABC-123
```

Анализ только по коду (без Jira/Confluence):

```text
/reverse-analysis feature "Card Blocking" code-only, no Jira, no Confluence
```

## Результат: два слоя

**Технический слой** — `docs/features/<feature>/`: `overview.adoc`, `flow.adoc`,
`integrations.adoc`, `data.adoc`, `questions.adoc`, плюс `journal.md` и
`manifest.json`. Русский AsciiDoc с метками источников; обязательный заголовок с
атрибутами `:feature:`, `:run-date:`, `:code-commit:`. После прогона
замораживается.

**Спека** — `openspec/specs/<capability>/spec.md`: функциональные требования как
текущая истина (см. `rules/openspec.md`). Пишется один раз на новую capability.

**Финальный слой** — `analytics/` + `architecture/` в корне проекта: дерево по
типам (файлы `UpperCamelCase`, каталоги `kebab-case`), производное от
технического слоя и спеки.

## Процесс (9 шагов)

1. Запуск `/reverse-analysis "<feature>"`; preflight проверяет полноту запроса.
2. Intake в основной сессии: область в `journal.md`, `manifest.json` (статус `scoping`).
3. Code mapping (`code-mapping`) → карта в `journal.md`. Остановка: подтверждение области.
4. Технический черновик (`documentation`) → пять `.adoc` (статус `draft`).
5. Проверка доказуемости (`verifier`) по техслою → статус `confirmed`.
6. Извлечение спеки (`documentation`) → `openspec/specs/<capability>/spec.md`.
7. Финальная генерация (`documentation`) → `analytics/` + `architecture/`.
8. Проверка деривации (`verifier`): финал ↔ спека ↔ техслой.
9. Закрытие: `manifest.json` (статус `complete`), заморозка технического слоя.

## Serena MCP — семантический поиск кода

Без Serena агенты ищут через `rg`. С Serena — находят символы семантически и
расширяют их вместо дублирования.

Предварительно (один раз на машину):

```text
pip install uv          # или см. https://docs.astral.sh/uv/
uv tool install -p 3.13 serena-agent   # если uv не в PATH: python -m uv tool install -p 3.13 serena-agent
serena init             # инициализирует LSP-бэкенд
```

Per-project:

```text
serena project create   # создаёт .serena/project.yml
```

Шаблон уже содержит `.serena/project.yml` — замените `project_name` и
`ignored_paths` под свой проект. Обязательно добавьте поле `languages:` в
`.serena/project.yml` — без него Serena 1.5.3+ не определяет язык проекта.
На Qwen/GigaCode MCP-сервер может стартовать вне корня проекта; если Serena
сообщает неверный рут, укажите явный путь: `--project <путь>` вместо
`--project-from-cwd`. Serena объявлена в `settings.json`
(`mcpServers.serena`); напоминания подключены асинхронными hooks. **Фолбэк:**
если `serena` недоступен, агенты переключаются на `rg`, а smoke-проверки
проходят без него.

## Карта модулей (Graphify)

`gate_context_inject` на старте сессии инжектит `.gigacode/context/module-map.md`
— компактную карту модулей. Карта генерируется из графа знаний Graphify:

1. `pip install graphifyy`
2. `/graphify .` (повторный прогон — `/graphify . --update`)
3. `python scripts/build_module_map.py` — читает `graphify-out/graph.json`, пишет
   `.gigacode/context/module-map.md` (лимит размера `--max-lines 120`).

Перегенерируйте карту после заметных изменений архитектуры. Коммитить
`module-map.md` или нет — решение команды. **Фолбэк:** нет файла — гейт молча
пропускает секцию; ручная карта в `journal.md` тоже работает.

## Context7 MCP — документация библиотек (опционально)

Context7 **не** включён в `settings.json` по умолчанию. Чтобы включить, добавьте
в `.gigacode/settings.json` в блок `mcpServers`:

```json
"context7": {
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"]
}
```

Нужен Node.js 18+. API-ключ опционален (повышает rate limit): добавьте
`"--api-key", "<ключ>"` в `args` — ключи в репозиторий не коммитим. **Фолбэк:**
без Context7 анализ идёт на знаниях модели и официальной документации.

## Jira / Confluence (Atlassian MCP)

Atlassian MCP настраивает команда; шаблон его не устанавливает и не хранит
токены. Если он недоступен, анализ продолжается по коду и вводу пользователя, а
в результате явно фиксируется это ограничение. Код всегда приоритетнее Jira и
Confluence как источник текущей реализации.

## Ограничение размера субагентов

Каждый файл субагента — короче 10 000 символов. Переиспользуемые детали выносите
в `rules/` или шаблоны, а не раздувайте промпты субагентов.

## Проверка семантики хуков вашей сборки GigaCode

Имена событий и тулов в `router.config.json` соответствуют документации Qwen
Code. GigaCode — форк, поэтому перед продакшеном один раз проверьте реальные
имена: временно зарегистрируйте `python .gigacode/hooks/hook_probe.py` на нужные
события, выполните типовые действия (запрос, правка файла, git-команда) и сверьте
`hook_event_name`/`tool_name` в `.gigacode/logs/hook-probe.jsonl` с матчерами в
`router.config.json`.

## Адаптация для командного репозитория

Используйте модуль как корень проекта аналитика. Обновляйте `settings.json`
только безопасными для проекта значениями; не храните secrets, токены и
персональные пути. Если ваш форк GigaCode ожидает `.gigacode/` в другом месте,
сохраните внутреннюю структуру и измените только внешний путь модуля.
