# Observability (Sentry)

Единая точка инициализации Sentry для Atman. Управляет телеметрией через
`ATMAN_OBS_LEVEL` с четырьмя уровнями: `off`, `minimal`, `debug`, `verbose`.

## Область применения

- **В составе:** `src/atman/observability/` — `init_observability()`, сэмплинг,
  PII-скрабинг, span-хелперы (`ai_chat_span`, `memory_span`, `db_span` и др.).
- **Мост совместимости:** `src/atman/adapters/observability/sentry.py` —
  устаревший `init_sentry_from_env()` делегирует вызов к `init_observability()`.
- **Вне области:** размещение span-ов на уровне приложения (задачи P2.x),
  Sentry Alert-правила, отслеживание релизов.

## Краткая таблица

| Уровень | Трассировка | Профилирование | Spotlight |
|---------|-------------|----------------|-----------|
| `off` | нет | нет | выкл |
| `minimal` | 10 % + AI 100 % | выкл | выкл |
| `debug` | 100 % | 10 % | вкл |
| `verbose` | 100 % | 100 % | вкл |

Подробная матрица уровней, список PII-полей и инструкция по настройке —
в [`levels.md`](levels.md).

## Сканер инструментирования

`tools/check_instrumentation.py` сканирует `src/atman/{handlers,adapters,agents,engines}/`
на наличие асинхронных функций без span-хелпера. Функции, освобождённые от этого
требования, перечислены в `.sentry-instrumentation-allowlist`; обоснование —
в [`instrumentation-allowlist-rationale.md`](instrumentation-allowlist-rationale.md).
