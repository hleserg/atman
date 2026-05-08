# Atman — Docker Compose
# Генерируется из deploy/docker-compose.yml.tpl через envsubst
# Управление: docker compose up -d / stop / down

version: '3.9'

services:
  postgres:
    image: pgvector/pgvector:pg${POSTGRES_VERSION}
    container_name: atman-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --lc-collate=C --lc-ctype=C"
    ports:
      - "127.0.0.1:${POSTGRES_PORT}:5432"
    volumes:
      - atman-postgres-data:/var/lib/postgresql/data
      - ${PG_BACKUP_PATH}:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:${QDRANT_VERSION}
    container_name: atman-qdrant
    restart: unless-stopped
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
    ports:
      - "127.0.0.1:${QDRANT_PORT}:6333"
      - "127.0.0.1:6334:6334"
    volumes:
      - atman-qdrant-data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  atman-postgres-data:
  atman-qdrant-data:
