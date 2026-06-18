# GigaCode

Монорепозиторий проектных флоу GigaCode. Каждый флоу самодостаточен и
открывается как корень проекта для `gigacode`.

## Флоу

- **Разработка (dev-flow)** — в корне репозитория (`.gigacode/`, `rules/`,
  `scripts/`). Команды `/develop-feature` и `/fix-bug`, git safety, quality
  gates, OpenSpec.
  📖 Старт: [docs/USER-GUIDE.md](docs/USER-GUIDE.md) ·
  обзор флоу: [docs/flow-overview.md](docs/flow-overview.md).

- **Аналитика (reverse-analysis)** — в [`modules/analytics/`](modules/analytics/).
  Контур reverse-analysis одной бизнес-фичи за раз.
  📖 [modules/analytics/README.md](modules/analytics/README.md).

Позже рядом можно добавить другие модули, например `modules/development` и
`modules/nt`.

## Язык

Язык workflow по умолчанию — русский. Технические идентификаторы (пути,
команды, имена веток и хуков, символы кода, raw output) не переводятся.
