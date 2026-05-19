# ADR-001 — Production Isolation (eval namespace)

**Status:** Accepted
**Date:** 2026-05-19

> **Russian version:** [ADR-001-production-isolation-ru.md](ADR-001-production-isolation-ru.md)

## Context

Atman has two distinct user groups with different needs:

1. **Production users** — run agents in live environments. They install Atman to power agent memory and reflection. They do not need eval infrastructure: no Alembic, no SQLAlchemy, no eval-specific database schemas.

2. **Researchers and developers** — run evaluation suites, replay sessions, compare configurations. They need eval infrastructure that may be heavy (database migrations, large model dependencies).

Mixing these two profiles in a single install means every production deployment would carry eval dependencies. This inflates container size, increases attack surface, and creates unnecessary coupling.

## Decision

Atman uses **one repository with two install profiles** enforced at the Python packaging level:

| Profile | Command | Contents |
|---------|---------|----------|
| Production | `pip install atman` | `core/` + `adapters/` only |
| Eval | `pip install "atman[eval]"` | Core + Alembic, SQLAlchemy, PostgreSQL |
| Dev | `pip install "atman[dev]"` | Core + test and lint tools |
| All | `pip install "atman[all]"` | Everything |

**Module boundary:**

- `src/atman/core/` and `src/atman/adapters/` — production code. No imports of eval modules.
- `src/atman/eval/` — eval-only code. Isolated behind a lazy import guard in `eval/__init__.py`. Production code never imports it.

**Database boundary:**

- Production schema: `public.*` tables managed by production migrations.
- Eval schema: `public.eval.*` tables managed by `eval/migrations/` (Alembic), loaded only with `atman[eval]`.

**Import linter contract:**

A linter rule `no-core-to-optional-agent-cli` is enforced in CI. It fails the build if any module in `core/` or `adapters/` imports from `eval/`.

## Consequences

**Positive:**
- Production installs are lean. No eval dependencies in production containers.
- Eval infrastructure can evolve independently without risk to production runtime.
- Clear import boundary makes architectural violations detectable at CI time.

**Negative:**
- Two migration tracks to maintain (production + eval).
- Developers must be conscious of which profile they are working in.
- Lazy import guard adds a small amount of boilerplate in `eval/__init__.py`.

## Migration Impact

Existing code that imported eval utilities directly from non-eval modules must be refactored to use the lazy import pattern or moved into `eval/`. Any such violation is surfaced by the import linter before merging.
