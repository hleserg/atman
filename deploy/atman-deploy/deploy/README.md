# deploy/

Всё что нужно для развёртывания Atman на чистой машине.

## Структура

```
deploy/
├── setup.sh                   # главный скрипт — запускать этот
├── config.env                 # параметры деплоя (в git, без секретов)
├── schema.sql                 # схема PostgreSQL (идемпотентная)
├── docker-compose.yml.tpl     # шаблон → генерируется в ../docker-compose.yml
├── ollama-override.conf.tpl   # шаблон → /etc/systemd/system/ollama.service.d/
├── install-docker.sh          # установка Docker (вызывается из setup.sh)
├── gen-secrets.sh             # генерация паролей (вызывается из setup.sh)
├── smoke-test.sh              # проверка после деплоя
├── Makefile                   # удобные команды для повседневной работы
└── .gitignore                 # исключения (секреты, сгенерированные файлы)
```

## Быстрый старт

```bash
# Из корня репозитория
bash deploy/setup.sh

# С явным путём для данных
bash deploy/setup.sh --data-path /mnt/nvme/atman

# Без скачивания моделей (потом вручную)
bash deploy/setup.sh --skip-models
```

## Что создаётся автоматически

| Файл | Где | Описание |
|---|---|---|
| `~/.atman/.secrets` | хост | пароли и ключи, `chmod 600` |
| `../.env` | проект | копия секретов для Python |
| `../docker-compose.yml` | проект | из шаблона |
| `/etc/systemd/system/ollama.service.d/override.conf` | система | настройки Ollama |

## Что НЕ в git

- `~/.atman/.secrets` — пароли и ключи
- `../.env` — то же самое, для Python
- `../docker-compose.yml` — содержит пути к данным конкретной машины

## Повседневное управление

```bash
cd deploy

make status        # статус всех сервисов
make up            # запустить инфраструктуру
make down          # остановить
make backup        # бэкап PostgreSQL
make quality       # метрики качества памяти
make alerts        # активные алерты
make psql          # открыть psql консоль
make smoke         # smoke test
make help          # все команды
```

## Требования

- Ubuntu 22.04+ (или WSL2 с Ubuntu)
- `sudo` доступ
- `curl`
- NVIDIA GPU для Ollama (опционально — без GPU работает на CPU)

Всё остальное (uv, Docker, Ollama) устанавливается автоматически.

## Переменные конфига

Все параметры деплоя в `config.env`. Менять можно:

- `OLLAMA_LLM_MODEL` — какую LLM использовать
- `OLLAMA_EMBED_MODEL` — embedding модель
- `POSTGRES_PORT` / `QDRANT_PORT` — порты если заняты
- `OLLAMA_FLASH_ATTENTION` — выключить если проблемы с GPU

## Идемпотентность

Скрипт и схема безопасно запускаются повторно:
- существующие контейнеры не пересоздаются
- существующие секреты не перезаписываются
- `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` везде
- `DROP POLICY IF EXISTS` перед `CREATE POLICY`
