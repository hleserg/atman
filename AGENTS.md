# AGENTS.md

## Overview

Atman — проект психологического слоя для AI-агента. Репозиторий находится на стадии **прототипирования**: основная часть — документация (markdown-файлы), но уже есть первая реализация компонента Factual Memory.

**Текущее состояние**:
- ✅ Документация: архитектура, стандарты разработки, исследования
- ✅ Factual Memory Adapter v0.1.0: модели, порты, адаптеры, 41 unit-тест
- ✅ Базовая структура: `src/atman/`, `tests/`, `pyproject.toml`
- ⏳ Остальные компоненты (Experience Store, Identity Store, Reflection Engine) в очереди

**Для работы с кодом** см. раздел "Local Agent Instructions" ниже.

## Cursor Cloud specific instructions

### Структура репозитория

- `MANIFEST.md` — философский манифест проекта
- `docs/architecture/SYSTEM.md` — подробная архитектура системы (7 компонентов, режимы работы, протоколы)
- `docs/development/DEVELOPMENT_STANDARD.md` — стандарт разработки (терминология, границы, DoD)
- `docs/research/` — исследования (mem0, интеграции)
- `docs/ideas/` — идеи для будущих блоков
- `reports/sessions/` — шаблоны отчётов о сессиях
- `.github/` — шаблоны issue и PR
- `src/atman/` — реализация (Core, Adapters, Infrastructure)
- `tests/` — тесты
- `.cursor/` — инструкции для локальных агентов

### Lint / Test / Build / Run

**Текущее состояние кода**:
- ✅ Python код: `src/atman/` (Factual Memory реализован)
- ✅ Зависимости: `pyproject.toml` (Pydantic, pytest)
- ✅ Тесты: 41 unit-тест в `tests/` (все проходят)
- ❌ CI/CD workflows: пока нет
- ❌ Pre-commit hooks: пока нет

**Команды для работы с кодом**:
```bash
pip install -e .[dev]    # Установить зависимости (включая dev/test)
pytest tests/ -v         # Запустить тесты
python3 -m atman.cli     # Интерактивный CLI (Factual Memory)
```

**Для работы с документацией**: редактирование markdown-файлов, соблюдение двуязычной синхронизации.

**Важно**: При работе с кодом следуйте `docs/development/DEVELOPMENT_STANDARD.md` — канонические термины, границы Core/Adapter, Definition of Done.

### Планируемый стек (из архитектурных документов)

Когда код появится, проект будет использовать:
- Python ≥ 3.12, менеджер пакетов `uv`, build-система Hatchling
- PydanticAI + Anthropic (Claude), mem0, APScheduler
- Детали см. в `docs/architecture/SYSTEM.md`

### Язык документации

**Основной язык документации — английский.**

При работе с текстовыми файлами:
- Основная версия документов ведётся на английском языке
- Для ключевых файлов (`README.md`, `SYSTEM.md`) поддерживаются русские версии с суффиксом `-ru.md`
- При изменении английской версии необходимо синхронизировать соответствующую русскую версию
- Комментарии в коде — на английском
- Commit-сообщения — на английском

**Файлы с двуязычной поддержкой:**
- `README.md` / `README-ru.md`
- `docs/architecture/SYSTEM.md` / `docs/architecture/SYSTEM-ru.md`
- `MANIFEST.md` / `MANIFEST-ru.md`

### Полезные заметки

- PR-шаблон находится в `.github/pull_request_template.md` — используйте его при создании PR.
- Нет pre-commit хуков, lint-staged, или CI workflows.

## Local Agent Instructions

**For local Cursor agents** (not cloud agents), read the master prompt before starting any work:

📋 **Master Prompt**: [`.cursor/local-agent-master-prompt.md`](.cursor/local-agent-master-prompt.md)

The master prompt provides:
- Complete workflow and standards
- Links to all essential documentation
- Terminology discipline rules
- Architecture boundaries (Core vs Adapters)
- Definition of Done checklist
- Forbidden actions and common pitfalls

**Why separate from cloud instructions?**
- Cloud agents get `AGENTS.md` injected automatically
- Local agents need explicit guidance to follow the same standards
- Master prompt ensures local agents don't "go rogue" and follow project rules

**Before starting work, always**:
1. Read `.cursor/local-agent-master-prompt.md`
2. Review `docs/development/DEVELOPMENT_STANDARD.md`
3. Check relevant sections in `docs/architecture/SYSTEM.md`
