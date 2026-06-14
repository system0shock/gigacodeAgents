# GigaCode Developer Template

Этот репозиторий является проектным шаблоном GigaCode для enterprise-процессов разработки.

Язык workflow по умолчанию - русский. GigaCode задает уточняющие вопросы, объясняет блокеры и пишет Markdown-артефакты разработки на русском языке, если пользователь явно не попросил другой язык. Технические идентификаторы, такие как file paths, commands, branch names, hook names, code symbols, package names и raw command output, остаются без перевода.

> 📖 **Новым пользователям:** начните с [руководства пользователя](docs/USER-GUIDE.md) —
> быстрый старт (установка зависимостей) и понятное пошаговое описание флоу.
> Этот README остаётся справочником по настройке и адаптации.

Шаблон предоставляет две проектные команды:

- `/develop-feature`: спланировать или реализовать фичу.
- `/fix-bug`: расследовать, спланировать или исправить баг.

Обе команды используют skill `development-flow` и поддерживают два режима:

- `plan-only`: подготовить Markdown-артефакты разработки без изменения исходного кода.
- `implement`: спланировать работу, пройти git safety checks, внести scoped edits, проверить поведение и подготовить PR-ready notes.

## Требования

- GigaCode CLI
- Git
- Python 3
- PowerShell на Windows
- Bash для Linux-compatible smoke checks

## Быстрый старт

Запустите из корня репозитория:

```powershell
gigacode
```

Пример для фичи:

```text
/develop-feature plan-only payment retry with acceptance criteria: retry failed provider calls once after transient timeout
```

Пример для бага:

```text
/fix-bug plan-only card blocking timeout expected: user sees final status actual: request hangs after provider timeout
```

## Выходные артефакты

Артефакты разработки создаются как Markdown-файлы в каталоге:

```text
docs/development/<task-slug>/
```

Ожидаемые файлы:

- `journal.md` — контекст, impact map, план и ход реализации
- `verification.md` — команды проверки и доказательства
- `pr-summary.md` — сводка для ревьюера

Журнал ссылается на авторитетную OpenSpec-спецификацию в `openspec/` и не
дублирует её.

## Project Intelligence

Workflow использует project analytics и Graphify, когда они доступны.

Fallbacks:

- Если analytics отсутствует, workflow продолжает работу с кодом, тестами, локальной документацией и контекстом от пользователя.
- Если Graphify отсутствует, используется direct repository inspection и manual impact mapping.

## Enterprise Git Safety

Шаблон блокирует реализацию и git write operations на защищенных ветках, включая `main`, `master`, `develop`, `release/*`, `hotfix/*`, `production`, `staging` и `uat`. Сюда же входит push, нацеленный на защищённую ветку по refspec из feature-ветки (`git push origin main`, `git push origin HEAD:main`).

Шаблон по умолчанию блокирует destructive git operations, включая `git reset --hard`, destructive `git clean` variants, forced pushes, branch deletion, remote URL changes, direct protected-branch commits и команды, отбрасывающие правки рабочего дерева (`git checkout -f`, `git checkout -- <path>`, `git switch --discard-changes`, `git restore`).

В v1 шаблон не выполняет auto-commit и auto-push. PR readiness означает, что workflow готовит reviewer-facing notes и verification evidence для человека или CI workflow.

Все хуки проходят через единый роутер `.gigacode/hooks/router.py`:
маршрутизация описана в `.gigacode/hooks/router.config.json`, каждое решение
журналируется в `.gigacode/logs/decisions.jsonl`. Добавление нового гейта —
это новый файл в `.gigacode/hooks/gates/` плюс строка в конфиге; роутер не
редактируется. Если хуки сломаны, временный выключатель —
`"disableAllHooks": true` в `.gigacode/settings.json`.

## Smoke Checks

Windows:

```powershell
.\scripts\smoke-check.ps1
```

Linux-compatible shell:

```bash
bash scripts/smoke-check.sh
```

Smoke checks не требуют GigaCode, Graphify, MCP servers, network access или enterprise credentials.

## Адаптация под команду

Обновите `rules/git-safety.md` под protected branches и protected paths вашей команды.

Обновляйте `.gigacode/settings.json` только project-safe defaults. Не храните в репозитории secrets, tokens, personal paths или environment-specific credentials.

### Проверка семантики хуков вашей сборки GigaCode

Имена событий и тулов в `router.config.json` соответствуют документации
Qwen Code. GigaCode — форк, поэтому перед продакшен-использованием один раз
проверьте реальные имена: временно зарегистрируйте
`python .gigacode/hooks/hook_probe.py` на интересующие события в
`.gigacode/settings.json`, выполните типовые действия (запрос, правка файла,
git-команда) и сверьте `hook_event_name`/`tool_name` в
`.gigacode/logs/hook-probe.jsonl` с матчерами в `router.config.json`.

## OpenSpec-спецификации

Шаблон управляет авторитетными спецификациями через OpenSpec.

Предварительное условие (один раз на машину):

    npm install -g @fission-ai/openspec@1.4.1

Шаблон поставляет адаптированные для GigaCode навыки и команды OpenSpec в
`.gigacode/` и файл `openspec/config.yaml`. Если потребуется перегенерировать
их, запустите `openspec init --tools qwen --force` и перенесите
`.qwen/skills/openspec-*` и `.qwen/commands/opsx-*` в `.gigacode/`.

