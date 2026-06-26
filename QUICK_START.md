# QUICK_START — GigaCode

Самый короткий путь к первому запуску. Подробности — в
[modules/development/docs/USER-GUIDE.md](modules/development/docs/USER-GUIDE.md)
(разработка) и [modules/analytics/README.md](modules/analytics/README.md)
(аналитика).

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

## 2. Разработка (dev-flow) — в `modules/development/`

Windows:

```powershell
cd modules\development
.\scripts\smoke-check.ps1      # должно закончиться "Smoke check passed"
gigacode
```

Linux/macOS:

```bash
cd modules/development
bash scripts/smoke-check.sh
gigacode
```

Первая задача в сессии (режим `plan-only` — план без правок кода):

```text
/develop-feature plan-only payment retry; критерии приёмки: повторять упавший вызов один раз после транзиентного таймаута
```

Багфикс: `/fix-bug plan-only <симптом; ожидаемое vs фактическое; шаги>`.
Когда план устроит — повторите в режиме `implement`.

### Стадии и человеческие чекпойнты

В режиме `implement` флоу проходит фиксированные стадии, и агент **не может**
перепрыгнуть стоп сам — между стадиями подтверждение даёт человек (агенту это
запрещено: `git_guard` блокирует любую его попытку запустить `confirm.py`).

| Стадия | Артефакт | Чем открывается следующая |
|---|---|---|
| **intake** | `docs/development/<slug>/intake.json` | человек: `confirm.py intake <slug>` |
| **contract** (заморозка scope) | `docs/development/<slug>/contract.json` | человек: `confirm.py contract <slug>` |
| **plan** | `openspec/changes/<slug>/{proposal,design,tasks}.md` | — (scope уже заморожен) |
| **implement + verify** | код в рамках `scope_globs` + `verification.md` | **машина**: гейт сам пишет `verdict.json` по реальной сборке/тестам |
| **delivery** | `docs/development/<slug>/pr-summary.md` | открывается только при `verdict.json = pass` |

Подтверждение стадии (выполняет человек во втором терминале, `slug` — имя задачи
из `docs/development/`):

```bash
python .gigacode/hooks/confirm.py intake <slug>      # после проверки intake.json
python .gigacode/hooks/confirm.py contract <slug>    # после проверки замороженного scope
```

Ключевая гарантия: `verdict.json` — машинный (агент его не пишет), а доставка
(`pr-summary.md`) открывается только реальным `pass`. Поэтому «агент сказал
готово» ≠ «готово» — проходит только то, что собралось/прошло проверку.

## 3. Обсервер — наблюдение за флоу (опционально)

Пока агент работает в одном терминале, во **втором** запустите наблюдатель —
живую веб-картину флоу (только чтение, ничего не пишет):

```bash
cd modules/development
python .gigacode/hooks/observer.py        # затем откройте http://127.0.0.1:8787
# python .gigacode/hooks/observer.py --port 9000 --slug card   # другой порт / одна задача
```

Страница (одна, без внешних ассетов) обновляется в реальном времени по SSE и
показывает: текущую стадию, бюджет стопов, заявленный scope, вердикт и поток
решений гейтов. Это «приборная панель» процесса — удобно вести демо и видеть,
где флоу остановился и почему.

Без браузера тот же срез даёт CLI:

```bash
python .gigacode/hooks/projection.py            # снимок один раз
python .gigacode/hooks/projection.py --follow    # режим tail
python .gigacode/hooks/projection.py --slug card # только одна задача
```

Обсервер и `projection` — ручные инструменты, не хуки: они не зарегистрированы
в `settings.json` и не влияют на решения гейтов.

## 4. Аналитика (reverse-analysis) — в `modules/analytics/`

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

## 5. Если что-то блокирует

Гейт всегда печатает причину и что сделать. Причины детерминированы и чинятся
самим агентом: дописать спеку, заполнить артефакт задачи, поправить сборку.
Деструктивный git (`reset --hard`, force-push, удаление `.git`/`.gigacode`)
заблокирован специально — это ручная человеческая операция вне агента.

Аварийный выключатель (правит человек — для агента файл защищён):
`"disableAllHooks": true` в `<модуль>/.gigacode/settings.json`
(`modules/development/...` для разработки, `modules/analytics/...` для аналитики).
Это последнее средство: потом почините причину и верните хуки.

Журнал всех решений гейтов — `<модуль>/.gigacode/logs/decisions.jsonl`.

> **Заметка про smoke на защищённой ветке.** Проверка `guard_allow::git commit`
> ожидает обычную рабочую ветку. Если запустить smoke, находясь на `master`/`main`
> (их `git_guard` защищает), эта строка покажет block — это корректное поведение
> гейта, а не поломка. Прогоняйте smoke на feature/bugfix-ветке.

## 6. Защита самого контрол-плейна (опционально, рекомендуется)

После развёртывания и после любой намеренной правки `.gigacode/**` обновите
базлайн целостности — тогда Stop-гейт `gate_integrity` ловит подмену
enforcement-кода/конфига (man-in-the-middle через любой канал, включая MCP):

```bash
python .gigacode/hooks/integrity.py generate    # записать .gigacode/integrity.manifest
python .gigacode/hooks/integrity.py verify       # exit 0 = без изменений
```

Пока манифест не сгенерирован, гейт работает в режиме fail-open (предупреждает,
но пропускает) — то есть свежий деплой не падает, но и не защищён, пока вы не
создадите базлайн. `integrity.py`, как и `confirm.py`, — человеческий
инструмент: агенту он закрыт (`git_guard` блокирует команды, называющие
`.gigacode`).

## Дальше

- Разработка целиком: [modules/development/README.md](modules/development/README.md) · [modules/development/docs/USER-GUIDE.md](modules/development/docs/USER-GUIDE.md) · [modules/development/docs/flow-overview.md](modules/development/docs/flow-overview.md)
- Аналитика целиком: [modules/analytics/README.md](modules/analytics/README.md) · [modules/analytics/docs/flow-overview.md](modules/analytics/docs/flow-overview.md)
- Опциональные инструменты (Serena, Graphify, Context7) и их установка — в гайдах выше; у каждого есть fallback.
