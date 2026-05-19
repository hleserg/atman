# Observability (Sentry)

Single-entrypoint Sentry integration for Atman. Controls telemetry via
`ATMAN_OBS_LEVEL` with four levels: `off`, `minimal`, `debug`, `verbose`.

## Scope

- **In scope:** `src/atman/observability/` — `init_observability()`, sampling,
  PII scrubbing, span helpers (`ai_chat_span`, `memory_span`, `db_span`, etc.).
- **Backwards-compat bridge:** `src/atman/adapters/observability/sentry.py` —
  legacy `init_sentry_from_env()` delegates to `init_observability()`.
- **Out of scope:** application-level span placement (covered by P2.x tasks),
  Sentry Alert rules, release tracking.

## Quick reference

| Level | Trace sampling | Profiling | Spotlight |
|-------|---------------|-----------|-----------|
| `off` | none | none | off |
| `minimal` | 10 % + AI at 100 % | off | off |
| `debug` | 100 % | 10 % | on |
| `verbose` | 100 % | 100 % | on |

See [`levels.md`](levels.md) for the full level matrix, PII denylist, and
quick-start setup instructions.

## Instrumentation scanner

`tools/check_instrumentation.py` scans `src/atman/{handlers,adapters,agents,engines}/`
for async functions without a span helper. Functions exempt from the requirement
are listed in `.sentry-instrumentation-allowlist`; rationale is in
[`instrumentation-allowlist-rationale.md`](instrumentation-allowlist-rationale.md).
