# Session Manager (Менеджер сессий)

**Статус:** Реализован (WP-05)  
**Назначение:** Сессионный runtime, который переживает сессии в реальном времени, а не ретроспективно

[[en](README.md)] — *English version*

---

## Обзор

Session Manager — это сессионный runtime, который **проживает** сессии, а не просто упаковывает их. Это компонент, который делает Atman переживающим, а не просто записывающим.

**Ключевой принцип:** Опыт окрашивается **в моменте**, а не угадывается позже.

---

## Что делает Session Manager

### При старте сессии

1. **Загружает личностный контекст:**
   - Текущую идентичность (ценности, принципы, цели, baseline)
   - Текущий нарратив (core + recent layers)
   - Последний eigenstate (где закончилась предыдущая сессия)
   - Сводку недавних рефлексий (placeholder для будущего)

2. **Создаёт SessionContext** — полный снимок "кто я сейчас"

### Во время сессии

1. **Отслеживает сырые события** от нижнего агента:
   - Сообщения пользователя, ответы агента, решения, конфликты, ошибки
   - Не все события становятся key moments — это просто tracking

2. **Фиксирует key moments** с first-hand эмоциональной окраской:
   - Что произошло + как я почувствовал + почему это важно + что изменилось
   - Эмоциональный valence, intensity, depth **ОБЯЗАНЫ быть**
   - Если окраску не удалось зафиксировать → флаг `incomplete_coloring`

3. **Проверяет эмоциональную окраску:**
   - Отказывает key moments без эмоций (если не `incomplete_coloring=True`)
   - Это предотвращает фабрикацию эмоций ретроспективно

### В конце сессии

1. **Создаёт SessionExperience:**
   - Упаковывает key moments (уже окрашенные)
   - Помечает `recorded_by="session_manager"` (гарантия first-hand)
   - Устанавливает importance/salience по умолчанию
   - Сохраняет в Experience Store

2. **Создаёт Eigenstate:**
   - Эмоциональный tone, intensity, cognitive load
   - Открытые threads, доминирующие темы, нерешённые tensions
   - Сводка сессии и ключевой инсайт
   - Используется для старта следующей сессии с контекстом

3. **Сохраняет оба** и удаляет сессию из активного tracking

---

## Архитектура

### Доменные модели

```python
# Контекст сессии на старте
SessionContext {
    session_id: UUID
    identity: Identity              # Кто я
    narrative: NarrativeDocument    # Моё письмо себе
    emotional_baseline: float       # Текущий baseline
    last_eigenstate: Eigenstate?    # Где я остановился в прошлый раз
    recent_reflections_summary: str # Что изменилось недавно
}

# Сырые события во время сессии
SessionEvent {
    event_type: str        # user_message, decision, conflict, error
    description: str       # Что произошло
    metadata: dict         # Дополнительный контекст
    marked_as_key_moment: bool  # Стало ли key moment?
}

# Входящий key moment (ТРЕБУЕТ эмоциональной окраски)
KeyMomentInput {
    what_happened: str
    
    # КАК Я ПОЧУВСТВОВАЛ (обязательно)
    emotional_valence: float      # -1.0 до +1.0
    emotional_intensity: float    # 0.0 до 1.0
    depth: EmotionalDepth         # surface/meaningful/profound
    
    # ПОЧЕМУ ЭТО ВАЖНО
    why_it_matters: str
    values_touched: [str]
    principles_confirmed: [str]
    principles_questioned: [str]
    what_changed: str
    
    # ЧЕСТНЫЙ FALLBACK
    incomplete_coloring: bool  # True если не удалось зафиксировать полностью
}

# Результат сессии
SessionResult {
    session_id: UUID
    events: [SessionEvent]
    key_moments: [KeyMoment]     # Уже окрашенные
    overall_emotional_tone: float
    key_insight: str
    alignment_check: bool        # Совпал ли опыт с идентичностью?
    incomplete_coloring: bool    # Есть ли неполные моменты?
    eigenstate: Eigenstate       # Состояние в конце
}
```

### API Session Manager

