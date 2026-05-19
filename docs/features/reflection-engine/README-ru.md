# Движок рефлексии

> **English:** [README.md](README.md)

## Что делает

Движок рефлексии обрабатывает накопленный опыт и генерирует структурированные инсайты о паттернах, здоровье и развитии агента. Он работает на трёх уровнях глубины, каждый с собственной областью охвата и триггером.

Рефлексия — это не интроспекция в ходе разговора. Она происходит между сессиями, как отдельный шаг обработки.

## Три уровня

### Micro Reflection — `MicroReflectionService`

Запускается после закрытия каждой сессии. Обновляет уровень RECENT нарративного документа синтезом произошедшего. Лёгкий процесс: без обнаружения паттернов, без оценки здоровья.

### Daily Reflection — `DailyReflectionService`

Запускается раз в день (или по требованию). Сканирует последние записи `SessionExperience` для обнаружения новых объектов `PatternCandidate`. Каждый паттерн имеет `PatternType` (поведенческий, реляционный, когнитивный и т.д.) и `PatternStatus` (emerging, confirmed, resolved).

### Deep Reflection — `DeepReflectionService`

Запускается еженедельно или по требованию. Выполняет полный структурный анализ: картирование связей сущностей, обнаружение кандидатов на слияние среди опытов, оценка здоровья по критериям Яходы. Может предлагать изменения идентичности агента через `apply_self_change`.

## Ключевые концепции

**`PatternCandidate`** — обнаруженный поведенческий или когнитивный паттерн. Имеет тип, статус, ссылки на доказательства и оценку достоверности.

**`PatternStatus`** — `emerging` | `confirmed` | `resolved`. Паттерны продвигаются по статусам по мере накопления доказательств.

**`PatternType`** — классификация паттерна (поведенческий, реляционный, когнитивный, аффективный и т.д.).

**`ReflectionEvent`** — запись об отдельном запуске рефлексии: уровень, что было найдено, время запуска.

**`HealthAssessment`** — структурированная оценка психологического здоровья агента по критериям Яходы.

**`JahodaCriterion`** — один из шести критериев позитивного психического здоровья Мари Яходы (самопринятие, рост, автономия, восприятие реальности, мастерство в среде, позитивные отношения). Каждый критерий получает `CriterionAssessment` с оценкой и обоснованием.

**`ReflectionRecord`** — персистентный вывод завершённого запуска рефлексии, хранимый через `ReflectionEventStore`.

**Порт `ReflectionModel`** — интерфейс для основанной на LLM модели рефлексии. Реализации:
- `OpenAIReflectionModel` — вызывает любой OpenAI-совместимый эндпоинт
- `MockReflectionModel` — детерминированный вывод для тестов

## Публичный API

```python
# Micro рефлексия — запустить после закрытия сессии
await micro_service.run(agent_id=agent_id, session_id=session_id)

# Daily рефлексия — обнаружение паттернов
result = await daily_service.run(agent_id=agent_id)
for pattern in result.new_patterns:
    print(pattern.type, pattern.status, pattern.confidence)

# Deep рефлексия — полный анализ
result = await deep_service.run(agent_id=agent_id)
print(result.health_assessment.overall_score)
```

## Конфигурация

```bash
# Бэкенд модели рефлексии: openai | anthropic | mock  (по умолчанию: openai)
ATMAN_REFLECTION_BACKEND=openai

# LLM-эндпоинт, используемый OpenAIReflectionModel
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_MODEL=gemma3:27b-it-qat
```

## CLI

```bash
# Запустить рефлексию вручную
python -m atman.cli_reflection reflect micro --agent-id <uuid>
python -m atman.cli_reflection reflect daily --agent-id <uuid>
python -m atman.cli_reflection reflect deep --agent-id <uuid>

# Потоковый вывод в реальном времени
python -m atman.cli_reflection reflect micro --live --agent-id <uuid>
```
