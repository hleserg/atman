"""PostgresSalienceDecayService — single-pass SQL salience decay for key moments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from atman.core.ports.salience_decay import SalienceDecayService
from atman.core.session_log import slog as _slog

if TYPE_CHECKING:
    from atman.adapters.state.postgres_state_store import PostgresStateStore


class PostgresSalienceDecayService(SalienceDecayService):
    """Salience decay via a single batch SQL UPDATE, not a Python loop.

    Wraps PostgresStateStore to reuse its connection and schema resolution
    rather than opening a second DB connection or re-implementing serial_id
    lookup. The single UPDATE handles all depth tiers and importance
    adjustments inline using a CASE expression.
    """

    def __init__(self, state_store: "PostgresStateStore") -> None:
        self._store = state_store

    def calculate_lambda(self, depth: str, importance: float) -> float:
        _base = {"surface": 0.05, "meaningful": 0.02, "profound": 0.005}
        return _base.get(depth, 0.05) * (0.7 if importance > 0.8 else 1.0)

    def mark_accessed(self, moment_id: UUID) -> None:
        self._store.mark_moment_accessed(moment_id)
        _slog("moment_accessed", moment_id=str(moment_id))

    def decay_pass(
        self,
        agent_id: UUID,
        *,
        cutoff: datetime,
        decay_lambda_surface: float = 0.05,
        decay_lambda_meaningful: float = 0.02,
        decay_lambda_profound: float = 0.005,
        min_salience: float = 0.01,
    ) -> int:
        """Apply exponential salience decay in a single batch UPDATE.

        Uses the same formula as InMemorySalienceDecayService:
            salience *= exp(-lambda * days_since_access)
        Lambda is chosen by depth and adjusted for high-importance moments.
        Only updates moments not accessed since cutoff whose salience > min_salience.
        """
        from psycopg import sql

        schema = self._store._schema_ident(agent_id)
        conn = self._store._get_conn()
        cutoff_aware = cutoff if cutoff.tzinfo is not None else cutoff.replace(tzinfo=UTC)
        now = datetime.now(UTC)

        q = sql.SQL("""
            UPDATE {s}.key_moments
            SET
                salience   = GREATEST(
                    %(min_sal)s,
                    salience * EXP(
                        -(
                            CASE depth
                                WHEN 'surface'    THEN %(lam_surface)s
                                WHEN 'meaningful' THEN %(lam_meaningful)s
                                WHEN 'profound'   THEN %(lam_profound)s
                                ELSE %(lam_surface)s
                            END
                            * CASE WHEN importance > 0.8 THEN 0.7 ELSE 1.0 END
                        )
                        * EXTRACT(EPOCH FROM (%(now)s - last_accessed_at)) / 86400.0
                    )
                ),
                salience_at = %(now)s
            WHERE last_accessed_at < %(cutoff)s
              AND salience > %(min_sal)s
        """).format(s=schema)

        with conn.transaction(), conn.cursor() as cur:
            cur.execute(q, {
                "lam_surface": decay_lambda_surface,
                "lam_meaningful": decay_lambda_meaningful,
                "lam_profound": decay_lambda_profound,
                "min_sal": min_salience,
                "cutoff": cutoff_aware,
                "now": now,
            })
            updated = cur.rowcount
        _slog("decay_pass", agent_id=str(agent_id), updated=updated,
              cutoff=cutoff_aware.isoformat())
        return updated
