-- Migration 0020: fix create_agent_schema — restore key_moments/reframing_notes inline creation
--
-- Migration 0019 accidentally removed the inline CREATE TABLE for key_moments
-- and reframing_notes from create_agent_schema, relying on extend_agent_schema_0008
-- to "handle IF NOT EXISTS". But extend_agent_schema_0008 only ALTERs those tables,
-- it never CREATEs them. This left new-agent registration broken.
--
-- Also fixes extend_agent_schema_0007: removes the stale FK
-- `reflection_entities.reflection_id REFERENCES public.reflections(id)` which
-- was dropped by migration 0016. The correct FK (to agent_N.reflections) is
-- added by repoint_reflection_entities_fk after extend_agent_schema_0015 creates
-- the per-agent reflections table.
--
-- Depends on: 0019_identity_narrative_full_state
-- Usage: python scripts/run_migrations.py

-- ── Fix extend_agent_schema_0007 (remove stale public.reflections FK) ────────

CREATE OR REPLACE FUNCTION public.extend_agent_schema_0007(schema_name TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.fact_entities (
            fact_id    UUID NOT NULL REFERENCES public.facts(id) ON DELETE CASCADE,
            entity_id  UUID NOT NULL REFERENCES %I.entities(id) ON DELETE RESTRICT,
            agent_id   UUID NOT NULL,
            role       TEXT NOT NULL
                           CHECK (role IN ('subject','object','context','mentioned')),
            confidence REAL NOT NULL DEFAULT 1.0
                           CHECK (confidence BETWEEN 0 AND 1),
            PRIMARY KEY (fact_id, entity_id, role)
        );
        CREATE INDEX IF NOT EXISTS fact_entities_entity_agent_idx
            ON %I.fact_entities (entity_id, agent_id);
    $sql$, schema_name, schema_name, schema_name);

    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.key_moment_entities (
            key_moment_id            UUID NOT NULL,
            entity_id                UUID NOT NULL REFERENCES %I.entities(id) ON DELETE RESTRICT,
            agent_id                 UUID NOT NULL,
            involvement              TEXT NOT NULL
                                         CHECK (involvement IN (
                                             'primary_subject','present','mentioned','evoked'
                                         )),
            valence_toward_entity    REAL CHECK (valence_toward_entity BETWEEN -1.0 AND 1.0),
            intensity_toward_entity  REAL CHECK (intensity_toward_entity BETWEEN 0.0 AND 1.0),
            PRIMARY KEY (key_moment_id, entity_id, involvement)
        );
    $sql$, schema_name, schema_name);

    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.entity_relations (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id             UUID NOT NULL,
            from_entity_id       UUID NOT NULL REFERENCES %I.entities(id) ON DELETE RESTRICT,
            to_entity_id         UUID NOT NULL REFERENCES %I.entities(id) ON DELETE RESTRICT,
            relation_type        TEXT NOT NULL,
            since                DATE,
            until                DATE,
            confidence           REAL NOT NULL DEFAULT 1.0
                                     CHECK (confidence BETWEEN 0 AND 1),
            learned_from_fact_id UUID,
            learned_by           TEXT NOT NULL
                                     CHECK (learned_by IN ('mrebel','rules','reflection','manual')),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (from_entity_id != to_entity_id),
            UNIQUE (from_entity_id, to_entity_id, relation_type)
        );
        CREATE INDEX IF NOT EXISTS entity_relations_from_active_idx
            ON %I.entity_relations (agent_id, from_entity_id)
            WHERE until IS NULL;
        CREATE INDEX IF NOT EXISTS entity_relations_to_active_idx
            ON %I.entity_relations (agent_id, to_entity_id)
            WHERE until IS NULL;
    $sql$, schema_name, schema_name, schema_name, schema_name, schema_name);

    -- reflection_entities: no FK on reflection_id here — public.reflections was
    -- dropped in 0016. repoint_reflection_entities_fk adds the correct FK to
    -- agent_N.reflections after extend_agent_schema_0015 creates it.
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.reflection_entities (
            reflection_id  BIGINT NOT NULL,
            entity_id      UUID NOT NULL REFERENCES %I.entities(id) ON DELETE RESTRICT,
            agent_id       UUID NOT NULL,
            role           TEXT,
            PRIMARY KEY (reflection_id, entity_id)
        );
    $sql$, schema_name, schema_name);
END;
$$;

-- ── Fix create_agent_schema (restore key_moments + reframing_notes inline) ───

