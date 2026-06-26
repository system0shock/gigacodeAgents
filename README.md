# GigaCode

Монорепозиторий проектных флоу GigaCode для агентной разработки. Каждый флоу
самодостаточен и открывается как корень проекта для `gigacode`. Хуки превращают
обычную сессию в управляемый процесс: детерминированные гейты (git-safety,
структура спеки, линтер, сборка) **блокируют**, эвристики — только подсказывают.

## ⚡ Быстрый старт

Минимальный путь к первому запуску обеих флоу (Windows и Linux/macOS) —
**[QUICK_START.md](QUICK_START.md)**.

## Флоу

- **Разработка (dev-flow)** — в [`modules/development/`](modules/development/)
  (`.gigacode/`, `rules/`, `scripts/`, `openspec/`). Команды `/develop-feature`
  и `/fix-bug`; git-safety, quality gates, OpenSpec, артефакты задачи. В режиме
  `implement` — фиксированные стадии **intake → contract → plan → implement →
  delivery** с человеческими чекпойнтами (`confirm.py`, агенту самоодобрение
  закрыто) и **машинным вердиктом**: доставка открывается только реальным
  `pass`. За живым ходом флоу можно следить в **обсервере** (веб-панель,
  `python .gigacode/hooks/observer.py` → http://127.0.0.1:8787).
  📖 [modules/development/README.md](modules/development/README.md) ·
  руководство: [modules/development/docs/USER-GUIDE.md](modules/development/docs/USER-GUIDE.md) ·
  обзор флоу: [modules/development/docs/flow-overview.md](modules/development/docs/flow-overview.md).

- **Аналитика (reverse-analysis)** — в [`modules/analytics/`](modules/analytics/).
  Одноразовый обратный анализ одной бизнес-фичи по коду → технический слой +
  спека OpenSpec + дерево документации.
  📖 [modules/analytics/README.md](modules/analytics/README.md).

Каждый модуль открывается как корень проекта для `gigacode`. Позже рядом можно
добавить другие модули (например `modules/nt`).

## Требования

| Обязательно | Зачем |
|---|---|
| **GigaCode CLI** (`gigacode`) | хост: запускает хуки и команды |
| **Git** | гейты читают рабочее дерево; `git_guard` защищает репозиторий |
| **Python 3** (`python3` / `python` / Windows-лаунчер `py`) | роутер и все гейты написаны на Python |
| **Node.js** | среда выполнения GigaCode; запускает кросс-платформенный лаунчер хуков `node .gigacode/hooks/run-hook.cjs`, который сам находит Python на любой ОС |
| **PowerShell** (Windows) / **Bash** (Linux/macOS) | только для smoke-проверок |

Опционально (для каждого инструмента — graceful fallback): **OpenSpec CLI**
(strict-валидация спеки), **Serena** (семантический поиск кода), **Graphify**
(карта модулей), **Context7** (документация библиотек). Репозиторий не
устанавливает MCP-серверы и не хранит секреты.

## Кросс-платформенность

Хуки вызываются одной и той же командой `node .gigacode/hooks/run-hook.cjs` на
всех ОС — лаунчер резолвит `python3`/`python`/`py` и сам подставляет
UTF-8-окружение. ОС-специфичных правок `settings.json` делать не нужно; решения
гейтов отдаются в форме, которую читает рантайм GigaCode/Qwen
(`hookSpecificOutput`).

## Язык

Язык workflow по умолчанию — русский (вопросы, блокеры, артефакты). Технические
идентификаторы (пути, команды, имена веток/хуков, символы кода, raw output) не
переводятся.
