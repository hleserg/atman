# Справочник по эндпоинтам

> Автоматически сгенерировано `make codemap`. Не редактировать.
> Источник: скрипты `pyproject.toml`, `docker-compose.yml`, AST-сканирование CLI.

## Команды CLI (`[project.scripts]`)

| Команда | Точка входа |
|---------|-------------|
| `atman` | `atman.cli:main` |
| `atman-dev` | `atman.tui.app:main` |
| `atman-experience` | `atman.cli_experience:main` |
| `atman-identity` | `atman.cli_identity:main` |
| `atman-maintenance` | `atman.cli_maintenance:main` |
| `atman-skills` | `atman.skills.cli:main` |
| `atman-web` | `atman.web_dashboard:main` |
| `devui` | `atman.tui.app:main` |
| `webui` | `atman.web_dashboard:main` |

## Команды CLI (обнаружены в исходном коде)

| Компонент | Команда |
|-----------|---------|
| `eval` | `list_command` |
| `eval` | `run_command` |

## Порты инфраструктуры (`docker-compose.yml`)

| Сервис | Порты | Назначение |
|---------|-------|---------|
| `postgres` | `127.0.0.1:5432:5432` | Реляционное хранилище (факты, рефлексии, состояние) |
| `qdrant` | `127.0.0.1:6333:6333`, `127.0.0.1:6334:6334` | Векторный поиск (извлечение опыта) |

## HTTP API

Маршруты FastAPI определены в `src/atman/` (см. опциональную зависимость `[api]`).
Запустите `uvicorn atman.api:app --reload` и откройте `/docs` для интерактивного Swagger UI.
