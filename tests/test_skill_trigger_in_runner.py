"""Tests for Gap 1 — trigger_router wired into runner per-turn message loop.

Covers:
* build_skill_suggestions_section renders suggestions correctly
* Empty suggestion list → empty string (nothing injected)
* Runner calls trigger_router when skill_manager is wired
* Runner skips trigger_router when skill_manager is None (NoopSkillManager guard)
* Runner silently swallows trigger_router exceptions
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest


# ── build_skill_suggestions_section unit tests ───────────────────────────────


@dataclass
class _FakeSuggestion:
    skill_name: str
    card_text: str
    confidence: float = 0.9


def test_empty_suggestions_returns_empty_string():
    from atman.adapters.agent.instructions import build_skill_suggestions_section

    assert build_skill_suggestions_section([]) == ""


def test_single_suggestion_renders_name_and_card():
    from atman.adapters.agent.instructions import build_skill_suggestions_section

    s = _FakeSuggestion(skill_name="code-review", card_text="Reviews code for quality issues.")
    result = build_skill_suggestions_section([s])

    assert "code-review" in result
    assert "Reviews code for quality issues." in result
    assert "Релевантные навыки" in result
    assert "atman_skills_invoke" in result


def test_multiple_suggestions_all_rendered():
    from atman.adapters.agent.instructions import build_skill_suggestions_section

    suggestions = [
        _FakeSuggestion(skill_name="skill-a", card_text="Does A."),
        _FakeSuggestion(skill_name="skill-b", card_text="Does B."),
    ]
    result = build_skill_suggestions_section(suggestions)

    assert "skill-a" in result
    assert "skill-b" in result
    assert "Does A." in result
    assert "Does B." in result


def test_suggestion_missing_card_text_handled():
    from atman.adapters.agent.instructions import build_skill_suggestions_section

    @dataclass
    class _MinimalSuggestion:
        skill_name: str = "minimal"
        card_text: str = ""

    result = build_skill_suggestions_section([_MinimalSuggestion()])
    assert "minimal" in result


# ── runner integration: trigger_router is called ─────────────────────────────


class _RecordingSkillManager:
    """Minimal skill manager stub that records trigger_router calls."""

    def __init__(self):
        self.trigger_router_calls: list[str] = []
        self._suggestions: list = []

    def set_suggestions(self, suggestions: list):
        self._suggestions = suggestions

    def trigger_router(self, message: str, agent_id, session_id) -> list:
        self.trigger_router_calls.append(message)
        return self._suggestions

    def collect_behavioral_hints_from_message(self, message, agent_id, session_id) -> None:
        return

    def list_pinned(self, agent_id):
        return []

    def list_available(self, agent_id, session_id):
        return []


def test_trigger_router_called_per_turn_when_skill_manager_wired():
    """Runner must call trigger_router when skill_manager is not None."""
    from atman.adapters.agent.runner import _call_trigger_router_if_enabled

    manager = _RecordingSkillManager()
    agent_id = uuid4()
    session_id = uuid4()

    _call_trigger_router_if_enabled("hello world", agent_id, session_id, manager)

    assert manager.trigger_router_calls == ["hello world"]


def test_trigger_router_not_called_when_skill_manager_none():
    """Runner must not call trigger_router when skill_manager is None."""
    from atman.adapters.agent.runner import _call_trigger_router_if_enabled

    result = _call_trigger_router_if_enabled("hello world", uuid4(), uuid4(), None)
    assert result == []


def test_trigger_router_exception_is_swallowed():
    """A failing trigger_router must not crash the turn."""
    from atman.adapters.agent.runner import _call_trigger_router_if_enabled

    class _BrokenManager(_RecordingSkillManager):
        def trigger_router(self, message, agent_id, session_id):
            raise RuntimeError("router crashed")

    result = _call_trigger_router_if_enabled("test", uuid4(), uuid4(), _BrokenManager())
    assert result == []


def test_suggestions_returned_to_caller():
    """trigger_router return value is passed back so runner can inject it."""
    from atman.adapters.agent.runner import _call_trigger_router_if_enabled

    manager = _RecordingSkillManager()
    expected = [_FakeSuggestion(skill_name="x", card_text="y")]
    manager.set_suggestions(expected)

    result = _call_trigger_router_if_enabled("anything", uuid4(), uuid4(), manager)
    assert result is expected
