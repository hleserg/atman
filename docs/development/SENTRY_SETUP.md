# Sentry — настройка мониторинга

## 1. Создать проект

1. Зарегистрироваться на **sentry.io** (бесплатный план — 5k ошибок/мес)
2. **Create Project → Python**
3. Скопировать DSN: `https://abc123@o123456.ingest.sentry.io/456789`

---

## 2. Прописать DSN

В файле `.env` в корне проекта:

```bash
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/456789
SENTRY_ENVIRONMENT=development        # development | staging | production
SENTRY_TRACES_SAMPLE_RATE=0.2         # 0..1, какой % сессий трейсируется
```

Установить пакет (если ещё не установлен):

```bash
pip install -e "."   # sentry-sdk[httpx,asyncio] теперь в основных зависимостях
```

---

## 3. Smoke-test (30 секунд)

Убедиться что интеграция работает до запуска агента:

```bash
PYTHONPATH=src python3 -c "
import os
os.environ['SENTRY_DSN'] = 'твой-dsn'
from atman.adapters.observability.sentry import _init, capture_silent_exception
_init(dsn=os.environ['SENTRY_DSN'], environment='test')
capture_silent_exception(ValueError('test ping from Atman'), context='smoke_test')
print('ping sent — подожди 10 сек и смотри Issues в Sentry')
"
```

В дашборде Sentry → **Issues** должен появиться `ValueError: test ping from Atman`.

---

## 4. Живая сессия

```bash
SENTRY_DSN=... make live-chat
```

После сессии в Sentry:
- **Performance → Transactions** — транзакция `session_lifecycle` со span-деревом (httpx к LLM, tool calls)
- **Metrics → atman.llm.latency_ms** — распределение latency LLM-вызовов
- **Metrics → atman.session.duration** — длительность сессии
- **Metrics → atman.rag.items_injected** — сколько items ambient RAG подсветил

---

## 5. Maintenance cron

```bash
SENTRY_DSN=... python3 -m atman.cli_maintenance run --loop --interval 3600
```

В Sentry → **Crons** → монитор `atman-maintenance` с check-in статусами каждого batch'а.

---

## 6. Постоянная работа

### systemd

```ini
# /etc/systemd/system/atman-maintenance.service
[Service]
EnvironmentFile=/atman/atman/.env
ExecStart=/usr/bin/python3 -m atman.cli_maintenance run --loop --interval 3600
Restart=on-failure
```

```bash
systemctl daemon-reload
systemctl enable --now atman-maintenance
```

### Docker Compose

```yaml
environment:
  - SENTRY_DSN=${SENTRY_DSN}
  - SENTRY_ENVIRONMENT=production
```

---

## 7. Что отслеживается автоматически

| Что | Где смотреть |
|-----|-------------|
| Все `logging.error(...)` с `exc_info` | Issues |
| Все httpx-запросы к LLM | Performance → Spans |
| Ошибки affect detector (раньше молчали) | Issues, тег `silent_context=affect_detector` |
| Ошибки auto-record refusal (раньше молчали) | Issues, тег `silent_context=auto_record_refusal` |
| Каждый maintenance batch | Crons → atman-maintenance |
| Latency LLM-ответов | Metrics → atman.llm.latency_ms |
| Длительность сессий | Metrics → atman.session.duration |
| Ambient RAG activity | Metrics → atman.rag.items_injected |

---

## 8. Фильтрация по агенту

Все события тегированы `agent_id` и `session_id`.  
В Sentry можно фильтровать: **Issues → Filter → agent_id = <uuid>**.

---

## Важно

- Без `SENTRY_DSN` в окружении — интеграция полностью отключена, поведение идентично прежнему
- DSN не коммитить в git — только в `.env` (он в `.gitignore`)
