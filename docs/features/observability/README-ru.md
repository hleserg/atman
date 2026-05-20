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

## Span-хелперы

Все хелперы находятся в `atman.observability.spans` и деградируют gracefully
когда Sentry не инициализирован (SDK возвращает no-op span).

| Хелпер | Op name | Когда использовать |
|--------|---------|-------------------|
| `ai_chat_span(provider, model)` | `gen_ai.chat` | LLM чат-завершение |
| `ai_embeddings_span(provider, model)` | `gen_ai.embeddings` | батч эмбеддингов |
| `ai_rerank_span(provider, model, docs, top_n)` | `gen_ai.rerank` | реранкинг |
| `memory_span(action, namespace)` | `memory.<action>` | recall / store / reflect |
| `db_span(system, operation, collection)` | `db` | запросы postgres / qdrant |
| `cron_span(monitor_slug)` | `cron` | тело планового задания |
| `pipeline_span(op, description)` | custom | любой другой этап пайплайна |

## Сканер инструментирования

`tools/check_instrumentation.py` сканирует `src/atman/{handlers,adapters,agents,engines}/`
на наличие публичных функций верхнего уровня без span-хелпера. CI-задача
(`.github/workflows/sentry-instrumentation.yml`) работает в режиме **жёсткой блокировки** —
отсутствие span-а является ошибкой сборки, а не предупреждением.

Функции, освобождённые от этого требования, перечислены в
`.sentry-instrumentation-allowlist`; обоснование —
в [`instrumentation-allowlist-rationale.md`](instrumentation-allowlist-rationale.md).

## Поток PII-данных

| Данные | Куда отправляется | Защита |
|--------|------------------|--------|
| UUID агента | `scope.set_user({"id": ...})` | Только UUID, без имени/почты |
| Ключи событий `slog()` (fact_id, agent_id, source) | Breadcrumbs | Неличные метаданные |
| Содержимое факта (первые 120 символов) | Поле breadcrumb `content` | Скрабинг по ключу `fact_content` |
| Имя модели LLM | Атрибут span-а | Не является личными данными |
| Stack traces исключений | Error events | `send_default_pii=False`, `EventScrubber` |

В Sentry никогда не попадают: raw prompt-ы, ответы LLM, эмбеддинги,
полный текст фактов, результаты рефлексии, identity-payload-ы.
