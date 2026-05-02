"""Governance decisions for persistent narrative and identity mutations."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GovernanceMode(StrEnum):
    """
    How a mutation is allowed to proceed.

    Core narrative commits must never use AUTO — they require explicit review
    approval (see :meth:`GovernanceDecision.allows_core_narrative_commit`).
    """

    AUTO = "auto"
    REVIEW = "review"
    LOCKED = "locked"
    EXPERIMENTAL = "experimental"


class GovernanceDecision(BaseModel):
    """
    Decision record attached to governed writes.

    For :meth:`~atman.core.services.narrative_revision.NarrativeRevisionService.update_core_layer`,
    only decisions that pass :meth:`allows_core_narrative_commit` are accepted.
    """

    mode: GovernanceMode = Field(description="Governance mode for this write")
    review_approved: bool = Field(
        default=False,
        description="True when a human or trusted reviewer approved this change",
    )

    def allows_core_narrative_commit(self) -> bool:
        """Whether a core-layer narrative commit is permitted."""
        match self.mode:
            case GovernanceMode.LOCKED | GovernanceMode.AUTO:
                return False
            case GovernanceMode.REVIEW | GovernanceMode.EXPERIMENTAL:
                return self.review_approved

    model_config = ConfigDict(extra="forbid")
