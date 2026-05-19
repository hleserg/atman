# Instrumentation allowlist rationale

Each function in `.sentry-instrumentation-allowlist` has a one-line reason
why it is exempt from the Sentry instrumentation requirement.

## adapters/agent/factory.*

| Function | Rationale |
|----------|-----------|
| `build_deps` | Pure DI factory — assembles objects in-memory, no I/O, no hot path |
| `build_daily_reflection_service` | Factory helper — wires together services, no I/O itself |
| `build_deep_reflection_service` | Factory helper — wires together services, no I/O itself |

## adapters/agent/instructions.*

| Function | Rationale |
|----------|-----------|
| `build_instructions` | Pure string assembly from already-retrieved data; no I/O |
| `build_memory_context` | Pure string assembly; I/O done by callers before calling this |
| `build_skill_suggestions_section` | Pure string assembly from a list of Skill objects |

## adapters/agent/memory_injection.*

| Function | Rationale |
|----------|-----------|
| `inject_memory` | Pure in-memory transformer; I/O and spans owned by callers |

## adapters/agent/pending_reviews_context.*

| Function | Rationale |
|----------|-----------|
| `format_pending_reviews_block` | Pure formatting helper; no network or disk I/O |

## adapters/agent/preflight.*

| Function | Rationale |
|----------|-----------|
| `check_nlp_packages` | Startup-only health check; not on the session hot path |
| `check_postgres` | Startup-only DB ping; not on the session hot path |
| `check_llm` | Startup-only LLM probe; not on the session hot path |
| `is_warmup_needed` | Pure file-system check at startup |
| `install_nlp` | One-shot model install at cold start |
| `start_warmup_background` | Launches a background task; span would be orphan without parent tx |
| `run_cli_preflight` | Startup orchestrator; no business-critical I/O path |
| `run_streamlit_preflight` | Startup orchestrator for Streamlit UI |

## adapters/agent/runner.*

| Function | Rationale |
|----------|-----------|
| `chat` | Will be instrumented in P2.4 (Anthropic adapter + AtmanTurn) |

## adapters/agent/tools.*

| Function | Rationale |
|----------|-----------|
| `record_key_moment` | Will be instrumented in P2.x (memory_span) |
| `log_experience` | Will be instrumented in P2.x (memory_span) |
| `restart_session` | Thin session lifecycle helper; will be instrumented in P2.x |
| `wait_session` | Thin session lifecycle helper |
| `resolve_pending_review` | Will be instrumented in P2.x |
| `request_reflection` | Will be instrumented in P2.9 (reflection cron) |

## adapters/observability/sentry.*

| Function | Rationale |
|----------|-----------|
| `is_enabled` | IS the instrumentation layer — instrumenting it would be circular |
| `init_sentry_from_env` | Observability bootstrapper; cannot depend on itself being active |
| `set_agent_scope` | Scope helper called before spans exist |
| `set_session_tag` | Scope tag helper |
| `capture_silent_exception` | Error reporter; instrumenting it would cause infinite loops |
| `metric_distribution` | Metric emitter; part of the observability layer itself |
| `metric_gauge` | Metric emitter |
| `metric_increment` | Metric emitter |
| `cron_checkin` | Cron monitor emitter |

## adapters/reflection/__init__.*

| Function | Rationale |
|----------|-----------|
| `get_reflection_model` | Pure factory returning a model instance; no I/O |

## adapters/reflection/fixture_loader.*

| Function | Rationale |
|----------|-----------|
| `reflection_fixtures_dir` | Returns a Path constant; no I/O |
| `load_reflection_session_experiences` | Test/dev fixture helper; not on production hot path |
| `load_reflection_identity` | Test/dev fixture helper |
| `anchor_session_experiences_to_utc_day_window` | Pure datetime window calculation |

## adapters/reflection/prompts.*

All prompt-builder functions are pure string assembly from already-hydrated
Python objects. They contain no network I/O, no DB calls, and no LLM calls.
The callers (reflection services) own the spans around the full reflection cycle.

## adapters/storage/_atomic_write.*

| Function | Rationale |
|----------|-----------|
| `write_atomically` | Low-level file I/O helper; will be covered by parent `db_span` in P2.8 |

## adapters/storage/reflection_persistence_helper.*

| Function | Rationale |
|----------|-----------|
| `persist_micro_reflection` | Will be instrumented in P2.9 (reflection spans) |
| `persist_daily_reflection` | Will be instrumented in P2.9 |
| `persist_deep_reflection` | Will be instrumented in P2.9 |
