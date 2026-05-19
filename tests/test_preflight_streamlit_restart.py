"""Preflight Streamlit restart argv builder."""

from __future__ import annotations

import sys

from atman.adapters.agent.preflight import _streamlit_restart_argv


def test_streamlit_restart_argv_includes_executable() -> None:
    argv = _streamlit_restart_argv()
    assert argv[0] == sys.executable
    assert len(argv) >= 2
