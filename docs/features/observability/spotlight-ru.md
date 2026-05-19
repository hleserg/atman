# Spotlight — локальный UI для разработки

Spotlight — браузерный UI, который принимает Sentry envelopes и отображает трассы,
ошибки и спаны **без отправки данных в Sentry SaaS**.
Работает параллельно с реальным DSN: оба адресата получают данные.

## Быстрый старт

```bash
# Терминал 1 — запустить Spotlight
make spotlight          # открывает http://localhost:8969

# Терминал 2 — запустить Atman с debug-уровнем трассировки
ATMAN_OBS_LEVEL=debug SENTRY_DSN=http://fake@localhost/1 uvicorn atman.app:app
```

Отправьте любой запрос, затем откройте <http://localhost:8969> — там появится вотерфолл трасс.

> `ATMAN_OBS_LEVEL=debug` устанавливает `spotlight=True` в `sentry_sdk.init()`.
> SDK автоматически пересылает все envelopes в sidecar Spotlight.

## Способы настройки

### 1. Нативный Linux / macOS

Дополнительная конфигурация не нужна. `make spotlight` запускает sidecar;
SDK подключается к `http://localhost:8969/stream` по умолчанию.

### 2. WSL2

WSL2 автоматически перенаправляет `localhost` на Windows-хост начиная с Windows 10 21H2.
`make spotlight` работает без дополнительных настроек. Если Atman запущен внутри WSL2,
а Spotlight — в Windows (или наоборот), задайте:

```bash
export SENTRY_SPOTLIGHT=http://$(hostname).local:8969/stream
```

### 3. Docker Compose

Контейнер Atman не может обратиться к `localhost:8969` хоста напрямую.
Используйте `host.docker.internal` и Linux host-gateway:

```yaml
# docker-compose.yml — сервис atman
services:
  atman:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      ATMAN_OBS_LEVEL: debug
      SENTRY_DSN: "http://fake@localhost/1"
      SENTRY_SPOTLIGHT: "http://host.docker.internal:8969/stream"
```

Запустите Spotlight на хосте (`make spotlight`), затем `docker compose up`.

### 4. Standalone Electron-приложение

Скачайте десктопное приложение с <https://spotlightjs.com> — Node.js не нужен.
Запустите его перед стартом Atman; оно слушает порт 8969 автоматически.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|-------------|-----------|
| `ATMAN_OBS_LEVEL` | `minimal` | Установите `debug` или `verbose` для включения Spotlight |
| `SENTRY_SPOTLIGHT` | `http://localhost:8969/stream` | URL sidecar (Docker / WSL2) |
| `SENTRY_DSN` | _(не задан)_ | Можно использовать фейковый DSN (`http://fake@localhost/1`) для локальной трассировки |

`SENTRY_SPOTLIGHT` читается напрямую из sentry-sdk — никакого кода на стороне Atman не требуется.

## Связь с `init_observability()`

`spotlight=True` автоматически устанавливается для уровней `debug` и `verbose` в
`src/atman/observability/sentry_init.py`. Уровень `minimal` (продакшн-дефолт)
**не** включает Spotlight, чтобы исключить случайную пересылку данных в проде.

## Смотрите также

- [Уровни observability](levels.md) — полная матрица уровней
- [Руководство по инструментированию](README-ru.md) — span-хелперы и сканер
- Документация Spotlight: <https://spotlightjs.com/docs/>
