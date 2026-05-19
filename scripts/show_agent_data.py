#!/usr/bin/env python3
"""Quick Rich-table view of the current agent's facts, key moments, and entities.

Usage:
    PYTHONPATH=. python3 scripts/show_agent_data.py
    make show-agent

Reads ATMAN_CURRENT_AGENT from environment (same as live_chat.py).
Connects via POSTGRES_* env vars (superuser — bypasses RLS).
"""

from __future__ import annotations

import os
import sys
from uuid import UUID

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from rich.console import Console
from rich.table import Table

console = Console(highlight=False)


def _db_url() -> str:
    user = os.getenv("POSTGRES_USER", "atman")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "atman")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _agent_serial(conn, agent_id: UUID) -> int | None:
    row = conn.execute(
        "SELECT serial_id FROM public.agents WHERE id = %s", [agent_id]
    ).fetchone()
    return int(row[0]) if row else None


def _show_key_moments(conn, schema: str, agent_id: UUID) -> None:
    import psycopg.sql as sql

    rows = conn.execute(
        sql.SQL(
            """
        SELECT id, what_happened, why_it_matters, salience, recorded_at
        FROM {}.key_moments
        WHERE agent_id = %s
        ORDER BY recorded_at DESC
        LIMIT 10
        """
        ).format(sql.Identifier(schema)),
        [agent_id],
    ).fetchall()
    t = Table(
        title="[cyan]Key Moments[/cyan] (last 10)",
        show_lines=False, box=None, padding=(0, 1),
    )
    t.add_column("ID", style="dim", width=8)
    t.add_column("What happened", width=55)
    t.add_column("Why it matters", width=35)
    t.add_column("Sal", width=5, justify="right")
    t.add_column("Recorded", width=20)
    for row in rows:
        rid, what, why, sal, recorded_at = row
        t.add_row(
            str(rid)[:8],
            (what or "")[:55],
            (why or "")[:35],
            f"{float(sal or 0):.2f}",
            str(recorded_at)[:19],
        )
    if not rows:
        t.add_row("[dim]— no records —[/dim]", "", "", "", "")
    console.print(t)


def _show_facts(conn, agent_id: UUID) -> None:
    rows = conn.execute(
        """
        SELECT id, content, confidence, created_at
        FROM public.facts
        WHERE agent_id = %s
        ORDER BY created_at DESC
        LIMIT 10
        """,
        [agent_id],
    ).fetchall()
    t = Table(
        title="[cyan]Facts[/cyan] (last 10)",
        show_lines=False, box=None, padding=(0, 1),
    )
    t.add_column("ID", style="dim", width=8)
    t.add_column("Content", width=70)
    t.add_column("Conf", width=6, justify="right")
    t.add_column("Created", width=20)
    for row in rows:
        rid, content, confidence, created_at = row
        t.add_row(
            str(rid)[:8],
            (content or "")[:70],
            f"{float(confidence or 0):.2f}",
            str(created_at)[:19],
        )
    if not rows:
        t.add_row("[dim]— no records —[/dim]", "", "", "")
    console.print(t)


def _show_entities(conn, schema: str, agent_id: UUID) -> None:
    import psycopg.sql as sql

    schema_ident = sql.Identifier(schema)
    rows = conn.execute(
        sql.SQL(
            """
        SELECT e.id, e.canonical_name, e.entity_type, COUNT(fe.fact_id) AS fact_cnt, e.first_seen_at
        FROM {}.entities e
        LEFT JOIN {}.fact_entities fe ON fe.entity_id = e.id
        WHERE e.agent_id = %s
        GROUP BY e.id, e.canonical_name, e.entity_type, e.first_seen_at
        ORDER BY fact_cnt DESC, e.first_seen_at DESC
        LIMIT 20
        """
        ).format(schema_ident, schema_ident),
        [agent_id],
    ).fetchall()
    t = Table(
        title="[cyan]Entities[/cyan] (top 20 by fact links)",
        show_lines=False, box=None, padding=(0, 1),
    )
    t.add_column("ID", style="dim", width=8)
    t.add_column("Name", width=30)
    t.add_column("Type", width=18)
    t.add_column("Facts", width=6, justify="right")
    t.add_column("First seen", width=20)
    for row in rows:
        rid, name, etype, fact_cnt, first_seen = row
        t.add_row(
            str(rid)[:8],
            (name or "")[:30],
            (etype or "")[:18],
            str(fact_cnt or 0),
            str(first_seen)[:19],
        )
    if not rows:
        t.add_row("[dim]— no entities —[/dim]", "", "", "", "")
    console.print(t)


def main() -> None:
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        for line in open(env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    raw_id = os.getenv("ATMAN_CURRENT_AGENT", "").strip()
    if not raw_id:
        console.print("[red]ATMAN_CURRENT_AGENT not set[/red]")
        sys.exit(1)
    try:
        agent_id = UUID(raw_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {raw_id!r}[/red]")
        sys.exit(1)

    import psycopg

    url = _db_url()
    with psycopg.connect(url, autocommit=True) as conn:
        serial = _agent_serial(conn, agent_id)
        if serial is None:
            console.print(f"[red]Agent {agent_id} not found in public.agents[/red]")
            sys.exit(1)
        schema = f"agent_{serial}"
        console.rule(f"[cyan]Agent[/cyan] {str(agent_id)[:8]}…  schema={schema}")
        console.print()

        _show_key_moments(conn, schema, agent_id)
        console.print()
        _show_facts(conn, agent_id)
        console.print()
        _show_entities(conn, schema, agent_id)


if __name__ == "__main__":
    main()
