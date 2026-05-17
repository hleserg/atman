"""Atman DB migration runner.

Idempotent, tracked. Applies in order:
1. `scripts/bootstrap_db.sql` (legacy DDL extracted from deploy/atman-setup.sh).
2. Every `migrations/versions/*.sql` not yet recorded in `public.schema_migrations`.

Tracking table:

    public.schema_migrations(
        version    TEXT PRIMARY KEY,   -- e.g. "0001_create_reflections_table" or "_bootstrap"
        applied_at TIMESTAMPTZ DEFAULT NOW(),
        checksum   TEXT NOT NULL       -- sha256 of the file contents at apply time
    )

Connection: uses `ATMAN_ADMIN_DATABASE_URL` from environment (admin/superuser, needed
for CREATE EXTENSION / CREATE ROLE / CROSS-SCHEMA GRANTs). After bootstrap the script
optionally runs `ALTER USER atman_app WITH PASSWORD '...'` if `ATMAN_APP_PASSWORD` is
set (otherwise leaves the password unchanged so re-runs don't accidentally rotate).

CLI:
    python scripts/run_migrations.py            # apply pending
    python scripts/run_migrations.py --dry-run  # show plan without applying
    python scripts/run_migrations.py --status   # report applied / pending
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_SQL = REPO_ROOT / "scripts" / "bootstrap_db.sql"
MIGRATIONS_DIR = REPO_ROOT / "migrations" / "versions"

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum   TEXT NOT NULL
);
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_env_from_dotenv() -> None:
    """Load `.env` from repo root if present. Tiny parser, ignores comments."""
    dotenv = REPO_ROOT / ".env"
    if not dotenv.exists():
        return
    for raw in dotenv.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # Don't overwrite explicitly set env vars
        os.environ.setdefault(k, v)


def _conn_url() -> str:
    url = os.environ.get("ATMAN_ADMIN_DATABASE_URL")
    if not url:
        sys.exit("ATMAN_ADMIN_DATABASE_URL is not set. Add it to .env or export it.")
    return url


def _redact(url: str) -> str:
    p = urlsplit(url)
    if p.password:
        netloc = f"{p.username}:***@{p.hostname}"
        if p.port:
            netloc += f":{p.port}"
        return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))
    return url


def _version_key(filename: str) -> str:
    """Strip the .sql extension. Keep the leading numeric prefix + slug as the version key."""
    return filename[: -len(".sql")] if filename.endswith(".sql") else filename


def _collect_migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        sys.exit(f"No migration files found under {MIGRATIONS_DIR}")
    # Warn on duplicate numeric prefixes so future renames don't silently reshuffle.
    by_prefix: dict[str, list[str]] = defaultdict(list)
    prefix_re = re.compile(r"^(\d+)")
    for f in files:
        m = prefix_re.match(f.name)
        if m:
            by_prefix[m.group(1)].append(f.name)
    collisions = {p: names for p, names in by_prefix.items() if len(names) > 1}
    if collisions:
        print("⚠ Duplicate migration prefixes (resolved by lexicographic order):")
        for p, names in sorted(collisions.items()):
            for n in names:
                print(f"    {p}: {n}")
    return files


def _applied_versions(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_MIGRATIONS_DDL)
        cur.execute("SELECT version, checksum FROM public.schema_migrations")
        return {v: c for v, c in cur.fetchall()}


def _apply_sql(conn: psycopg.Connection, version: str, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    checksum = _sha256(sql_path)
    with conn.cursor() as cur:
        # Open an explicit transaction so a failing migration rolls back fully.
        cur.execute(sql)
        cur.execute(
            "INSERT INTO public.schema_migrations(version, checksum) VALUES (%s, %s) "
            "ON CONFLICT (version) DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = NOW()",
            (version, checksum),
        )


def _plan(conn: psycopg.Connection) -> tuple[list[tuple[str, Path]], list[tuple[str, str]]]:
    """Return (pending, drift) — drift lists (version, reason) for applied files whose checksum changed."""
    applied = _applied_versions(conn)
    plan: list[tuple[str, Path]] = []
    drift: list[tuple[str, str]] = []

    # Bootstrap is always considered version "_bootstrap"
    boot_version = "_bootstrap"
    boot_checksum = _sha256(BOOTSTRAP_SQL)
    if boot_version in applied:
        if applied[boot_version] != boot_checksum:
            drift.append((boot_version, "checksum mismatch on bootstrap_db.sql"))
    else:
        plan.append((boot_version, BOOTSTRAP_SQL))

    for sql_path in _collect_migration_files():
        v = _version_key(sql_path.name)
        if v in applied:
            if applied[v] != _sha256(sql_path):
                drift.append((v, "checksum mismatch — file changed after apply"))
            continue
        plan.append((v, sql_path))
    return plan, drift


def _maybe_alter_atman_app_password(conn: psycopg.Connection) -> None:
    pwd = os.environ.get("ATMAN_APP_PASSWORD")
    if not pwd:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'atman_app'")
        if cur.fetchone() is None:
            return
        # ALTER USER ... PASSWORD doesn't accept a bind parameter for the
        # password literal (it must be a string literal in the SQL). psycopg's
        # Literal() quoting handles escaping safely.
        from psycopg import sql

        cur.execute(
            sql.SQL("ALTER USER atman_app WITH PASSWORD {pwd}").format(pwd=sql.Literal(pwd))
        )
    print("→ atman_app password updated from ATMAN_APP_PASSWORD")


def _atman_app_password_from_database_url() -> str | None:
    """Extract atman_app password from DATABASE_URL env (postgresql://atman_app:PWD@...)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    p = urlsplit(url)
    if p.username == "atman_app" and p.password:
        return p.password
    return None


def cmd_apply(dry_run: bool) -> int:
    url = _conn_url()
    print(f"DB: {_redact(url)}")
    print(f"Bootstrap: {BOOTSTRAP_SQL}")
    print(f"Migrations dir: {MIGRATIONS_DIR}")

    with psycopg.connect(url, autocommit=False) as conn:
        plan, drift = _plan(conn)

        if drift:
            print("\n✗ DRIFT detected — applied files have changed since first apply:")
            for v, reason in drift:
                print(f"    {v}: {reason}")
            print("Resolve manually before continuing (revert file or update schema_migrations).")
            return 2

        if not plan:
            print("\n✓ Nothing to apply — schema is up to date.")
            return 0

        print(f"\nPending ({len(plan)}):")
        for v, path in plan:
            print(f"    {v}  ←  {path.name}  ({path.stat().st_size} bytes)")

        if dry_run:
            print("\n--dry-run: not applying.")
            return 0

        for v, path in plan:
            print(f"→ applying {v}")
            try:
                _apply_sql(conn, v, path)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"✗ failed at {v}: {e}", file=sys.stderr)
                return 1
            print(f"  ok ({v})")

        # After bootstrap, ensure atman_app password matches what DATABASE_URL claims.
        # Source of truth = .env DATABASE_URL.
        if (db_pwd := _atman_app_password_from_database_url()) is not None:
            os.environ.setdefault("ATMAN_APP_PASSWORD", db_pwd)
        _maybe_alter_atman_app_password(conn)
        conn.commit()

    print("\n✓ All migrations applied.")
    return 0


def cmd_status() -> int:
    url = _conn_url()
    print(f"DB: {_redact(url)}")
    with psycopg.connect(url, autocommit=False) as conn:
        applied = _applied_versions(conn)
        plan, drift = _plan(conn)
        print(f"\nApplied ({len(applied)}):")
        for v in sorted(applied):
            print(f"    {v}")
        print(f"\nPending ({len(plan)}):")
        for v, path in plan:
            print(f"    {v}  ←  {path.name}")
        if drift:
            print(f"\nDrift ({len(drift)}):")
            for v, reason in drift:
                print(f"    {v}: {reason}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    _load_env_from_dotenv()
    parser = argparse.ArgumentParser(description="Atman DB migration runner")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without applying")
    parser.add_argument("--status", action="store_true", help="Show applied / pending and exit")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.status:
        return cmd_status()
    return cmd_apply(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