Рабочий процесс:

1. `/opsx:propose "<идея>"` — создать изменение в `openspec/changes/<id>/`.
2. Заполнить артефакты; запустить `openspec validate <id> --strict`.
3. `/opsx:apply` — реализовать, `/opsx:archive` — завершить.

Правила формата описаны в `rules/openspec.md`. Рабочие заметки по запуску
остаются в `docs/development/<task-slug>/` и ссылаются на изменение OpenSpec.

> **Примечание:** Формат файлов команд (`.toml` против `.md`) для команд
> `opsx-*` не верифицирован — поставляются оба формата. Проверьте
> совместимость с вашей сборкой GigaCode.

## Serena MCP — семантический поиск кода

Serena предоставляет семантическую навигацию по коду через протокол MCP.
Без Serena агенты работают только через `rg`. С Serena агенты находят
существующие символы и расширяют их вместо дублирования.

**Предварительные условия (один раз на машину):**

    pip install uv          # или см. https://docs.astral.sh/uv/
    uv tool install -p 3.13 serena-agent
    serena init             # инициализирует LSP-бэкенд

**Настройка per-project:**

    serena project create   # создаёт .serena/project.yml в текущей директории

Шаблон уже содержит `.serena/project.yml`. Замените `project_name` и
`ignored_paths` значениями вашего проекта.

Serena **не является обязательным условием**. Если `serena` недоступен,
агенты переключаются на поиск через `rg`, а smoke-проверки завершаются
успешно без него.

## Quality gates (Phase 4)

Шесть гейтов качества работают через hook router (`.gigacode/hooks/router.py`)
и настраиваются одним файлом `.gigacode/quality-gates.json` — языковая
специфика живёт в конфиге, не в коде гейтов.

| Гейт | Событие | Режим |
|---|---|---|
| `gate_context_inject` | SessionStart, SubagentStart(coder), UserPromptSubmit | инъекция правил и активных OpenSpec changes |
| `gate_spec_structure` | PreToolUse, PostToolUse, Stop | ask: запись в `openspec/specs/` (легитимна в `/opsx:sync`/`archive`); блок: провал `openspec validate --strict` |
| `gate_lint` | PostToolUse (изменённый файл) | блок при ненулевом exit code линтера |
| `gate_build` | Stop (момент готовности PR) | блок при провале сборки |
| `gate_clean_code` | PostToolUse | advisory: размер файла/функции, TODO/FIXME, Thread.sleep в тестах |
| `gate_existing_code` | PreToolUse (новые файлы) | advisory: дубликаты символов и Kafka-топиков (rg → git grep) |

Пример настройки для Kotlin/Java + Gradle:

```json
{
  "lint": [
    { "command": "gradlew.bat ktlintCheck", "applies_to": ["**/*.kt", "**/*.kts"], "timeout_seconds": 300 },
    { "command": "gradlew.bat checkstyleMain", "applies_to": ["**/*.java"], "timeout_seconds": 300 }
  ],
  "build": { "command": "gradlew.bat compileKotlin compileTestKotlin", "timeout_seconds": 600 },
  "test": { "command": "gradlew.bat test" },
  "clean_code": { "max_file_lines": 400, "max_function_lines": 60, "placeholder_markers": ["TODO", "FIXME", "XXX"] }
}
```

Пустая `command` = гейт пропускается без записи в журнал (silent allow);
смоук-чеки и работа в репозитории без настроенных команд не блокируются.
`test.command` использует агент `verifier` (гейты тесты не гоняют).
На Linux/macOS указывайте `./gradlew ...`.

## Карта модулей (Graphify) и Context7

### Graphify → module-map

`gate_context_inject` на старте сессии инжектит `.gigacode/context/module-map.md` —
компактную карту модулей репозитория. Карта генерируется из графа знаний Graphify:

1. Установи graphify: `pip install graphifyy`.
2. Построй граф репозитория: `/graphify .` (скилл; повторный прогон — `/graphify . --update`).
3. Сгенерируй карту: `python scripts/build_module_map.py`
   (читает `graphify-out/graph.json`, пишет `.gigacode/context/module-map.md`,
   лимит размера `--max-lines 120`).

Перегенерируй карту после заметных изменений архитектуры (новые модули,
новые Kafka-потоки). Коммитить `module-map.md` или нет — решение команды.

**Фолбэк:** если Graphify не используется, файла просто нет — гейт молча
пропускает секцию. Ручная карта в том же файле тоже работает.

### Context7

Context7 объявлен в `settings.json` (`mcpServers.context7`) и поднимается через
`npx -y @upstash/context7-mcp` — нужен Node.js 18+. Даёт свежую документацию
библиотек (Spring Kafka, kotlinx.coroutines, JUnit 5) при написании нового кода.

API-ключ опционален (повышает rate limit): добавь `--api-key <ключ>` в `args`.
Ключи в шаблон не коммитим.

**Фолбэк:** без Node/ключа сервер просто не стартует — flow продолжает работать
на знаниях модели; проверяй API по официальным докам и фиксируй это в
`verification.md`.
