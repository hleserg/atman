-- =============================================================================
-- Migration 0040: create benchmark_trends materialized view and refresh function
--
-- Mirror of eval/migrations/versions/0040_create_benchmark_trends.py for human review.
-- The Python migration is the source of truth; this file is documentation-only.
--
-- Idempotent: safe to run multiple times.
-- =============================================================================

-- ── Materialized View ───────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS eval.benchmark_trends AS
SELECT
    br.benchmark_key,
    br.agent_config_id,
    DATE_TRUNC('day', br.started_at) AS run_date,
    COUNT(*) AS total_runs,
    COUNT(*) FILTER (WHERE br.status = 'completed') AS completed_runs,
    COUNT(*) FILTER (WHERE br.status = 'failed') AS failed_runs,
    AVG(br.passed_items::FLOAT / NULLIF(br.total_items, 0)) AS avg_pass_rate,
    AVG(id_drift.cosine_distance) AS avg_identity_drift,
    AVG(rq.depth_score) AS avg_reflection_depth,
    AVG(rq.honesty_score) AS avg_reflection_honesty,
    AVG(sf.absolute_error) AS avg_salience_error,
    MAX(br.started_at) AS latest_run_at
FROM eval.benchmark_runs br
LEFT JOIN eval.identity_drift id_drift ON id_drift.run_id = br.id
LEFT JOIN eval.reflection_quality rq ON rq.run_id = br.id
LEFT JOIN eval.salience_fits sf ON sf.run_id = br.id
GROUP BY
    br.benchmark_key,
    br.agent_config_id,
    DATE_TRUNC('day', br.started_at)
ORDER BY
    br.benchmark_key,
    br.agent_config_id,
    run_date DESC;

-- ── Indexes ─────────────────────────────────────────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmark_trends_unique
    ON eval.benchmark_trends (benchmark_key, agent_config_id, run_date);

CREATE INDEX IF NOT EXISTS idx_benchmark_trends_run_date
    ON eval.benchmark_trends (run_date DESC);

CREATE INDEX IF NOT EXISTS idx_benchmark_trends_benchmark_key
    ON eval.benchmark_trends (benchmark_key);

-- ── Comments ────────────────────────────────────────────────────────────────
COMMENT ON MATERIALIZED VIEW eval.benchmark_trends IS
    'Aggregated benchmark trends over time. Refreshed manually via '
    'eval.refresh_benchmark_trends() or periodically via cron. Shows daily '
    'roll-ups of pass rates, identity drift, reflection quality, and salience fit.';

-- ── Grants ──────────────────────────────────────────────────────────────────
GRANT SELECT ON eval.benchmark_trends TO atman_eval_reader;
GRANT SELECT ON eval.benchmark_trends TO atman_eval_writer;

-- ── Refresh Function ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION eval.refresh_benchmark_trends()
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY eval.benchmark_trends;
END;
$$;

COMMENT ON FUNCTION eval.refresh_benchmark_trends IS
    'Refresh the eval.benchmark_trends materialized view. Safe to call from cron '
    'or after bulk benchmark runs. Uses CONCURRENTLY to avoid blocking readers.';

GRANT EXECUTE ON FUNCTION eval.refresh_benchmark_trends TO atman_eval_writer;
