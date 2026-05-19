# Installing Atman

> **Russian version:** [INSTALLATION-ru.md](INSTALLATION-ru.md)

## Requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12+ | Runtime |
| [uv](https://github.com/astral-sh/uv) | latest | Environment and dependency management |
| Docker + Docker Compose | 24+ | PostgreSQL (optional) |
| llama.cpp (`llama-server`) or Ollama | — | LLM for reflections |

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Installing Dependencies

Clone the repository and install:

```bash
git clone https://github.com/your-org/atman.git
cd atman

# Create virtual environment and install in editable mode
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

For production without dev tools:

```bash
uv pip install atman
```

For production with eval infrastructure (Alembic, PostgreSQL):

```bash
uv pip install "atman[eval]"
```

## Docker Services

PostgreSQL is run via Docker Compose (optional — only needed when `ATMAN_MEMORY_BACKEND=postgres`):

```bash
# Start PostgreSQL in the background
docker compose up -d postgres

# Check status
docker compose ps
```

The `docker-compose.yml` in the repository root contains a `postgres` service with defaults from `.env`.

Apply schema migrations:

```bash
# Requires atman[eval]
uv run alembic upgrade head
```

## Configuring the LLM

Atman works with any OpenAI-compatible LLM endpoint.

### Option A: llama-server (llama.cpp)

```bash
llama-server \
  --model /path/to/gemma3-27b-it-qat.gguf \
  --port 8081 \
  --ctx-size 8192
```

Set the environment variables:

```bash
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_MODEL=gemma3:27b-it-qat
```

### Option B: Ollama

```bash
ollama serve
ollama pull gemma3:27b
```

Set the environment variables:

```bash
ATMAN_LLM_BASE_URL=http://localhost:11434/v1
ATMAN_LLM_MODEL=gemma3:27b
```

For embeddings via Ollama:

```bash
ollama pull bge-m3
EMBEDDING_BACKEND=ollama
EMBEDDING_OLLAMA_HOST=http://localhost:11434
```

## Configuration

Copy the environment template:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Required
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_MODEL=gemma3:27b-it-qat

# Memory backend (default: file — no PostgreSQL needed)
ATMAN_MEMORY_BACKEND=file

# Embedding backend (default: ollama)
EMBEDDING_BACKEND=ollama
EMBEDDING_OLLAMA_HOST=http://localhost:11434
```

The full list of variables with descriptions is in `.env.example`.

## First Run

Verify the installation:

```bash
atman --help
```

Start the factual memory REPL:

```bash
atman
```

Run a reflection manually:

```bash
python -m atman.cli_reflection reflect micro --agent-id <uuid>
```

Run demos:

```bash
make demo-factual
make demo-experience
```

## Health Check

Run the tests:

```bash
uv run pytest tests/ -v
```

Run code checks:

```bash
make check
```

Verify LLM connectivity:

```bash
curl http://localhost:8081/v1/models
```

Verify Ollama connectivity:

```bash
curl http://localhost:11434/api/tags
```
