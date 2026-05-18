-- Atman bootstrap DDL — minimum prerequisites for migrations 0001..0018.
--
-- Why minimum: an earlier version of this file mirrored deploy/atman-setup.sh
-- inline DDL (legacy `facts`, `key_moments`, `experiences`, `identity`, etc.)
-- and collided with migration 0002's modern `facts` schema (added `status`
-- column + lifecycle fields). `CREATE TABLE IF NOT EXISTS` silently skipped
-- the modern definition, then the migration's index on `status` failed.
--
-- The migration chain owns the canonical schema. Bootstrap should only
-- create what migrations reference but do not themselves create:
--   * extensions      — uuid-ossp, vector, pg_trgm
--   * public.agents   — referenced as FK target by many migrations
--   * public.sessions — referenced by 0001.public.reflections.session_id
--
-- Everything else (facts, key_moments, identity, narrative, ...) belongs
-- inside agent_N schemas (created in 0004) or in dedicated public tables
-- created by individual migrations.
--
-- Idempotent. Safe to re-run.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Agents registry ───────────────────────────────────────────────────────────
-- serial_id + description: required by migrations 0006/0007/0008/0009/0014/0018
-- (which iterate "SELECT serial_id FROM public.agents") and by
-- src/atman/agents_registry.py (INSERT ... RETURNING serial_id, ..., description).
-- The pre-existing deploy/atman-setup.sh inline DDL omitted these columns;
-- adding them here so a fresh DB satisfies both code and migrations.
CREATE TABLE IF NOT EXISTS public.agents (
    serial_id   BIGSERIAL UNIQUE NOT NULL,
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    config      JSONB NOT NULL DEFAULT '{}',
    active      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_agents_serial ON public.agents(serial_id);

-- ── Sessions (legacy public table; FK target for 0001.public.reflections) ────
-- Note: per-agent agent_N.sessions are created in 0004; the public copy here
-- exists only to satisfy 0001's FK. 0015_move + 0016_drop later reorganise
-- subjective tables into per-agent schemas.
CREATE TABLE IF NOT EXISTS public.sessions (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id             UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at             TIMESTAMPTZ,
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','completed','interrupted')),
    identity_snapshot_id UUID
);
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON public.sessions(agent_id, started_at DESC);

-- atman_app role is created by migration 0002 and per-schema grants by 0004.
-- Bootstrap intentionally does NOT pre-create atman_app to avoid duplicate
-- ownership of role lifecycle. If you need to set atman_app's password, do
-- it after migrations via:
--   ALTER USER atman_app WITH PASSWORD '...';
-- (scripts/run_migrations.py does this automatically when ATMAN_APP_PASSWORD
--  or DATABASE_URL is provided.)
