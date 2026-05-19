# Observability levels — ATMAN_OBS_LEVEL

Atman uses a single `ATMAN_OBS_LEVEL` environment variable to control how much
Sentry telemetry is collected. Call `init_observability()` once at process
startup; it reads this variable automatically.

## Level matrix

| Level | Trace sampling | Profiling | Spotlight | debug flag | PII scrubbing |
|-------|---------------|-----------|-----------|------------|---------------|
| `off` | none | none | off | — | — |
| `minimal` | 10 % (+ AI at 100 %) | off | off | off | full |
| `debug` | 100 % | 10 % | on | off | full |
| `verbose` | 100 % | 100 % | on | on | full |

AI-related operations (`gen_ai.*` spans, `/api/agent`, `/api/chat`, `/api/memory`)
are always sampled at 100 % in all non-off levels via `_traces_sampler`.

## Level descriptions

### `off`
`init_observability()` returns immediately. `sentry_sdk` is **never imported**,
so there is truly zero overhead. Use in unit-test runs where you do not want any
Sentry-related side effects.

### `minimal` _(production default)_
Only unhandled exceptions and `logging.ERROR`+ lines reach Sentry. Traces are
sampled at 10 % to keep quota costs low. No profiling, no Spotlight. PII is
fully scrubbed by `EventScrubber(ATMAN_DENYLIST)`.

### `debug` _(development default)_
100 % trace sampling lets you see the full request waterfall in Spotlight
(`localhost:8969`). Profiling at 10 % adds flamegraph data. SDK `debug` flag
stays off to avoid noise in dev logs. Set `ATMAN_OBS_LEVEL=debug` in your
`.env` when developing locally.

### `verbose`
Everything `debug` offers, plus:
- SDK `debug=True` (prints internal Sentry SDK logs)
- `attach_stacktrace=True` on every message
- `include_local_variables=True` (captures local variable values in tracebacks)
- 100 % profiling

Use `verbose` only for deep diagnostics; local variable capture can incidentally
expose sensitive values even with `EventScrubber`, so never use in production.

## PII scrubbing

All levels except `off` apply `EventScrubber` with the following denylist
extending sentry-sdk's `DEFAULT_DENYLIST`:

```
# fact / memory content
memory_content, memory_text, fact_payload, fact_content, content_excerpt,
# reflection / identity
reflection_text, identity_payload, key_insight, user_journal,
# LLM I/O
embedding_input, rerank_documents, prompt, prompt_text, completion, response_text,
# raw payloads
embedding, vector,
# credentials
api_key, authorization
```

Set `ATMAN_SEND_PROMPTS=1` together with `debug` or `verbose` only in fully
isolated dev environments when you need to inspect raw LLM payloads.

## Quick-start

```bash
# Install dev deps with observability
pip install -e ".[dev]"

# Copy example env
cp .env.example .env
# Edit SENTRY_DSN — required even for Spotlight-only (use a local/fake DSN)

# Start Spotlight local UI
make spotlight   # runs: npx @spotlightjs/spotlight

# Run with debug telemetry
ATMAN_OBS_LEVEL=debug atman ...
```
