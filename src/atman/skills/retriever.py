"""Skill trigger-router: maps user messages to relevant skill suggestions.

MVP implementation: keyword match + embedding similarity.
Future extension point: swap router with a small tool-use model (function-gemma etc.)
by returning the same list[SkillSuggestion] contract.
"""

from __future__ import annotations

from uuid import UUID

from atman.skills.models import Skill, SkillSuggestion, SuggestionStrength
from atman.skills.store import SkillStore


class SkillRetriever:
    """Suggest relevant skills for a given user message.

    Uses two signals in order:
    1. Keyword match against manifest.triggers_keywords (fast, zero-shot)
    2. Embedding cosine similarity against manifest.triggers_embedding_anchors
       (only when embedding port is provided)

    The final confidence is max(keyword_score, embedding_score).
    Skills below their individual min_confidence threshold are filtered out.
    """

    def __init__(
        self,
        store: SkillStore,
        embedding=None,  # EmbeddingPort | None
    ) -> None:
        self._store = store
        self._embedding = embedding

    def suggest(
        self,
        message: str,
        agent_id: UUID,
        session_id: UUID,
    ) -> list[SkillSuggestion]:
        """Return ranked suggestions for on-demand (non-pinned) skills."""
        _ = session_id
        candidates = self._store.list_active_on_demand(agent_id)
        if not candidates:
            return []

        message_lower = message.lower()
        results: list[SkillSuggestion] = []

        # Compute embedding once for all candidates if embedding is available
        message_embedding: list[float] | None = None
        if self._embedding is not None and candidates:
            try:
                message_embedding = self._embedding.embed(message)
            except Exception:
                message_embedding = None

        for skill in candidates:
            confidence, reason = self._score(skill, message_lower, message_embedding)
            if confidence < skill_min_confidence(skill):
                continue
            strength = (
                SuggestionStrength.strong_suggest
                if confidence >= 0.85
                else SuggestionStrength.suggest
            )
            results.append(
                SkillSuggestion(
                    skill_id=str(skill.id),
                    skill_name=skill.name,
                    card_text=_card_text(skill),
                    confidence=round(confidence, 3),
                    reason=reason,
                    strength=strength,
                )
            )

        results.sort(key=lambda s: s.confidence, reverse=True)
        return results

    def _score(
        self,
        skill: Skill,
        message_lower: str,
        message_embedding: list[float] | None,
    ) -> tuple[float, str]:
        """Return (confidence, reason) for a single skill."""
        keyword_score, keyword_reason = self._keyword_score(skill, message_lower)
        embedding_score, embedding_reason = 0.0, ""

        if message_embedding is not None:
            embedding_score, embedding_reason = self._embedding_score(skill, message_embedding)

        if keyword_score >= embedding_score:
            return keyword_score, keyword_reason
        return embedding_score, embedding_reason

    def _keyword_score(self, skill: Skill, message_lower: str) -> tuple[float, str]:
        """1.0 on substring keyword match, 0.0 otherwise.

        Uses substring search rather than word-boundary regex to handle
        inflected languages (Russian cases, German compounds, etc.) where
        the keyword stem appears as part of a longer word form.
        """
        for kw in _keywords_from_skill(skill):
            if kw.lower() in message_lower:
                return 1.0, f'matched keyword "{kw}"'
        return 0.0, ""

    def _embedding_score(self, skill: Skill, message_embedding: list[float]) -> tuple[float, str]:
        """Cosine similarity against each anchor; return max score."""
        anchors = _anchors_from_skill(skill)
        if not anchors:
            return 0.0, ""

        best_score = 0.0
        best_anchor = ""
        for anchor in anchors:
            try:
                if self._embedding is None:
                    continue
                anchor_vec = self._embedding.embed(anchor)
                sim = _cosine_similarity(message_embedding, anchor_vec)
                if sim > best_score:
                    best_score = sim
                    best_anchor = anchor
            except Exception:  # nosec B112
                continue

        if best_score > 0:
            return best_score, f"semantic similarity to anchor: {best_anchor!r}"
        return 0.0, ""


# ── helpers ───────────────────────────────────────────────────────────────────


def skill_min_confidence(skill: Skill) -> float:
    """Read min_confidence from SKILL.md if available, else fall back to 0.65."""
    try:
        from atman.skills.manifest import parse_skill_md

        manifest = parse_skill_md(skill.manifest_path)
        return manifest.min_confidence
    except Exception:
        return 0.65


def _keywords_from_skill(skill: Skill) -> list[str]:
    try:
        from atman.skills.manifest import parse_skill_md

        return parse_skill_md(skill.manifest_path).triggers_keywords
    except Exception:
        return []


def _anchors_from_skill(skill: Skill) -> list[str]:
    try:
        from atman.skills.manifest import parse_skill_md

        return parse_skill_md(skill.manifest_path).triggers_embedding_anchors
    except Exception:
        return []


def _card_text(skill: Skill) -> str:
    """First ~500 chars of SKILL.md body for context injection."""
    try:
        from atman.skills.manifest import parse_skill_md

        body = parse_skill_md(skill.manifest_path).body
        return body[:500].strip()
    except Exception:
        return skill.description_short


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
