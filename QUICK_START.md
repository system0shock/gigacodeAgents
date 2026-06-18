# QUICK_START — GigaCode

Самый короткий путь к первому запуску. Подробности — в
[docs/USER-GUIDE.md](docs/USER-GUIDE.md) (разработка) и
[modules/analytics/README.md](modules/analytics/README.md) (аналитика).

## 1. Проверьте обязательное

```bash
gigacode --version    # GigaCode CLI (хост)
git --version
node --version        # среда GigaCode + лаунчер хуков
python --version      # или python3 / py  (роутер и гейты на Python)
```

Хуки вызываются через `node .gigacode/hooks/run-hook.cjs`, который сам находит
Python на любой ОС — ОС-специфичных правок не нужно.

Рекомендуется (strict-валидация спеки; без неё гейт мягко пропускает проверку):

```bash
npm install -g @fission-ai/openspec@1.4.1
```

## 2. Разработка (dev-flow) — в корне репозитория

Windows:

```powershell
.\scripts\smoke-check.ps1      # должно закончиться "Smoke check passed"
gigacode
```

Linux/macOS:

```bash
bash scripts/smoke-check.sh
gigacode
```

Первая задача в сессии (режим `plan-only` — план без правок кода):

```text
/develop-feature plan-only payment retry; критерии приёмки: повторять упавший вызов один раз после транзиентного таймаута
```

Багфикс: `/fix-bug plan-only <симптом; ожидаемое vs фактическое; шаги>`.
Когда план устроит — повторите в режиме `implement`.

## 3. Аналитика (reverse-analysis) — в `modules/analytics/`

Windows:

```powershell
cd modules\analytics
.\scripts\smoke-check.ps1
gigacode
```

Linux/macOS:

```bash
cd modules/analytics
bash scripts/smoke-check.sh
gigacode
```

Запуск анализа одной фичи (только по коду, без Jira/Confluence):

```text
/reverse-analysis feature "Card Blocking" code-only, no Jira, no Confluence
```

## 4. Если что-то блокирует

Гейт всегда печатает причину и что сделать. Причины детерминированы и чинятся
самим агентом: дописать спеку, заполнить артефакт задачи, поправить сборку.
Деструктивный git (`reset --hard`, force-push, удаление `.git`/`.gigacode`)
заблокирован специально — это ручная человеческая операция вне агента.

Аварийный выключатель (правит человек — для агента файл защищён):
`"disableAllHooks": true` в `.gigacode/settings.json` (для аналитики — в
`modules/analytics/.gigacode/settings.json`). Это последнее средство: потом
почините причину и верните хуки.

Журнал всех решений гейтов — `.gigacode/logs/decisions.jsonl`.

## Дальше

- Разработка целиком: [docs/USER-GUIDE.md](docs/USER-GUIDE.md) · [docs/flow-overview.md](docs/flow-overview.md)
- Аналитика целиком: [modules/analytics/README.md](modules/analytics/README.md) · [modules/analytics/docs/flow-overview.md](modules/analytics/docs/flow-overview.md)
- Опциональные инструменты (Serena, Graphify, Context7) и их установка — в гайдах выше; у каждого есть fallback.