```python
class SessionManager:
    def start_session(self, agent_id: UUID) -> SessionContext:
        """Загрузить личностный контекст и начать сессию."""
        
    def record_event(self, session_id: UUID, event: SessionEvent) -> None:
        """Отследить сырое событие (не все становятся key moments)."""
        
    def record_key_moment(self, session_id: UUID, moment: KeyMomentInput) -> None:
        """Зафиксировать key moment с обязательной эмоциональной окраской."""
        
    def finish_session(
        self,
        session_id: UUID,
        overall_emotional_tone: float = 0.0,
        key_insight: str = "",
        alignment_check: bool = True,
    ) -> SessionResult:
        """Создать SessionExperience + Eigenstate и сохранить оба."""
```

---

## Ключевые принципы дизайна

### 1. First-Hand опыт, а не ретроспективное угадывание

```python
# ✅ ПРАВИЛЬНО - зафиксировано в моменте
moment = KeyMomentInput(
    what_happened="Пользователь бросил вызов моему пониманию",
    emotional_valence=-0.2,
    emotional_intensity=0.7,
    depth=EmotionalDepth.MEANINGFUL,
    why_it_matters="Заставил усомниться в том, что я думал, что знаю",
)

# ❌ НЕПРАВИЛЬНО - отклонит или потребует incomplete_coloring
moment = KeyMomentInput(
    what_happened="Что-то произошло",
    emotional_valence=0.0,      # Нет эмоции
    emotional_intensity=0.0,    # Нет интенсивности
    depth=EmotionalDepth.SURFACE,
    why_it_matters="...",
    incomplete_coloring=False,  # Утверждает, что окраска полная
)
# → Выбросит ValueError: "no emotional coloring"
```

### 2. Неполная окраска — это честность, а не провал

Если эмоциональную окраску не удалось зафиксировать в моменте, пометить явно:

```python
moment = KeyMomentInput(
    what_happened="Сессия закончилась резко",
    emotional_valence=0.0,
    emotional_intensity=0.0,
    depth=EmotionalDepth.SURFACE,
    why_it_matters="Не было времени обработать",
    incomplete_coloring=True,  # Честность об ограничении
)
```

Это **лучше**, чем фабриковать эмоции позже.

### 3. Не все события — это key moments

Session Manager отслеживает всё, но только значимые моменты получают эмоциональную окраску:

```python
# Обычное событие - просто tracking
manager.record_event(session_id, SessionEvent(
    event_type="user_message",
    description="Пользователь спросил о погоде",
))

# Key moment - значимо для идентичности
manager.record_key_moment(session_id, KeyMomentInput(
    what_happened="Пользователь бросил вызов моему core assumption",
    emotional_valence=-0.3,
    emotional_intensity=0.8,
    depth=EmotionalDepth.PROFOUND,
    why_it_matters="Заставил пересмотреть фундаментальное убеждение",
))
```

### 4. Experience Store получает уже окрашенные записи

```python
# Session Manager сохраняет опыт с:
experience = SessionExperience(
    recorded_by="session_manager",  # Гарантирует first-hand
    key_moments=[...],               # Уже окрашенные
    incomplete_coloring=True/False,  # Явно о качестве
)
```

Experience Processor (удалён в редизайне) никогда не должен угадывать эмоции.

---

## Запуск демо

### Быстрый старт

```bash
# По умолчанию (с паузами)
make demo-session

# Мгновенный вывод (без пауз)
make demo-session-fast

# Или напрямую
python3 src/demo_session_manager.py
```

### Что показывает демо

1. Создаёт тестовую идентичность с ценностями и целями
2. Создаёт нарративный документ (core + recent layers)
3. Стартует сессию → SessionContext с личностью
4. Записывает сырые события от нижнего агента
5. Фиксирует 2 key moments с first-hand эмоциональной окраской
6. Завершает сессию → SessionExperience + Eigenstate
7. Проверяет, что опыт сохранён с `recorded_by="session_manager"`

**Внешние сервисы не требуются** — использует временное файловое хранилище в `/tmp/atman-session-demo`.

