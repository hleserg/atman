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

## Span helpers

All helpers live in `atman.observability.spans` and degrade gracefully when
Sentry is not initialised (no-op span returned by SDK).

| Helper | Op name | Use when |
|--------|---------|----------|
| `ai_chat_span(provider, model)` | `gen_ai.chat` | LLM chat completion |
| `ai_embeddings_span(provider, model)` | `gen_ai.embeddings` | embedding batch |
| `ai_rerank_span(provider, model, docs, top_n)` | `gen_ai.rerank` | reranking |
| `memory_span(action, namespace)` | `memory.<action>` | recall / store / reflect |
| `db_span(system, operation, collection)` | `db` | postgres / qdrant queries |
| `cron_span(monitor_slug)` | `cron` | scheduled job body |
| `pipeline_span(op, description)` | custom | any other pipeline stage |

## Instrumentation scanner

`tools/check_instrumentation.py` scans `src/atman/{handlers,adapters,agents,engines}/`
for top-level public functions without a span helper. The CI job
(`.github/workflows/sentry-instrumentation.yml`) runs in **hard-block mode** —
a missing span is a build failure, not a warning.

Functions exempt from the requirement are listed in
`.sentry-instrumentation-allowlist`; rationale is in
[`instrumentation-allowlist-rationale.md`](instrumentation-allowlist-rationale.md).

## PII data flow

Data that reaches Sentry and its safeguards:

| Data | Where sent | Safeguard |
|------|-----------|-----------|
| Agent UUID | `scope.set_user({"id": ...})` | UUID only, no name/email |
| `slog()` event keys (fact_id, agent_id, source) | Breadcrumbs | Non-personal metadata |
| Fact content (first 120 chars) | Breadcrumb field `content` | Scrubbed by `fact_content` denylist key |
| LLM model name | Span attribute | Not personal |
| Exception stack traces | Error events | `send_default_pii=False`, `EventScrubber` |

Never stored in Sentry: raw prompts, completions, embeddings, full fact text,
reflection output, identity payloads. See `atman.observability.scrubbing` for
the full denylist.
