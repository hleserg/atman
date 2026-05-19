# Session Tester Runbook

Скрипт `e2e/session_tester.py` прогоняет 6 живых сценариев с агентом и отчитывается
о здоровье всех компонентов: entity detection, ambient/passive RAG, affect detector,
auto key moments, tool calls, session finish, micro-reflection.

---

## Запуск

```bash
cd /atman/atman   # или .claude/worktrees/<branch>

# Убедись что запущены:
#   - llama-server на :8081
#   - PostgreSQL (параметры из .env)

make warmup-models   # только при первом запуске (скачивает ~6 GB, потом ~30 сек)

PYTHONPATH=src:. python3 e2e/session_tester.py
```

Вывод идёт в stdout. Логи ошибок — в stderr.

---

## Сценарии (6 штук, рандомный порядок)

| ID | Категория | Тема |
|----|-----------|------|
| soul-1 | по душам | Непрерывность и самоощущение |
| soul-2 | по душам | Ценности и границы |
| work-1 | работа | PostgreSQL wire-протокол |
| work-2 | работа | Race condition при concurrent insert |
| complaint-1 | жалобы | Забывание и потери |
| complaint-2 | жалобы | Смысл и усталость |

Структура каждого сценария:
- **Ход 1**: фиксированный открывающий вопрос от тестера
- **Ход 2**: динамический follow-up — читает реальный ответ агента, выбирает
  фразу из него, задаёт уточняющий вопрос в стиле категории
- **Ход 3**: финальный вопрос (тоже динамический)

---

## Что проверяется

| Компонент | Что значит OK |
|-----------|---------------|
| Entity detection | GLiNER нашёл хотя бы одну сущность за сессию |
| Ambient RAG | `compose_injection` вернул >0 items |
| Passive RAG | `surface_for_context` вернул >0 items (пусто на чистой БД — `ℹ`) |
| Affect detector | `AffectDetector.process()` выполнился для каждого хода |
| Auto key moments | NLP обнаружил boundary event → `sm.append_key_moment()` |
| Agent tool calls | Агент вызвал хотя бы один тул (record_key_moment и др.) |
| Session finish | `sm.finish_session()` завершился без ошибок |
| Micro-reflection | `micro_reflection.reflect()` выполнился, вернул insight |

---

## Интерпретация результатов

**✅** — компонент работает нормально  
**⚠** — компонент доступен, но в этой сессии не сработал (например, no boundary event)  
**ℹ** — компонент работает, но данных ещё нет (пустая БД, агент не вызвал тул)  
**❌** — компонент упал с ошибкой — **нужно разбираться**

### Типичные проблемы

| Симптом | Вероятная причина |
|---------|------------------|
| Entity detection ⚠ everywhere | GLiNER не загружен, или `ATMAN_LINGUISTIC_ENABLED=false` |
| Affect detector ❌ | `sm.affect_detector` is None — PostgreSQL не подключён при build_deps |
| Passive RAG ⚠ everywhere | Чистая БД — прогони несколько реальных сессий сначала |
| Micro-reflection ❌ | `deps.micro_reflection` не wired — проверь factory.py |
| Session finish ❌ с "Cannot finish without key moments" | force_finish отработал (это `⚠`, не `❌`) |
| LLM timeout на каждом ходу | llama-server не запущен или перегружен |

---

## Preflight перед запуском

Скрипт сам не запускает preflight. Проверь вручную:

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from atman.adapters.agent.preflight import check_postgres, check_llm, check_nlp_packages, _pg_url
import os
# load .env manually if needed
url = _pg_url()
print('PG:', check_postgres(url))
print('LLM:', check_llm(os.getenv('AGENT_LLM_BASE_URL', 'http://localhost:8081/v1')))
print('NLP missing:', check_nlp_packages())
"
```

---

## Добавление сценариев

Добавь объект `Scenario` в список `SCENARIOS` в `e2e/session_tester.py`:

```python
Scenario(
    name="my-scenario: описание",
    category="soul",   # soul | work | complaint | <custom>
    opening="Первый вопрос от тестера...",
    n_turns=3,
)
```

Для нестандартной категории добавь ветку в `_followup()`.
