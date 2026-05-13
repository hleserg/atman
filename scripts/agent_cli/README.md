# Agent CLI tooling (`scripts/agent_cli`)

Reproducible checks for the **split-layout** checkout: core `src/atman` plus `atman_agent_cli/src/atman/agent_cli`.

## Prerequisites

- **Python 3.12+**
- Repo root checked out so both paths exist:

  - `atman_agent_cli/src/atman/agent_cli/`
  - `src/atman/` (canonical core package)

### `PYTHONPATH`

These scripts prepend source roots internally (bootstrap). For invoking other entrypoints consistently with documentation order:

```bash
export PYTHONPATH="atman_agent_cli/src:src"
```

(Core `atman/__init__.py` prevents naive namespace merging; bootstrap registers `atman.agent_cli`.)

### Install extras

Once the workspace `pyproject.toml` defines **`[agent-cli]`**:

```bash
pip install -e ".[agent-cli]"
```

Until that lands in root `pyproject.toml`, install the editable core package plus optional libs you need (`textual`, `requests`, embedding/RAG stacks, etc.), or mirror the dependency list drafted in [`atman_agent_cli/src/atman/agent_cli/__init__.py`](../../atman_agent_cli/src/atman/agent_cli/__init__.py):

```bash
pip install -e ".[dev]"
```

## Scripts

| Script | Purpose |
|--------|---------|
| [`preflight.py`](preflight.py) | Layout, Python ≥3.12, `atman` + `atman.agent_cli` imports (with bootstrap), optional dependency inventory, HTTP probe to `{ATMAN_LLM_URL}/v1/models` |
| [`wait_for_llm.py`](wait_for_llm.py) | Poll until `/v1/models`, `/health`, or `/` answers |
| [`smoke_imports.py`](smoke_imports.py) | Fast import smoke + **AgentConfig** field count (no network, no dirs created) |

## Example commands (from repo root)

```bash
export PYTHONPATH=atman_agent_cli/src:src
python3 scripts/agent_cli/preflight.py --repo .
python3 scripts/agent_cli/wait_for_llm.py --llm-url http://127.0.0.1:8080
python3 scripts/agent_cli/smoke_imports.py
```

JSON diagnostics:

```bash
python3 scripts/agent_cli/preflight.py --repo . --json
```

## Operational flow

Typical developer loop → **preflight → wait\_for\_llm → launch TUI** (see [`atman_agent_cli/RUNBOOK.md`](../../atman_agent_cli/RUNBOOK.md)).
