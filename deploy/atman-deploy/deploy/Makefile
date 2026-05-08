# =============================================================================
# Atman — Makefile для управления инфраструктурой
# Использование: make <команда>
# =============================================================================

.PHONY: help up down restart logs status setup smoke backup pull-models \
        psql qdrant-info quality reset-db

# Секреты и конфиг
-include ../.env
DOCKER ?= docker

help: ## Показать все команды
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Инфраструктура ────────────────────────────────────────────────────────────

setup: ## Полный деплой (первый запуск)
	bash setup.sh

up: ## Запустить PostgreSQL и Qdrant
	$(DOCKER) compose -f ../docker-compose.yml up -d
	@echo "Ollama: sudo systemctl start ollama"

down: ## Остановить всё
	$(DOCKER) compose -f ../docker-compose.yml stop
	sudo systemctl stop ollama 2>/dev/null || true

restart: ## Перезапустить
	$(DOCKER) compose -f ../docker-compose.yml restart
	sudo systemctl restart ollama

status: ## Статус всех сервисов
	@echo "=== Docker ==="
	@$(DOCKER) ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" \
	  | grep -E "NAME|atman" || echo "нет запущенных контейнеров"
	@echo ""
	@echo "=== Ollama ==="
	@systemctl is-active ollama 2>/dev/null && ollama list || echo "не запущена"
	@echo ""
	@echo "=== GPU ==="
	@nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader 2>/dev/null || echo "nvidia-smi недоступен"

logs: ## Логи (postgres + qdrant)
	@$(DOCKER) compose -f ../docker-compose.yml logs --tail=50 -f

logs-pg: ## Логи только PostgreSQL
	@$(DOCKER) logs -f atman-postgres

logs-ollama: ## Логи Ollama
	@journalctl -u ollama -f --no-pager

# ── Модели ───────────────────────────────────────────────────────────────────

pull-models: ## Скачать/обновить модели Ollama
	ollama pull $(OLLAMA_LLM_MODEL)
	ollama pull $(OLLAMA_EMBED_MODEL)

# ── БД ───────────────────────────────────────────────────────────────────────

psql: ## Открыть psql консоль
	$(DOCKER) exec -it atman-postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

schema-apply: ## Применить схему (идемпотентно)
	$(DOCKER) exec -i atman-postgres \
	  psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < schema.sql

reset-db: ## ⚠️  Удалить и пересоздать БД (ТЕРЯЮТСЯ ВСЕ ДАННЫЕ)
	@echo "Это удалит все данные. Введи 'yes' для подтверждения:"
	@read CONFIRM && [ "$$CONFIRM" = "yes" ] || exit 1
	$(DOCKER) rm -f atman-postgres || true
	$(DOCKER) volume rm atman-postgres-data || true
	$(DOCKER) compose -f ../docker-compose.yml up -d postgres
	sleep 5
	$(DOCKER) exec -i atman-postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < schema.sql
	@echo "БД пересоздана"

backup: ## Бэкап PostgreSQL
	$(DOCKER) exec atman-postgres pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) \
	  | gzip > ../$(shell date +%Y%m%d_%H%M%S)_atman_backup.sql.gz
	@echo "Бэкап создан"

restore: ## Восстановить из последнего бэкапа (BACKUP=файл.sql.gz)
	@[ -n "$(BACKUP)" ] || (echo "Укажи BACKUP=файл.sql.gz"; exit 1)
	zcat $(BACKUP) | $(DOCKER) exec -i atman-postgres \
	  psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

# ── Мониторинг ───────────────────────────────────────────────────────────────

smoke: ## Запустить smoke test
	bash smoke-test.sh \
	  "$(POSTGRES_USER)" "$(POSTGRES_DB)" \
	  "$(QDRANT_PORT)" "$(QDRANT_API_KEY)" \
	  "$(ATMAN_EMBED_MODEL)" "$(DOCKER)"

quality: ## Показать метрики качества памяти
	$(DOCKER) exec atman-postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c \
	  "SELECT agent_id, facts_total, experiences_total, \
	          incomplete_coloring_rate, avg_salience, \
	          emotional_baseline, days_since_narrative_update \
	   FROM memory_quality_metrics;"

alerts: ## Показать активные алерты
	$(DOCKER) exec atman-postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c \
	  "SELECT alert_type, severity, details, alerted_at \
	   FROM quality_alerts WHERE resolved_at IS NULL \
	   ORDER BY severity DESC, alerted_at DESC LIMIT 20;"

qdrant-info: ## Информация о коллекциях Qdrant
	@curl -sf http://localhost:$(QDRANT_PORT)/collections \
	  -H "api-key: $(QDRANT_API_KEY)" | python3 -m json.tool

refresh-metrics: ## Обновить матвью метрик качества
	$(DOCKER) exec atman-postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) \
	  -c "SELECT refresh_quality_metrics();"

check-alerts: ## Проверить и записать новые алерты
	$(DOCKER) exec atman-postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) \
	  -c "SELECT check_quality_alerts() AS new_alerts;"
