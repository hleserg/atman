"""Unit tests for PostgresSalienceDecayService."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from atman.adapters.state.postgres_salience_decay import PostgresSalienceDecayService


def test_calculate_lambda_scales_by_depth_and_importance() -> None:
    store = MagicMock()
    svc = PostgresSalienceDecayService(store)

    surface = svc.calculate_lambda("surface", 0.5)
    profound = svc.calculate_lambda("profound", 0.5)
    high_importance = svc.calculate_lambda("surface", 0.9)

    assert surface > profound
    assert high_importance < surface


def test_mark_accessed_delegates_to_state_store() -> None:
    store = MagicMock()
    svc = PostgresSalienceDecayService(store)
    moment_id = uuid4()

    svc.mark_accessed(moment_id)

    store.mark_moment_accessed.assert_called_once_with(moment_id)