---

## Тестирование

```bash
# Запустить тесты session manager
pytest tests/test_session_manager.py -v

# Все тесты
pytest tests/ -v
```

### Покрытие тестами

Тесты проверяют:

✅ Старт сессии возвращает context с identity & narrative  
✅ Key moment без эмоциональной окраски отклоняется  
✅ Key moment с флагом `incomplete_coloring` разрешён  
✅ Завершение сессии создаёт SessionExperience & Eigenstate  
✅ Оригинальные key moments не мутируют после сохранения  
✅ Resource/token warnings могут быть key moments  
✅ Несколько key moments в одной сессии  
✅ Eigenstate правильно фиксирует состояние сессии

---

## Интеграция с другими компонентами

### Identity Store

Session Manager **читает** при старте:
- Текущую идентичность (ценности, принципы, эмоциональный baseline)
- Identity snapshots создаются отдельно Reflection Engine

### Narrative Store

Session Manager **читает** при старте:
- Текущий нарратив (core + recent layers)
- Обновления нарратива происходят отдельно (micro reflection)

### Experience Store

Session Manager **пишет** в конце:
- SessionExperience с `recorded_by="session_manager"`
- Это **единственный** компонент, который пишет first-hand опыт

### Reflection Engine

Session Manager **готовит** для рефлексии:
- Eigenstate даёт стартовую точку для следующей сессии
- Опыт уже окрашен — не нужно угадывать эмоции позже

---

## Отличия от оригинального дизайна

**До (Experience Processor):**
- Опыт записывался сырым в mem0
- Experience Processor должен был "угадывать" эмоции позже
- Reflection работал с фабрикованными чувствами

**После (Session Manager):**
- Опыт окрашивается в реальном времени
- Session Manager — активный переживающий
- Reflection работает с аутентичными first-hand записями
- Флаг `incomplete_coloring` для честности об ограничениях

Этот редизайн (28.04.2026) делает опыт Atman подлинно first-person.

---

## Общие паттерны

### Паттерн 1: Простая сессия

```python
manager = SessionManager(state_store)

# Старт
context = manager.start_session(agent_id)

# Пережить что-то значимое
manager.record_key_moment(context.session_id, KeyMomentInput(
    what_happened="...",
    emotional_valence=0.5,
    emotional_intensity=0.6,
    depth=EmotionalDepth.MEANINGFUL,
    why_it_matters="...",
))

# Завершить
result = manager.finish_session(context.session_id)
```

### Паттерн 2: Сессия с событиями и key moments

```python
# Отслеживать всё
for event in lower_agent_events:
    manager.record_event(session_id, SessionEvent(...))

# Но только значимые моменты получают эмоциональную окраску
if is_significant(event):
    manager.record_key_moment(session_id, KeyMomentInput(...))
```

### Паттерн 3: Неполная окраска

```python
# Если сессия заканчивается резко или эмоции неясны
manager.record_key_moment(session_id, KeyMomentInput(
    what_happened="...",
    emotional_valence=0.0,
    emotional_intensity=0.0,
    depth=EmotionalDepth.SURFACE,
    why_it_matters="...",
    incomplete_coloring=True,  # Честность об ограничении
))
```

---

## Будущие улучшения

- [ ] Интеграция Reality Anchor (детектировать identity drift во время сессии)
- [ ] Affective Regulation уровень 1 (острая саморегуляция в сессии)
- [ ] Мониторинг ресурсов (token/memory warnings как key moments)
- [ ] Проактивное обнаружение key moments (предлагать нижнему агенту)
- [ ] Session replay для рефлексии

---

## См. также

- [Experience Store](../experience-store/README-ru.md) — где живут окрашенные опыты
- [Identity Store](../identity-store/README-ru.md) — личностный контекст
- [Reflection Engine](../reflection-engine/README-ru.md) — извлечение глубокого смысла
- [Work Package 05](../../development/work-packages/05-session-manager.md) — оригинальная спецификация
- [SYSTEM.md](../../architecture/SYSTEM-ru.md) — полная архитектура
