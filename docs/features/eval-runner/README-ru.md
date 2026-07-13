# E1 Evaluation Runner Framework

## Назначение

E1 добавляет минимальный, но рабочий слой оркестрации бенчмарков в `src/atman/eval/`, сохраняя изоляцию от production runtime.

Ключевые цели:

- запуск бенчмарков через module-only CLI (`python -m atman.eval.benchmark_runner`)
- простой реестр бенчмарков (`registry.py` + decorator, без entry points)
- использование существующей eval-схемы БД (`eval.benchmark_runs`, `eval.run_items`) и хранение дополнительного контекста в `metadata` JSONB
- воспроизводимый локальный результат (JSONL reporter + demo script)

## Карта модулей

- `benchmark_runner.py` - Click CLI с командами `list` / `run`
- `runner_core.py` - lifecycle запуска и детерминированная app-level идемпотентность при наличии `git_sha`
- `run_context.py` - типизированный контекст запуска + `to_db_metadata()`
- `registry.py` - register/get/list бенчмарков
- `reporters/base.py` - протокол reporter'а
- `reporters/db_reporter.py` - запись в `eval.benchmark_runs` и `eval.run_items`
- `reporters/jsonl_reporter.py` - JSONL sink для локальных артефактов
- `seed_manager.py` - разрешение seed и применение глобального seed
- `hardware.py` - сбор CPU/memory/GPU с graceful fallback при отсутствии `psutil`/`pynvml` или NVML
- `benchmarks/noop.py` - smoke-бенчмарк для demo и CLI-проверок

## Быстрая карта eval-инструментов

E1 runner — это registry-based путь для бенчмарков. Некоторые eval-инструменты остаются standalone-скриптами, потому что требуют optional model downloads, внешних API или фиксированного исследовательского датасета.

| Вопрос | Инструмент | Источник меток / вывод |
| --- | --- | --- |
| Правильно ли собран eval runner? | `python -m atman.eval.benchmark_runner list` / `run noop` | Встроенный `noop` benchmark через `registry.py` |
| Достаточно ли хорош production GLiNER+MiniLM сейчас? | `python3 scripts/eval/eval_linguistic_quality.py --adapter gliner` | Runtime `EntityType` / метки linguistic adapter |
| Нужно ли дообучать GLiNER2 для русского NER-core? | `python -m atman.eval.gliner2.baseline --model fastino/gliner2-multi-v1` | T1-схема `atman-ner-core` на 13 меток, результат в `eval/results/gliner2_baseline_ru.json` |
| Как сгенерирован synthetic RU NER corpus? | `PIONEER_API_KEY=... python3 scripts/eval/generate_synthetic_ru.py` | GLiNER training JSONL в `eval/data/atman_ner_ru_synth.jsonl` |

GLiNER2 baseline намеренно **не** зарегистрирован в `atman.eval.registry`: это фиксированный zero-shot research runner, который при первом запуске скачивает HuggingFace-модели и пишет merged JSON artifact.

## Использование CLI

Список бенчмарков:

```bash
python -m atman.eval.benchmark_runner list
```

Запуск бенчмарка:

```bash
python -m atman.eval.benchmark_runner run noop --git-sha "$(git rev-parse --short HEAD)" --jsonl-output /tmp/atman-eval.jsonl
```

Опциональная запись в БД (существующая eval-схема):

```bash
python -m atman.eval.benchmark_runner run noop --db-dsn "$POSTGRES_URL"
```

Запуск standalone GLiNER2 baseline (нужен extra `eval`; первый запуск скачивает модели):

```bash
python -m atman.eval.gliner2.baseline --model fastino/gliner2-multi-v1
python -m atman.eval.gliner2.baseline --model urchade/gliner_multi-v2.1
```

Текущий committed result использует 130 gold-примеров на русском из `src/atman/eval/gliner2/dataset.py` и показывает, что обе baseline-модели попадают в диапазон `F1 0.4-0.7`, то есть fine-tuning нужен.

## Алиасы Makefile

- `make eval-list`
- `make eval-run`
- `make demo-eval-runner`
- `make demo-eval-runner-fast`

Для GLiNER2 baseline нет Makefile alias; используйте module command выше, чтобы дорогой выбор модели оставался явным.

## Synthetic RU NER data

`scripts/eval/generate_synthetic_ru.py` регенерирует committed corpus `eval/data/atman_ner_ru_synth.jsonl`.

Ограничения:

- нужен `PIONEER_API_KEY` и сетевой доступ к Pioneer API
- формат строк GLiNER training: `{"tokenized_text": [...], "ner": [[start, end, "label"], ...]}`
- индексы span — 0-based inclusive token spans
- скрипт валидирует набор меток и границы span перед успешной записью
- не входит в `make check` и не является частью E1 registry path

## Демонстрация

`src/demo_eval_runner.py` показывает:

1. обнаружение бенчмарков через registry
2. один запуск noop с JSONL-репортером
3. повторный запуск с тем же `git_sha`, возвращающий идемпотентный `skipped` outcome

Запуск:

```bash
make demo-eval-runner
```

## Примечания по безопасности/изоляции

- для eval runner не добавляются production entry points
- `atman.eval` остается optional и защищен dependency check
- `make lint-boundary` и `make verify-prod-isolation` остаются обязательными gate-проверками
