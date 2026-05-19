"""Tests for NoopSkillManager — safe behaviour when skills are disabled."""

from __future__ import annotations

from uuid import uuid4

import pytest

from atman.core.ports.skill_manager import SkillManagerPort
from atman.skills.noop import NoopSkillManager, SkillsDisabledError


def test_noop_satisfies_protocol():
    noop = NoopSkillManager()
    assert isinstance(noop, SkillManagerPort)


def test_list_pinned_returns_empty():
    noop = NoopSkillManager()
    assert noop.list_pinned(uuid4()) == []


def test_list_available_returns_empty():
    noop = NoopSkillManager()
    assert noop.list_available(uuid4(), uuid4()) == []


def test_trigger_router_returns_empty():
    noop = NoopSkillManager()
    assert noop.trigger_router("some message", uuid4(), uuid4()) == []


def test_get_skill_returns_none():
    noop = NoopSkillManager()
    assert noop.get_skill(uuid4(), "any-name") is None


def test_invoke_raises():
    noop = NoopSkillManager()
    with pytest.raises(SkillsDisabledError):
        noop.invoke(uuid4(), {}, uuid4(), uuid4())


def test_mark_result_raises():
    noop = NoopSkillManager()
    with pytest.raises(SkillsDisabledError):
        noop.mark_result(uuid4(), "helped")


def test_capture_raises():
    noop = NoopSkillManager()
    with pytest.raises(SkillsDisabledError):
        noop.capture("my-skill", "description", uuid4(), uuid4())


def test_process_session_skills_silent_noop():
    noop = NoopSkillManager()
    # Must not raise even without any setup
    noop.process_session_skills(uuid4(), uuid4())
