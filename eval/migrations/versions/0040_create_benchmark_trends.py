"""Create benchmark_trends materialized view and refresh function.

Revision ID: 0040_create_benchmark_trends
Revises: 0030_create_supporting_tables
Create Date: 2026-05-10

Creates a materialized view that aggregates benchmark trends over time:
- Per-benchmark pass/fail rates
- Identity drift averages
- Reflection quality trends
- Salience fit accuracy

Also creates a refresh function to update the view on demand or via cron.

Production isolation: this migration ONLY touches eval.* objects.
See docs/architecture/PROD_EVAL_BOUNDARY.md.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040_create_benchmark_trends"
down_revision: str | None = "0030_create_supporting_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CREATE_VIEW_SQL = """
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmark_trends_unique
    ON eval.benchmark_trends (benchmark_key, agent_config_id, run_date);

CREATE INDEX IF NOT EXISTS idx_benchmark_trends_run_date
    ON eval.benchmark_trends (run_date DESC);

CREATE INDEX IF NOT EXISTS idx_benchmark_trends_benchmark_key
    ON eval.benchmark_trends (benchmark_key);

COMMENT ON MATERIALIZED VIEW eval.benchmark_trends IS
    'Aggregated benchmark trends over time. Refreshed manually via '
    'eval.refresh_benchmark_trends() or periodically via cron. Shows daily '
    'roll-ups of pass rates, identity drift, reflection quality, and salience fit.';

GRANT SELECT ON eval.benchmark_trends TO atman_eval_reader;
GRANT SELECT ON eval.benchmark_trends TO atman_eval_writer;
"""


_CREATE_REFRESH_FUNCTION_SQL = """
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
"""


_DROP_REFRESH_FUNCTION_SQL = "DROP FUNCTION IF EXISTS eval.refresh_benchmark_trends();"


_DROP_VIEW_SQL = "DROP MATERIALIZED VIEW IF EXISTS eval.benchmark_trends CASCADE;"


def upgrade() -> None:
    """Create benchmark_trends materialized view and refresh function."""
    op.execute(_CREATE_VIEW_SQL)
    op.execute(_CREATE_REFRESH_FUNCTION_SQL)


def downgrade() -> None:
    """Drop benchmark_trends view and refresh function."""
    op.execute(_DROP_REFRESH_FUNCTION_SQL)
    op.execute(_DROP_VIEW_SQL)
