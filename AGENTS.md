# AGENTS.md

## Overview

Atman — проект, реализующий психологический слой для AI-агента. Репозиторий на стадии **прототипирования**: содержит документацию и первый реализованный компонент — Factual Memory Adapter (Python-библиотека).

## Cursor Cloud specific instructions

### Структура репозитория

- `src/atman/` — исходный код Python-пакета (Factual Memory Adapter)
- `src/demo.py` — демо-скрипт для проверки работы адаптера
- `tests/` — unit-тесты (pytest)
- `pyproject.toml` — конфигурация проекта и зависимостей
- `MANIFEST.md` — философский манифест проекта
- `docs/architecture/SYSTEM.md` — подробная архитектура системы (7 компонентов, режимы работы, протоколы)
- `docs/research/` — исследования (mem0, интеграции)
- `docs/ideas/` — идеи для будущих блоков
- `docs/development/` — стандарты разработки и work packages
- `reports/sessions/` — шаблоны отчётов о сессиях
- `.github/` — шаблоны issue и PR, workflows

### Lint / Test / Build / Run

**Требования:** Python ≥ 3.12

**Установка зависимостей:**
```bash
pip install -e ".[dev]"
```

**Запуск тестов:**
```bash
pytest tests/ -v
```

**Запуск демо:**
```bash
python3 src/demo.py
```

**Запуск CLI (интерактивный):**
```bash
python3 -m atman.cli
```

Линтеров и CI/CD workflows пока нет. Нет внешних зависимостей (баз данных, API и т.д.) — всё работает локально с file-based (JSONL) или in-memory хранилищем.

### Стек

- Python ≥ 3.12, build-система Hatchling
- `pydantic>=2.0.0` — единственная runtime-зависимость
- `pytest>=7.0.0`, `pytest-asyncio>=0.21.0` — dev-зависимости
- Планируется: PydanticAI + Anthropic (Claude), mem0, APScheduler (см. `docs/architecture/SYSTEM.md`)

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
- CLI использует file storage в `~/.atman/facts.jsonl` по умолчанию.
- Все тесты запускаются за <1 секунду, внешних сервисов не требуется.
