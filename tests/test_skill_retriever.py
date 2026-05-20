"""Tests for SkillRetriever — keyword match and confidence filtering."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from atman.skills.in_memory_store import InMemorySkillStore
from atman.skills.models import Skill, SkillKind, SkillOrigin, SkillStatus
from atman.skills.retriever import SkillRetriever, _cosine_similarity


def _now():
    return datetime.now(UTC)


def _make_skill_with_manifest(tmp_path: Path, agent_id, name: str, keywords: list[str]) -> Skill:
    """Create a skill and write its SKILL.md with the given keywords."""
    from atman.skills.manifest import SkillManifest, write_skill_md

    skill_root = tmp_path / name
    skill_root.mkdir()
    manifest_path = skill_root / "SKILL.md"

    manifest = SkillManifest(
        name=name,
        description=f"Does {name}.",
        triggers_keywords=keywords,
        min_confidence=0.65,
    )
    write_skill_md(manifest, manifest_path)

    now = _now()
    return Skill(
        id=uuid4(),
        agent_id=agent_id,
        entity_id=uuid4(),
        name=name,
        description=f"Does {name}.",
        version="0.1.0",
        kind=SkillKind.active,
        status=SkillStatus.active,
        origin=SkillOrigin.in_session,
        core=False,
        session_scoped=False,
        user_pinned=False,
        auto_pinned=False,
        invocations_count=0,
        success_count=0,
        failure_count=0,
        last_used_at=None,
        sessions_since_use=0,
        revision_needed=False,
        revision_priority=0,
        last_revised_at=None,
        manifest_inferred=False,
        skill_root=skill_root,
        manifest_path=manifest_path,
        created_at=now,
        updated_at=now,
    )


class TestSkillRetriever:
    def setup_method(self):
        self.agent_id = uuid4()
        self.session_id = uuid4()

    def test_keyword_match_returns_suggestion(self, tmp_path):
        store = InMemorySkillStore()
        # Use "outlet" (English) so substring match is unambiguous
        skill = _make_skill_with_manifest(
            tmp_path, self.agent_id, "outlet-control", ["розетк", "outlet"]
        )
        store.save_skill(skill)

        retriever = SkillRetriever(store=store, embedding=None)
        # "розетк" is a stem present in both "розетка" and "розетку"
        suggestions = retriever.suggest("включи розетку в спальне", self.agent_id, self.session_id)

        assert len(suggestions) == 1
        assert suggestions[0].skill_name == "outlet-control"
        assert suggestions[0].confidence == pytest.approx(1.0)
        assert "keyword" in suggestions[0].reason

    def test_no_match_returns_empty(self, tmp_path):
        store = InMemorySkillStore()
        skill = _make_skill_with_manifest(tmp_path, self.agent_id, "outlet-control", ["розетк"])
        store.save_skill(skill)

        retriever = SkillRetriever(store=store, embedding=None)
        suggestions = retriever.suggest("what is the weather today", self.agent_id, self.session_id)
        assert suggestions == []

    def test_pinned_skills_not_suggested(self, tmp_path):
        from dataclasses import replace

        store = InMemorySkillStore()
        skill = _make_skill_with_manifest(tmp_path, self.agent_id, "pinned-skill", ["розетка"])
        # make it pinned → it should be excluded from on-demand suggestions
        pinned_skill = replace(skill, auto_pinned=True)
        store.save_skill(pinned_skill)

        retriever = SkillRetriever(store=store, embedding=None)
        suggestions = retriever.suggest("включи розетку", self.agent_id, self.session_id)
        # Pinned skills are excluded from on-demand retrieval
        assert suggestions == []

    def test_keyword_case_insensitive(self, tmp_path):
        store = InMemorySkillStore()
        skill = _make_skill_with_manifest(tmp_path, self.agent_id, "my-skill", ["OUTLET"])
        store.save_skill(skill)

        retriever = SkillRetriever(store=store, embedding=None)
        suggestions = retriever.suggest("please use outlet today", self.agent_id, self.session_id)
        assert len(suggestions) == 1

    def test_multiple_skills_sorted_by_confidence(self, tmp_path):
        store = InMemorySkillStore()
        skill_a = _make_skill_with_manifest(tmp_path, self.agent_id, "skill-a", ["outlet"])
        skill_b = _make_skill_with_manifest(tmp_path, self.agent_id, "skill-b", ["outlet"])
        store.save_skill(skill_a)
        store.save_skill(skill_b)

        retriever = SkillRetriever(store=store, embedding=None)
        suggestions = retriever.suggest("turn on outlet", self.agent_id, self.session_id)
        assert len(suggestions) == 2
        # All have same confidence 1.0 from keyword match
        assert all(s.confidence == pytest.approx(1.0) for s in suggestions)

    def test_empty_store_returns_empty(self):
        store = InMemorySkillStore()
        retriever = SkillRetriever(store=store, embedding=None)
        assert retriever.suggest("any message", self.agent_id, self.session_id) == []


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)

    def test_dimension_mismatch_returns_zero(self):
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(0.0)
