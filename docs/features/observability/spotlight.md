# Spotlight — local dev observability UI

Spotlight is a local browser UI that receives Sentry envelopes and shows traces,
errors, and spans without sending anything to the Sentry SaaS cloud.
It runs in parallel with a real DSN: both targets receive data.

## Quick start

```bash
# Terminal 1 — start Spotlight
make spotlight          # opens http://localhost:8969

# Terminal 2 — run Atman with debug-level tracing
ATMAN_OBS_LEVEL=debug SENTRY_DSN=http://fake@localhost/1 uvicorn atman.app:app
```

Hit any endpoint, then open <http://localhost:8969> to see the trace waterfall.

> `ATMAN_OBS_LEVEL=debug` sets `spotlight=True` in `sentry_sdk.init()`.
> The SDK forwards every envelope to the Spotlight sidecar automatically.

## Setup paths

### 1. Native Linux / macOS

No extra config needed. `make spotlight` starts the sidecar; the SDK connects to
`http://localhost:8969/stream` by default.

### 2. WSL2

WSL2 forwards `localhost` to the Windows host automatically since Windows 10 21H2.
`make spotlight` works as-is. If you run Atman inside WSL2 and Spotlight inside
Windows (or vice-versa), set:

```bash
export SENTRY_SPOTLIGHT=http://$(hostname).local:8969/stream
```

### 3. Docker Compose

The Atman container cannot reach `localhost:8969` of the host directly.
Use `host.docker.internal` and the Linux host-gateway:

```yaml
# docker-compose.yml — atman service
services:
  atman:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      ATMAN_OBS_LEVEL: debug
      SENTRY_DSN: "http://fake@localhost/1"
      SENTRY_SPOTLIGHT: "http://host.docker.internal:8969/stream"
```

Start Spotlight on the host (`make spotlight`), then `docker compose up`.

### 4. Standalone Electron app

Download the desktop app from <https://spotlightjs.com> — no Node.js required.
Launch it before starting Atman; it listens on port 8969 automatically.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ATMAN_OBS_LEVEL` | `minimal` | Set to `debug` or `verbose` to enable Spotlight forwarding |
| `SENTRY_SPOTLIGHT` | `http://localhost:8969/stream` | Override Spotlight sidecar URL (Docker / WSL2) |
| `SENTRY_DSN` | _(unset)_ | Can be a fake DSN (`http://fake@localhost/1`) to enable tracing locally |

`SENTRY_SPOTLIGHT` is read by the sentry-sdk directly — no Atman-specific code needed.

## Relationship to `init_observability()`

`spotlight=True` is automatically set for `debug` and `verbose` levels in
`src/atman/observability/sentry_init.py`. The `minimal` level (production default)
does **not** enable Spotlight to avoid accidental data forwarding in prod.

## See also

- [Observability levels](levels.md) — full level matrix
- [Instrumentation guide](README.md) — span helpers and scanner
- Spotlight docs: <https://spotlightjs.com/docs/>
