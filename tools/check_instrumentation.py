#!/usr/bin/env python3
"""Sentry instrumentation scanner for Atman critical paths.

Scans src/atman/{handlers,adapters,agents,engines}/ and fails if any
top-level public function is missing Sentry instrumentation.

Usage
-----
    # scan default critical dirs
    python tools/check_instrumentation.py

    # scan specific files or directories
    python tools/check_instrumentation.py src/atman/adapters/agent/runner.py

Exit codes: 0 = all instrumented (or allowlisted), 1 = violations found.

Detection rules (any one is sufficient)
----------------------------------------
1. Decorated with @sentry_sdk.trace / @sentry_sdk.crons.monitor / @monitor
2. Body contains sentry_sdk.start_span / start_transaction call
3. Body contains call to a helper from atman.observability.spans:
   ai_chat_span, ai_embeddings_span, ai_rerank_span, memory_span, db_span,
   cron_span
4. Def line has inline comment: # sentry: skip
5. File contains: # sentry: skip-file
6. Qualified name module.func is in .sentry-instrumentation-allowlist

Private functions (starting with _) are skipped.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRITICAL_DIRS: tuple[str, ...] = (
    "handlers",
    "adapters",
    "agents",
    "engines",
)

INSTRUMENTATION_MARKERS: frozenset[str] = frozenset(
    {
        # sentry_sdk direct
        "sentry_sdk.start_span",
        "sentry_sdk.start_transaction",
        "sentry_sdk.trace",
        "sentry_sdk.crons.monitor",
        # atman helper spans
        "ai_chat_span",
        "ai_embeddings_span",
        "ai_rerank_span",
        "memory_span",
        "db_span",
        "cron_span",
        # legacy atman.adapters.observability.sentry helpers
        "session_transaction",
        "maintenance_job_span",
        "reflection_span",
        "cron_checkin",
    }
)

ALLOWLIST_FILE = Path(".sentry-instrumentation-allowlist")

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _load_allowlist() -> frozenset[str]:
    if not ALLOWLIST_FILE.exists():
        return frozenset()
    lines = ALLOWLIST_FILE.read_text().splitlines()
    return frozenset(line.strip() for line in lines if line.strip() and not line.strip().startswith("#"))


def _has_skip_file_comment(source: str) -> bool:
    return "# sentry: skip-file" in source


def _has_skip_inline(source_lines: list[str], lineno: int) -> bool:
    """Check if the def line (1-based) has # sentry: skip."""
    line = source_lines[lineno - 1] if lineno <= len(source_lines) else ""
    return "# sentry: skip" in line


def _qualified_name(module_rel: str, func_name: str) -> str:
    """Convert relative module path + function name to dotted qualified name.

    e.g. "adapters/agent/runner.py" + "run" -> "adapters.agent.runner.run"
    """
    parts = Path(module_rel).with_suffix("").parts
    return ".".join(parts) + "." + func_name


def _node_is_instrumented(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check decorators and body for instrumentation markers."""
    # Check decorators
    for dec in node.decorator_list:
        dec_str = ast.unparse(dec)
        for marker in INSTRUMENTATION_MARKERS:
            if marker in dec_str:
                return True

    # Check body for context-manager usage or direct calls
    for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
        # with ai_chat_span(...): / with sentry_sdk.start_span(...):
        if isinstance(child, ast.With):
            for item in child.items:
                call_str = ast.unparse(item.context_expr)
                for marker in INSTRUMENTATION_MARKERS:
                    if call_str.startswith(marker):
                        return True
        # direct calls inside body (e.g. sentry_sdk.start_transaction(...))
        if isinstance(child, ast.Call):
            call_str = ast.unparse(child)
            for marker in INSTRUMENTATION_MARKERS:
                if call_str.startswith(marker):
                    return True

    return False


# ---------------------------------------------------------------------------
# Per-file scanner
# ---------------------------------------------------------------------------


def scan_file(path: Path, allowlist: frozenset[str]) -> list[tuple[Path, int, str]]:
    """Return list of (file, lineno, func_name) violations."""
    source = path.read_text(encoding="utf-8")

    if _has_skip_file_comment(source):
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"WARNING: could not parse {path}: {exc}", file=sys.stderr)
        return []

    source_lines = source.splitlines()

    # Only top-level functions (direct children of Module)
    violations: list[tuple[Path, int, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        func_name: str = node.name
        if func_name.startswith("_"):
            continue  # private functions are exempt

        # inline skip
        if _has_skip_inline(source_lines, node.lineno):
            continue

        # allowlist (try both short and long forms)
        rel = str(path)
        # strip leading "src/atman/" prefix for canonical qualified name
        if "src/atman/" in rel:
            rel_stripped = rel.split("src/atman/", 1)[1]
        else:
            rel_stripped = rel
        qualified = _qualified_name(rel_stripped, func_name)
        if qualified in allowlist or func_name in allowlist:
            continue

        if _node_is_instrumented(node):
            continue

        violations.append((path, node.lineno, func_name))

    return violations


# ---------------------------------------------------------------------------
# Directory / file collection
# ---------------------------------------------------------------------------


def collect_files(paths: list[str]) -> list[Path]:
    """Expand paths to .py files under critical dirs."""
    result: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_file() and pp.suffix == ".py":
            result.append(pp)
        elif pp.is_dir():
            result.extend(sorted(pp.rglob("*.py")))
    return [f for f in result if "__pycache__" not in str(f)]


def default_scan_roots() -> list[str]:
    """Return the critical-path directories that exist under src/atman/."""
    base = Path("src/atman")
    return [str(base / d) for d in CRITICAL_DIRS if (base / d).is_dir()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    targets = argv if argv else default_scan_roots()
    files = collect_files(targets)

    if not files:
        print("check_instrumentation: no files to scan", file=sys.stderr)
        return 0

    allowlist = _load_allowlist()
    all_violations: list[tuple[Path, int, str]] = []
    for f in files:
        all_violations.extend(scan_file(f, allowlist))

    if all_violations:
        for path, lineno, name in all_violations:
            print(
                f"{path}:{lineno}: error: '{name}' is missing Sentry instrumentation "
                f"(use ai_chat_span / memory_span / db_span / @sentry_sdk.trace, "
                f"or add '# sentry: skip' with a rationale)",
                file=sys.stderr,
            )
        print(
            f"\ncheck_instrumentation: {len(all_violations)} violation(s) found.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_instrumentation: {len(files)} file(s) scanned, 0 violations.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
