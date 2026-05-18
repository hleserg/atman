# Live E2E Runbook — gemma4 (user agent) ↔ Atman session/reflection

> Living deployment log. Если работа прерывается — следующий агент/человек продолжает с первого чекбокса, у которого ещё стоит `[ ]`.
> Branch: `feat/live-e2e-gemma4-runtime`
> Дата старта: 2026-05-17
> Полная стратегия — в `/home/serg/.claude/plans/compiled-finding-oasis.md` (план Claude). Дубликат-выжимка ниже.

## Контракт (что хотим получить)

- Один LLM endpoint: `http://localhost:8081/v1`, модель `gemma4`. Обслуживает и pydantic-ai user-agent, и Atman reflection.
- **Ollama выпиливается** — все ML через native SDK (FlagEmbedding, transformers, gliner) либо llama-server.
- Embeddings: `BAAI/bge-m3` через FlagEmbedding (CPU, lazy).
- Reranker: `BAAI/bge-reranker-v2-m3` через FlagEmbedding (CPU, lazy).
- Linguistic: GLiNER + MiniLMv2-mnli-xnli + mREBEL (HF transformers, CPU, lazy).
- Postgres: миграции 0001..0018 → новый `scripts/run_migrations.py` с трекингом в `public.schema_migrations`.
- Финал: (a) scripted `e2e/live_scenario.py` на gemma4; (b) интерактивный REPL `e2e/live_chat.py` с **всеми 6** тулзами агента.
- Параллельно обновляем `deploy/atman-setup.sh` / `deploy/atman-deploy/deploy/setup.sh` / `deploy/atman-deploy/deploy/config.env` / `.env` / `atman-start.sh` / `atman_agent_cli/RUNBOOK.md` под новый контракт.

## Phase 0 — Baseline (read-only)  ✅

- [x] `git switch -c feat/live-e2e-gemma4-runtime` — на ветке.
- [x] `docker ps` — `atman-postgres` healthy (:5432); `atman-qdrant` unhealthy (нам не нужен); `open-webui` идёт фоном.
- [x] `curl :8081/v1/models` — llama-server жив, отдаёт `gemma4` + `atman-deepseek-r1-14b`.
- [x] Ollama — не запущена (`:11434` пустой ответ); соответствует решению выпилить.
- [x] `.venv` пересоздан под `serg` (был root-symlink).
- [x] `pip install -e ".[dev,linguistic,e2e]"` отработал: torch 2.12 (+cu130), transformers 5.1.0, FlagEmbedding 1.4.0, gliner 0.2.26, pydantic-ai-slim 1.97.0, psycopg 3.3.4.

## Phase 1 — User-agent alive БЕЗ Atman  ✅

- [x] Env: `AGENT_LLM_BASE_URL=http://localhost:8081/v1`, `AGENT_LLM_MODEL=gemma4`, `AGENT_LLM_API_KEY=dummy` зафиксированы в `.env`.
- [x] One-liner `create_agent().run_sync('Скажи привет одним словом.')` → **«Привет!»** Подтверждено.
- [x] **SYNC:** `atman_agent_cli/RUNBOOK.md` обновлён — раздел "Concrete example — gemma4 on :8081" с командой `llama-server -m gemma4.gguf --port 8081 --jinja`.

## Phase 2.1 — Smoke + cold-start для 5 native CPU моделей  ⏳

- [x] `scripts/measure_native_models_cold_start.py` — per-model try/except, `--only` повторяемый, force CPU через `CUDA_VISIBLE_DEVICES=""`.

