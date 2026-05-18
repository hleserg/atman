-- Migration 0019: add full_state JSONB to identity and narrative tables
--
-- Allows PostgresStateStore to round-trip the full Pydantic model without
-- column-mapping every nested field. Individual columns are kept for
-- searchability; full_state is the authoritative serialisation on read.
--
-- Also adds:
--   agent_N.narrative.identity_id   UUID  (links NarrativeDocument to Identity.id)
--   agent_N.narrative.finished_session_ids UUID[]  (crash-recovery marker)
--   agent_N.identity.eigenstate JSONB  (latest eigenstate blob; replaces narrative.eigenstate)
--
-- Depends on: 0004_agent_schema
-- Usage: python scripts/run_migrations.py

CREATE OR REPLACE FUNCTION public.extend_agent_schema_0019(schema_name TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    -- identity: add full_state + eigenstate blob
    EXECUTE format('ALTER TABLE %I.identity ADD COLUMN IF NOT EXISTS full_state JSONB NOT NULL DEFAULT ''{}''::jsonb', schema_name);
    EXECUTE format('ALTER TABLE %I.identity ADD COLUMN IF NOT EXISTS eigenstate JSONB NOT NULL DEFAULT ''{}''::jsonb', schema_name);

    -- narrative: add full_state + identity_id + finished_session_ids
    EXECUTE format('ALTER TABLE %I.narrative ADD COLUMN IF NOT EXISTS full_state JSONB NOT NULL DEFAULT ''{}''::jsonb', schema_name);
    EXECUTE format('ALTER TABLE %I.narrative ADD COLUMN IF NOT EXISTS identity_id UUID', schema_name);
    EXECUTE format('ALTER TABLE %I.narrative ADD COLUMN IF NOT EXISTS finished_session_ids UUID[] NOT NULL DEFAULT ''{}''', schema_name);
END;
$$;

-- Apply to all existing agent schemas
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name ~ '^agent_[0-9]+$'
    LOOP
        PERFORM public.extend_agent_schema_0019(r.schema_name);
    END LOOP;
END;
$$;

-- Redefine create_agent_schema to include 0019 for new agents
CREATE OR REPLACE FUNCTION public.create_agent_schema(
    p_agent_uuid UUID,
    p_serial_id  INT
)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    schema_name TEXT := 'agent_' || p_serial_id;
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);

    -- sessions
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.sessions (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id             UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
            started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at             TIMESTAMPTZ,
            status               TEXT NOT NULL DEFAULT 'active'
                                     CHECK (status IN ('active','completed','interrupted')),
            identity_snapshot_id UUID
        );
        CREATE INDEX IF NOT EXISTS sessions_agent_started_idx
            ON %I.sessions (agent_id, started_at DESC);
    $sql$, schema_name, schema_name);

    -- identity
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.identity (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id           UUID NOT NULL UNIQUE REFERENCES public.agents(id) ON DELETE CASCADE,
            self_description   TEXT NOT NULL DEFAULT '',
            core_values        JSONB NOT NULL DEFAULT '[]',
            habits             JSONB NOT NULL DEFAULT '[]',
            principles         JSONB NOT NULL DEFAULT '[]',
            goals              JSONB NOT NULL DEFAULT '[]',
            open_questions     JSONB NOT NULL DEFAULT '[]',
            emotional_baseline FLOAT NOT NULL DEFAULT 0.0
                                   CHECK (emotional_baseline BETWEEN -1 AND 1),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            full_state         JSONB NOT NULL DEFAULT '{}',
            eigenstate         JSONB NOT NULL DEFAULT '{}'
        );
    $sql$, schema_name);

    -- identity_snapshots
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.identity_snapshots (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id    UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
            snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            description TEXT,
            state       JSONB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS id_snapshots_agent_idx
            ON %I.identity_snapshots (agent_id, snapshot_at DESC);
        DROP TRIGGER IF EXISTS identity_snapshots_immutable ON %I.identity_snapshots;
        CREATE TRIGGER identity_snapshots_immutable
            BEFORE UPDATE ON %I.identity_snapshots
            FOR EACH ROW EXECUTE FUNCTION public.prevent_snapshot_modification();
    $sql$, schema_name, schema_name, schema_name, schema_name);

    -- narrative
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.narrative (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id             UUID NOT NULL UNIQUE REFERENCES public.agents(id) ON DELETE CASCADE,
            identity_id          UUID,
            core_layer           TEXT NOT NULL DEFAULT '',
            recent_layer         TEXT NOT NULL DEFAULT '',
            threads              JSONB NOT NULL DEFAULT '[]',
            eigenstate           JSONB NOT NULL DEFAULT '{}',
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            full_state           JSONB NOT NULL DEFAULT '{}',
            finished_session_ids UUID[] NOT NULL DEFAULT '{}'
        );
    $sql$, schema_name);

    -- key_moments and reframing_notes via extend functions (already handle IF NOT EXISTS)
    PERFORM public.extend_agent_schema_0006(schema_name);
    PERFORM public.extend_agent_schema_0007(schema_name);
    PERFORM public.extend_agent_schema_0008(schema_name);
    PERFORM public.extend_agent_schema_0009(schema_name);
    PERFORM public.extend_agent_schema_0010(schema_name);
    PERFORM public.extend_agent_schema_0015(schema_name);
    PERFORM public.repoint_reflection_entities_fk(schema_name);
    PERFORM public.extend_agent_schema_0017(schema_name);
    PERFORM public.extend_agent_schema_0018(schema_name);
    PERFORM public.extend_agent_schema_0019(schema_name);
    PERFORM public.grant_agent_schema_app_privileges(schema_name);
END;
$$;
