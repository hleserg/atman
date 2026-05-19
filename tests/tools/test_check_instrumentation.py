"""Tests for tools/check_instrumentation.py — HLE-259 P3.1 acceptance criteria."""

from __future__ import annotations

# Add tools/ to path for import
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

import ast

from check_instrumentation import (
    INSTRUMENTATION_MARKERS,
    _load_allowlist,
    _qualified_name,
    main,
    scan_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_func(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("no function found")


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# AC-2: uninstrumented function → exit 1 with error pointing at line
# ---------------------------------------------------------------------------


def test_uninstrumented_function_exit_1(tmp_path):
    f = _write_py(
        tmp_path,
        "bad.py",
        """
        def my_handler():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert len(violations) == 1
    assert violations[0][0] == f
    assert violations[0][2] == "my_handler"


def test_main_returns_1_for_violations(tmp_path):
    _write_py(
        tmp_path,
        "bad.py",
        """
        def my_handler():
            pass
    """,
    )
    rc = main([str(tmp_path)])
    assert rc == 1


# ---------------------------------------------------------------------------
# AC-3: # sentry: skip → exit 0
# ---------------------------------------------------------------------------


def test_sentry_skip_inline(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def my_handler():  # sentry: skip
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


def test_sentry_skip_file(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        # sentry: skip-file
        def my_handler():
            pass

        def another():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


# ---------------------------------------------------------------------------
# AC-4: ai_chat_span in body → exit 0
# ---------------------------------------------------------------------------


def test_ai_chat_span_in_body(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def my_handler():
            with ai_chat_span("anthropic", "claude"):
                pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


def test_memory_span_in_body(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def my_handler():
            with memory_span("recall", "facts"):
                pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


def test_db_span_in_body(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def my_handler():
            with db_span("postgresql", "SELECT"):
                pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


def test_sentry_sdk_start_span_in_body(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def my_handler():
            with sentry_sdk.start_span(op="test"):
                pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


# ---------------------------------------------------------------------------
# Decorator detection
# ---------------------------------------------------------------------------


def test_sentry_trace_decorator(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        @sentry_sdk.trace
        def my_handler():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


def test_cron_monitor_decorator(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        @sentry_sdk.crons.monitor(monitor_slug="job")
        def my_job():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


# ---------------------------------------------------------------------------
# Private functions are exempt
# ---------------------------------------------------------------------------


def test_private_function_exempt(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def _internal_helper():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


def test_allowlist_by_function_name(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        def my_handler():
            pass
    """,
    )
    violations = scan_file(f, frozenset({"my_handler"}))
    assert violations == []


def test_allowlist_ignores_indented_comments(tmp_path, monkeypatch):
    """Indented lines starting with # must be treated as comments, not entries."""
    allowlist_file = tmp_path / ".sentry-instrumentation-allowlist"
    allowlist_file.write_text("adapters.real.entry\n  # indented comment\n  # another\n")
    import check_instrumentation as ci

    monkeypatch.setattr(ci, "ALLOWLIST_FILE", allowlist_file)
    result = _load_allowlist()
    assert "# indented comment" not in result
    assert "# another" not in result
    assert "adapters.real.entry" in result


# ---------------------------------------------------------------------------
# Async functions
# ---------------------------------------------------------------------------


def test_async_uninstrumented(tmp_path):
    f = _write_py(
        tmp_path,
        "bad.py",
        """
        async def async_handler():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert len(violations) == 1
    assert violations[0][2] == "async_handler"


def test_async_instrumented(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        async def async_handler():
            with ai_chat_span("x", "y"):
                pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


# ---------------------------------------------------------------------------
# Multiple violations in one file
# ---------------------------------------------------------------------------


def test_multiple_violations(tmp_path):
    f = _write_py(
        tmp_path,
        "bad.py",
        """
        def handler_one():
            pass

        def handler_two():
            pass

        def _private():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    names = {v[2] for v in violations}
    assert names == {"handler_one", "handler_two"}


# ---------------------------------------------------------------------------
# skip-file overrides all violations
# ---------------------------------------------------------------------------


def test_skip_file_overrides_multiple(tmp_path):
    f = _write_py(
        tmp_path,
        "ok.py",
        """
        # sentry: skip-file
        def handler_one():
            pass

        def handler_two():
            pass
    """,
    )
    violations = scan_file(f, frozenset())
    assert violations == []


# ---------------------------------------------------------------------------
# INSTRUMENTATION_MARKERS completeness
# ---------------------------------------------------------------------------


def test_instrumentation_markers_include_helpers():
    for name in (
        "ai_chat_span",
        "ai_embeddings_span",
        "ai_rerank_span",
        "memory_span",
        "db_span",
        "cron_span",
    ):
        assert name in INSTRUMENTATION_MARKERS, f"{name} missing from INSTRUMENTATION_MARKERS"


# ---------------------------------------------------------------------------
# Empty dir → exit 0
# ---------------------------------------------------------------------------


def test_empty_dir_exit_0(tmp_path):
    rc = main([str(tmp_path)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Syntax error in file is warned but not crashed
# ---------------------------------------------------------------------------


def test_syntax_error_file_skipped(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def broken(:\n    pass\n")
    violations = scan_file(f, frozenset())
    assert violations == []  # skipped, not crashed


# ---------------------------------------------------------------------------
# qualified_name helper
# ---------------------------------------------------------------------------


def test_qualified_name():
    result = _qualified_name("adapters/agent/runner.py", "run")
    assert result == "adapters.agent.runner.run"
