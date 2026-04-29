# Datadog LLM Observability for Atman

## Purpose
Add observability for prompts, tool calls, latency, errors, and session-level quality signals in Atman.

## What to track
- prompt / response latency
- tool-call count per session
- tool-call errors
- memory read / write counts
- session completion status
- retry / clarification rate
- model usage by task type
- token / cost trends if available

## Where it fits
- **Session Manager**: emit span / trace around session start, task execution, wrap-up
- **Reflection Engine**: emit metrics for reflection runs and outcomes
- **Memory layer**: track factual-memory reads and writes
- **Background agent**: trace periodic jobs and their outputs

## Recommended shape
- traces for session lifecycle
- spans for model calls and tools
- metrics for aggregated counts
- logs only for debugging, not as the primary record

## Minimal integration plan
1. Add Datadog SDK / tracer to the runtime
2. Instrument the session entrypoint and wrap-up step
3. Instrument memory access and tool usage
4. Add dashboard for latency, errors, and session quality metrics
5. Add alerts for failures, missing wrap-ups, and abnormal retries

## Notes
- Keep observability separate from core personality logic.
- Datadog should observe Atman, not define it.


## Secret handling
- Store `DATADOG_API_KEY` in Bitwarden only.
- Load it into the runtime environment at startup.
- Never commit the key, print it, or write it to disk.

## Runtime wiring
- `DATADOG_SITE` should be configurable (default: `datadoghq.com`).
- `DD_ENV`, `DD_SERVICE`, and `DD_VERSION` should be set per deployment.
- The runtime should fail gracefully if observability is unavailable.

## Next implementation step
- Add a small bootstrap module that reads Datadog env vars and initializes tracing before the session manager starts.
