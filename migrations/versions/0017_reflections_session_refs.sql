-- Migration 0017: reflections — rename `experience_refs` → `session_refs`
--
-- After memory architecture v3 there's no separate `experiences` table; the
-- column's values are session ids (one virtual SessionExperience per Session,
-- so the ids match by construction — see REFLECTION_FUTURE.md §3.5). The
-- column name was already a misnomer; this migration aligns the schema with
-- reality.
--
-- Idempotent and transactional per agent schema. The index over the array
-- is recreated under the new name. The migration is safe to re-run.
--
-- Depends on: migration 0015 (per-agent `reflections` tables in
--             `agent_{serial_id}` schemas).
--
-- Usage:
--   psql -d atman -f migrations/versions/0017_reflections_session_refs.sql
--
-- Rollback: rename back via ALTER TABLE / ALTER INDEX; no data is lost.

-- ── Step 1: helper that performs the rename for one schema ──────────────────

CREATE OR REPLACE FUNCTION public.extend_agent_schema_0017(schema_name TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    has_old INTEGER;
    has_new INTEGER;
BEGIN
    -- Only touch the table if it exists in this agent's schema.
    PERFORM 1 FROM information_schema.tables
        WHERE table_schema = schema_name AND table_name = 'reflections';
    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT COUNT(*) INTO has_old
    FROM information_schema.columns
    WHERE table_schema = schema_name
      AND table_name = 'reflections'
      AND column_name = 'experience_refs';

    SELECT COUNT(*) INTO has_new
    FROM information_schema.columns
    WHERE table_schema = schema_name
      AND table_name = 'reflections'
      AND column_name = 'session_refs';

    IF has_new > 0 AND has_old = 0 THEN
        -- Already migrated; nothing to do.
        RETURN;
    END IF;

    IF has_old > 0 AND has_new = 0 THEN
        -- The straightforward rename path.
        EXECUTE format(
            'ALTER TABLE %I.reflections RENAME COLUMN experience_refs TO session_refs',
            schema_name
        );
    ELSIF has_old > 0 AND has_new > 0 THEN
        -- Both present (shouldn't happen, but be defensive). Copy from the
        -- legacy column into the new one for any rows where session_refs is
        -- empty/null, then drop the old column.
        EXECUTE format($sql$
            UPDATE %I.reflections
               SET session_refs = experience_refs
             WHERE (session_refs IS NULL OR cardinality(session_refs) = 0)
               AND experience_refs IS NOT NULL
        $sql$, schema_name);
        EXECUTE format(
            'ALTER TABLE %I.reflections DROP COLUMN experience_refs',
            schema_name
        );
    END IF;

    -- Drop any leftover index over the old column and create the new one.
    EXECUTE format(
        'DROP INDEX IF EXISTS %I.reflections_experience_refs_idx',
        schema_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS reflections_session_refs_idx '
        'ON %I.reflections USING GIN (session_refs)',
        schema_name
    );

    -- Refresh table comment so the schema docs match.
    EXECUTE format($sql$
        COMMENT ON TABLE %I.reflections IS
        'Per-agent reflection storage (micro/daily/deep). session_refs holds the analyzed session ids.';
    $sql$, schema_name);
END;
$$;

-- ── Step 2: run the rename for every existing agent schema ──────────────────

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT serial_id
        FROM public.agents
        ORDER BY serial_id
    LOOP
        PERFORM public.extend_agent_schema_0017('agent_' || r.serial_id);
    END LOOP;
END;
$$;