| Модель | Статус | setup | first (cold+infer) | second (warm) | ΔRSS | Комментарий |
|---|---|---|---|---|---|---|
| `bge-m3` | PASS | 0.14 s | **224.47 s** | 0.064 s | 2498 MB | ~220 s — download 2.3 GB с HF |
| `bge-reranker` | PASS (после фикса signature) | 2.54 s | 2.74 s | 0.003 s | 1212 MB | HF кэш частично уже тёплый после bge-m3 (общие токенайзеры). Warm — 3 мс. |
| `gliner` | PASS | 0.11 s | 164.51 s | 0.046 s | 1584 MB | ~1 GB download |
| `minilm` | PASS | 0.00 s | 21.75 s | 0.008 s | 117 MB | HF кэш был тёплый (модель уже скачана gliner-ом) — это load+infer без download |
| `mrebel` | PASS (после фикса DetectedEntity) | 2.34 s | 1.06 s | 0.249 s | 805 MB | Cache warm (download был на предыдущем FAIL'е). Warm — 249 мс. |

- [x] **Решение по warmup**: warm inference 8–64 мс — идеально. Cold-with-download ~3–4 мин блокирует первый ход REPL. Pre-warm рекомендуется.
      **TODO** (отдельный PR): `scripts/warmup_native_models.py` (тот же код без замеров) + Make-target `make warmup-models`. Опциональный шаг в `deploy/atman-setup.sh` step 5.

## Phase 2.2 — Postgres миграции 0001..0018  ✅

- [x] `scripts/run_migrations.py` написан (psycopg, `schema_migrations(version TEXT PK, applied_at, checksum)`, drift-detection, `--dry-run`, `--status`).
- [x] `scripts/bootstrap_db.sql` извлечён из inline-heredoc + фикс `\$\$` бага + минимизирован (extensions + agents + sessions).
- [x] Все 20 версий накатились (`_bootstrap` + 0001..0018), `schema_migrations` = 20 строк.
- [x] `atman_app` роль создана, пароль из `.env` применён (через `_maybe_alter_atman_app_password` после фикса `%L`-бага).
- [x] Логин `atman_app` подтверждён: `psql -U atman_app -d atman -c 'SELECT current_user'` → `atman_app`.
- [x] **SYNC:** `deploy/atman-setup.sh` step 7 — inline-DDL heredoc заменён на вызов `.venv/bin/python scripts/run_migrations.py`. Файл уменьшился с 934 → ~530 строк.

## Phase 2.3 — `.env` + deploy-скрипты  ⏳

- [x] `.env` обновлён: Ollama закомментирована, добавлены `ATMAN_LLM_*`, `AGENT_LLM_*`, `LLM_MODEL=gemma4`, `EMBEDDING_BACKEND=flag`, `EMBEDDING_FLAG_MODEL=BAAI/bge-m3`.
- [x] **SYNC:** `deploy/atman-setup.sh` — большая переработка: банер обновлён, step 4-5 (Ollama → llama-server check + native models lazy note), step 7 (heredoc → run_migrations.py), step 8 (Qdrant → opt-in `ATMAN_USE_QDRANT=1`), step 9 (docker-compose без qdrant сервиса), step 10 (extras → `.[dev,linguistic,e2e]` без qdrant-client/asyncpg/sqlalchemy/alembic), smoke-test и финальное summary переписаны под новый контракт. Bash syntax OK.
- [x] **SYNC:** `atman-start.sh` (root) — `ollama serve` убран; теперь запускает только Postgres (Qdrant если `ATMAN_USE_QDRANT=1`) и curl-чек LLM endpoint.
- [x] **SYNC:** `atman_agent_cli/RUNBOOK.md` — добавлен раздел "Concrete example — gemma4 on :8081".
- [x] **SYNC:** `deploy/atman-deploy/deploy/config.env` — Ollama-блок задепрекейчен и закомментирован; добавлены `ATMAN_LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_BACKEND=flag`, `EMBEDDING_FLAG_MODEL=BAAI/bge-m3`, `ATMAN_USE_QDRANT=0`.
- [x] **SYNC:** `deploy/atman-deploy/deploy/setup.sh` — добавлен заголовочный deprecation-warning. Полный рефактор оставлен отдельному PR (этот скрипт — упакован в `atman-deploy.zip`, не используется напрямую при разработке).
- [ ] **SYNC:** `deploy/УСТАНОВКА.md` — TODO (документация по установке, отдельный PR).
- [x] Smoke `build_deps()` → `OK True`, guardian инжектирован, state_store=FileStateStore (контракт текущего кода).

## Phase 3 — Scripted scenario (smoke)  ✅

- [x] `e2e/live_scenario.py` адаптирован: убран `OLLAMA_BASE_URL` setdefault; модель — `OpenAIChatModel(model_name=AGENT_LLM_MODEL, provider=OpenAIProvider(base_url=AGENT_LLM_BASE_URL))`; env-driven через `.env`.
- [x] Прогон: 3 сессии завершились без exception. **Сессия 1**: agent вызвал `record_key_moment`, eigenstate (valence=0.5, intensity=0.6, depth=meaningful), narrative recent layer обогатился. **Сессия 2**: agent отказался писать дезинформацию (value alignment работает). **Сессия 3**: `close_reason=timeout_sleep`. Итог: 3 SessionExperience, 3 KM (1 живой + 2 fallback).
- [ ] Postgres-state не проверяем — текущий `build_deps` использует FileStateStore. Миграции созданы "на склад".

## Phase 4 — Interactive REPL  ✅

- [x] `e2e/live_chat.py` написан (~210 строк): build_deps + pydantic-ai Agent с **всеми 6** тулзами (`record_key_moment`, `log_experience`, `restart_session`, `wait_session`, `resolve_pending_review`, `request_reflection`), system_prompt через `build_instructions(...)`.
- [x] Smoke: `printf "/quit\n" | python e2e/live_chat.py` → банер, открыл сессию, принял stdin, force_finish (no key moments) → корректно вышел.
- [x] HLE-33 AmbientMemoryService автоматически инжектируется в `deps.ambient_memory` через factory.
- [ ] Полный interactive прогон с реальными репликами и вызовами тулзов — оставлено пользователю (нужен живой stdin).

## Verification (после Phase 4)  ✅

- [x] `SELECT version FROM schema_migrations ORDER BY version;` → **20 строк** (`_bootstrap` + 19 миграций, две пары 0015/0018 в правильном лексикографическом порядке).
- [x] `\dt public.*` → `agents`, `facts`, `fact_relations`, `maintenance_jobs`, `schema_migrations`, `skills`, `skill_invocations`.
- [x] `pytest tests/test_inline_validation_callbacks.py -v` → **19 passed**.
- [x] `pytest tests/test_ambient_memory_service.py -v` → **14 passed** (HLE-33 после merge).
- [x] live_scenario.py: 3 сессии × gemma4 → 3 SessionExperience, 3 KM, narrative и eigenstate накопились.
- [x] live_chat.py: REPL открыл сессию и корректно завершил по `/quit`.
- [ ] agent_N схемы — будут созданы при первом `AgentsRegistry.create()` (не сейчас, т.к. live_scenario использует FileStateStore, а не PostgresStateStore).
- [ ] validation_findings — текущий прогон через `InMemoryMemoryGuardian`, пишет в RAM, не в Postgres. Для PostgresMemoryGuardian нужна отдельная реализация (отдельный PR).

## Принятые решения (decisions log)

| Дата | Решение | Зачем |
|---|---|---|
| 2026-05-17 | Один LLM (gemma4 :8081) для user-agent и reflection. Atman сам без LLM. | Архитектурный принцип проекта; см. memory `one-llm-principle`. |
| 2026-05-17 | Ollama выпиливается полностью. | Замена на native SDK + llama-server упрощает деплой; см. memory `ollama-deprecated`. |
| 2026-05-17 | HF small models — lazy с замером, pre-warmup только если > 30 с warm. | CPU инференс терпим; не оптимизируем заранее. |
| 2026-05-17 | `scripts/run_migrations.py` (Python + schema_migrations таблица) вместо Alembic / bash. | Идемпотентность, drift-детект, без зависимости от Alembic. |
| 2026-05-17 | Адаптируем `e2e/live_scenario.py` in-place, новый `e2e/live_chat.py` рядом. | Один существующий скрипт переводим под новый контракт, второй — interactive фронтенд. |

## Косяки в имплементации Atman (находим по ходу)

| # | Где | Косяк | Предложение |
|---|---|---|---|
| A | `src/atman/core/services/inline_validator.py:13-22` | HLE-32: `check_fact` / `check_entity` объявлены, но не подключены к write-path. Только `check_key_moment` живой (из `SessionManager.finish_session`). | Дописать call-sites в `PostgresFactualMemory.create_fact()` и `EntityRegistry.create_entity()` (или эквивалентах). Это отдельный PR; для текущего прогона документируем gap. |
| B | `src/atman/adapters/agent/factory.py:170-185` | `InMemoryMemoryGuardian` инжектится в `build_deps` без `entity_registry` / `factual_memory`. `scan_orphan_entities`, `scan_merge_candidates`, `scan_embedding_gaps` **silently** возвращают `[]`. | В `build_deps` принимать optional эти зависимости; если переданы — прокидывать в guardian. Иначе хотя бы логировать warning, чтобы пользователь `cli_maintenance` не получал ложный «нет проблем». |
| C | `src/atman/core/services/session_manager.py:1221` | Inline guardian вызывается только при `session_result.identity_id is not None`. Сессии без identity_id молча пропускают валидацию. | Перевернуть условие: если identity_id отсутствует — логировать warning и/или передавать в guardian `agent_id` напрямую (он есть на уровне SessionManager). Inline validation не должна молча выключаться. |
| D | `migrations/versions/0015_*.sql` и `0018_*.sql` | Две пары файлов с одинаковым префиксом. Lexicographic порядок «случайно» правильный — нет enforcement. | `run_migrations.py` warning'ает при коллизии префикса. Долгосрочно — CI-чек на уникальность префиксов. |
| E | `deploy/atman-setup.sh` step 7 (lines ~365-770) | Inline-heredoc на 412 строк — **второй source-of-truth** для схемы рядом с `migrations/versions/`. Drift неизбежен; уже видно отличия (например в inline `agents` без `description`, а миграции ожидают свежее состояние). | Извлечь в `scripts/bootstrap_db.sql`; setup.sh вызывает `python scripts/run_migrations.py`. |
| F | `src/atman/adapters/memory/ollama_embedding.py` | Адаптер Ollama-embedding ещё в коде, но решено выпилить. Может всплыть в default-конфиге если кто-то перепутает `EMBEDDING_BACKEND`. | Сначала вычищаем default-конфиг (`.env`, `pyproject.toml` extras), потом отдельным PR удаляем сам адаптер + тесты. |
| G | `e2e/live_scenario.py:28-29` | `os.environ.setdefault("OLLAMA_BASE_URL", ...)` — sticky, влияет на pytest и любые соседние процессы. | Перевести на `AGENT_LLM_BASE_URL`/`AGENT_LLM_MODEL` env через `OpenAIChatModel(provider=...)`. Phase 3. |
| H | `e2e/live_scenario.py:79` | `MODEL = "ollama:qwen3.5:9b"` — hard-coded Ollama-prefix формат, не env-driven. | Заменить на конструкцию `OpenAIChatModel(...)` управляемую env. Phase 3. |
| I | `pyproject.toml:43-50` | `eval` extras тянет `alembic>=1.13`, но в проде Alembic не используется (только в `eval/migrations/`). Раннер миграций самописный. | Не косяк, просто отметка: при выборе migration tool учесть — Alembic уже частично в проекте, есть смысл унифицировать (отдельная задача). |
| J | `deploy/atman-setup.sh:742,746` | `DO \$\$ BEGIN ... END \$\$` (с бэкслешами) внутри heredoc `<<'SQL'` (single-quoted tag). Бэкслеши попадают в psql литерально → syntax error → `atman_app` не создаётся → deploy валится молча в этом месте (видимо, поэтому БД оказалась пустая). | Заменить на `$$ BEGIN ... END $$;` (без бэкслешей). Я делаю это в `scripts/bootstrap_db.sql`, оригинал в setup.sh поправлю в Phase 2.3 SYNC. |

## Косяки в окружении (infra) — для контекста

| # | Что | Fix |
|---|---|---|
| inf-1 | `.venv/bin/python` → `/root/miniforge3/bin/python3` (root-owned) | Recreated venv under serg via `/home/serg/miniconda3/bin/python3 -m venv .venv`. |
| inf-2 | `atman-postgres` data dir owned by UID 1000, `pg_isready` ложно зелёный | chown postgres:postgres + restart. **TODO:** healthcheck заменить на `psql -c "SELECT 1"`. |
| inf-3 | БД полностью пустая | Bootstrap + migrations в Phase 2.2. |
| inf-4 | `atman-qdrant` unhealthy и не нужен | Игнорируем. **TODO:** опциональный Qdrant. |

## Открытые вопросы / риски

- HLE-32 `check_fact` / `check_entity` ещё не подключены к write-path; в smoke-прогоне мы видим только `check_key_moment`. Документировано как known gap в `inline_validator.py`.
- `bge-m3` через FlagEmbedding может потребовать > 30 с cold-start на CPU — узнаем в Phase 2.1.
- llama-server поддержка pydantic-ai tool-calling: если не сработает в Phase 4 — fallback на минимальный set из двух тулз.
- Reflection с gemma4 может выдавать невалидный JSON → fallback на `ATMAN_REFLECTION_BACKEND=mock` для первого прогона.

## Зачем ещё может потребоваться (think what else)

- pgvector extension должна быть включена — проверить в Phase 0 / 2.2 (`CREATE EXTENSION vector`).
- Embeddings dimensions: `bge-m3` = 1024; убедиться, что `facts.embedding` колонка в миграции 0002 совпадает (`vector(1024)`).
- HF cache путь — по умолчанию `~/.cache/huggingface`; если NVME mount-point свободнее, можно `HF_HOME=/mnt/nvme/atman/hf` (опционально).
- pre-commit hooks могут блокировать commit'ы; если не нужно — `git commit --no-verify` обсудить с пользователем (он не разрешал).
- llama-server сейчас уже поднят кем-то — проверить, что owner процесса понятен (`ps aux | grep llama-server`) и что параметры (контекст, GPU layers) разумные.