CREATE OR REPLACE FUNCTION public.create_agent_schema(
    p_agent_uuid UUID,
    p_serial_id  INT
)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    schema_name TEXT := 'agent_' || p_serial_id;
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);

    -- sessions (full 0008 column set)
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.sessions (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id             UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
            started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at             TIMESTAMPTZ,
            status               TEXT NOT NULL DEFAULT 'active'
                                     CHECK (status IN ('active','completed','interrupted')),
            identity_snapshot_id UUID,
            close_reason         TEXT CHECK (close_reason IN (
                                     'timeout_sleep','menu_timeout','restart','forced','interrupted'
                                 )),
            agent_recap          TEXT,
            restart_reason       TEXT NOT NULL DEFAULT '',
            user_language        TEXT NOT NULL DEFAULT 'ru',
            overall_tone         FLOAT CHECK (overall_tone BETWEEN -1 AND 1),
            key_insight          TEXT,
            unexamined_fact_refs UUID[] NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS sessions_agent_started_idx
            ON %I.sessions (agent_id, started_at DESC);
    $sql$, schema_name, schema_name);

    -- identity (with full_state + eigenstate from 0019)
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

    -- narrative (with full_state + identity_id + finished_session_ids from 0019)
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

    -- key_moments (full column set)
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.key_moments (
            id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id                 UUID NOT NULL CONSTRAINT key_moments_session_fk REFERENCES %I.sessions(id) ON DELETE RESTRICT,
            agent_id                   UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
            what_happened              TEXT NOT NULL,
            emotional_valence          FLOAT NOT NULL CHECK (emotional_valence BETWEEN -1 AND 1),
            emotional_intensity        FLOAT NOT NULL CHECK (emotional_intensity BETWEEN 0 AND 1),
            depth                      TEXT NOT NULL CHECK (depth IN ('surface','meaningful','profound')),
            why_it_matters             TEXT,
            values_touched             TEXT[] NOT NULL DEFAULT '{}',
            principles_confirmed       TEXT[] NOT NULL DEFAULT '{}',
            principles_questioned      TEXT[] NOT NULL DEFAULT '{}',
            what_changed               TEXT,
            recorded_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            embedding                  halfvec(1024),
            salience                   REAL NOT NULL DEFAULT 1.0 CHECK (salience BETWEEN 0.0 AND 1.0),
            salience_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_accessed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            access_count               INT NOT NULL DEFAULT 0 CHECK (access_count >= 0),
            incomplete_coloring        BOOLEAN NOT NULL DEFAULT FALSE,
            recorded_by                TEXT NOT NULL DEFAULT 'session_manager',
            identity_snapshot_id       UUID,
            importance                 REAL NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0.0 AND 1.0),
            context_halo               JSONB,
            fact_refs                  UUID[] NOT NULL DEFAULT '{}',
            structured_markers         JSONB,
            structured_markers_version TEXT
        );
        CREATE INDEX IF NOT EXISTS km_agent_idx
            ON %I.key_moments (agent_id);
        CREATE INDEX IF NOT EXISTS km_agent_session_idx
            ON %I.key_moments (agent_id, session_id);
        CREATE INDEX IF NOT EXISTS km_depth_idx
            ON %I.key_moments (agent_id, depth);
        CREATE INDEX IF NOT EXISTS km_agent_salience_idx
            ON %I.key_moments (agent_id, salience DESC);
        CREATE INDEX IF NOT EXISTS km_values_idx
            ON %I.key_moments USING GIN (values_touched);
        CREATE INDEX IF NOT EXISTS km_fact_refs_gin_idx
            ON %I.key_moments USING GIN (fact_refs)
            WHERE cardinality(fact_refs) > 0;
        CREATE INDEX IF NOT EXISTS km_embedding_idx
            ON %I.key_moments USING hnsw (embedding halfvec_cosine_ops)
            WHERE embedding IS NOT NULL;
        DROP TRIGGER IF EXISTS key_moments_immutable ON %I.key_moments;
        CREATE TRIGGER key_moments_immutable
            BEFORE UPDATE ON %I.key_moments
            FOR EACH ROW EXECUTE FUNCTION public.prevent_key_moment_modification();
    $sql$,
    schema_name, schema_name,
    schema_name, schema_name, schema_name, schema_name, schema_name, schema_name, schema_name, schema_name, schema_name);

    -- reframing_notes
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS %I.reframing_notes (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            experience_id   UUID,
            session_id      UUID,
            agent_id        UUID NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
            reflection      TEXT NOT NULL,
            reflection_type TEXT NOT NULL
                                CHECK (reflection_type IN ('growth','reinterpretation','closure','insight')),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS reframing_session_idx ON %I.reframing_notes (session_id);
        DROP TRIGGER IF EXISTS reframing_notes_append_only ON %I.reframing_notes;
        CREATE TRIGGER reframing_notes_append_only
            BEFORE UPDATE ON %I.reframing_notes
            FOR EACH ROW EXECUTE FUNCTION public.prevent_reframing_modification();
    $sql$, schema_name, schema_name, schema_name, schema_name);

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
