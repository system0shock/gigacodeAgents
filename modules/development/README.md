# Модуль разработки GigaCode (dev-flow)

Проектная конфигурация GigaCode для разработки: агент сначала пишет спецификацию
(OpenSpec), ищет существующий код перед созданием нового, проходит проверки
качества и git-безопасности и **не может завершить ход**, пока работа не оформлена
и не доказана. Блокируют только детерминированные гейты (git, валидатор спеки,
линтер, сборка); эвристики лишь подсказывают.

Откройте этот каталог как корень проекта для `gigacode`.

📖 **Подробное руководство** (установка, быстрый старт, как устроен флоу,
настройка под стек, что делать при блокировке): [`docs/USER-GUIDE.md`](docs/USER-GUIDE.md).
📖 **Обзор флоу** (запуск, артефакты, хуки, MCP, покрытие стека): [`docs/flow-overview.md`](docs/flow-overview.md).
🚀 **Быстрый старт** обеих флоу (Windows/Linux): [`../../QUICK_START.md`](../../QUICK_START.md) ·
монорепозиторий: [`../../README.md`](../../README.md).

## Состав модуля

- `.gigacode/settings.json` — настройки проекта, разрешения, hooks, mcpServers.
- `.gigacode/skills/` — скилл `development-flow` (+ `openspec-propose`).
- `.gigacode/commands/` — slash-команды `/develop-feature`, `/fix-bug`.
- `.gigacode/agents/` — субагенты (`coder`, `verifier` и др.).
- `.gigacode/hooks/` — единый роутер `router.py`, гейты в `gates/`, кросс-платформенный
  лаунчер `run-hook.cjs`.
- `openspec/` — `config.yaml` и `specs/` (спека как текущая истина).
- `rules/` — git-safety, language-policy, development-flow, openspec, code-style, testing.
- `scripts/` — билдер карты модулей + smoke-проверки.
- `docs/` — `USER-GUIDE.md`, `flow-overview.md`, шаблоны и артефакты задач (`development/<slug>/`).

## Требования

- **GigaCode CLI** (`gigacode`) — хост.
- **Git**; **Python 3** (`python3` / `python` / Windows `py`) — роутер и гейты;
  **Node.js** — среда GigaCode и лаунчер хуков (`node .gigacode/hooks/run-hook.cjs`
  сам находит Python на любой ОС).
- **PowerShell** (Windows) / **Bash** (Linux/macOS) — для smoke-проверок.
- Опционально (для каждого — fallback): OpenSpec CLI (strict-валидация спеки),
  Serena (семантический поиск), Graphify (карта модулей), Context7 (доки библиотек).

## Быстрый старт

Windows:

```powershell
cd modules\development
.\scripts\smoke-check.ps1      # "Smoke check passed"
gigacode
```

Linux/macOS:

```bash
cd modules/development
bash scripts/smoke-check.sh
gigacode
```

Затем в GigaCode (режим `plan-only` — план без правок кода):

```text
/develop-feature plan-only payment retry; критерии приёмки: повторять упавший вызов один раз после транзиентного таймаута
```

Багфикс — `/fix-bug plan-only <симптом; ожидаемое vs фактическое; шаги>`. Полный
разбор флоу, гейтов и настройки под стек — в [`docs/USER-GUIDE.md`](docs/USER-GUIDE.md).

## Адаптация для командного репозитория

Используйте модуль как корень проекта. В `settings.json` храните только
безопасные для проекта значения — без secrets, токенов и персональных путей.
Защищённые ветки/пути — в `rules/git-safety.md`; команды линта/сборки/тестов — в
`.gigacode/quality-gates.json` (см. раздел «Настройка под ваш стек» в USER-GUIDE).
Если ваш форк GigaCode ожидает `.gigacode/` в другом месте, сохраните внутреннюю
структуру модуля и измените только внешний путь.
