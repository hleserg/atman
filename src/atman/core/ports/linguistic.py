"""Port: LinguisticAnalyzer — NER and classification for messages and key moments."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from atman.core.models.entity import EntityType


class AmbientAnchor(BaseModel):
    """A salient contextual signal extracted from a user message."""

    model_config = ConfigDict(frozen=True)

    anchor_type: str = Field(
        description=("person_ref | topic | location | time_ref | action | emotion_ref")
    )
    text: str
    entity_type: EntityType | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    span: tuple[int, int] | None = Field(
        default=None,
        description="Character offsets (start, end) in the original text",
    )


class DetectedEntity(BaseModel):
    """A named entity recognised in a piece of text."""

    model_config = ConfigDict(frozen=True)

    text: str
    entity_type: EntityType
    confidence: float = Field(ge=0.0, le=1.0)
    span: tuple[int, int] | None = Field(
        default=None,
        description="Character offsets (start, end) in the original text",
    )


class RawSpan(BaseModel):
    """A labelled span that does not map to EntityType (agent-specific NER labels)."""

    model_config = ConfigDict(frozen=True)

    text: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    span: tuple[int, int] | None = None


class UserMessageAnalysis(BaseModel):
    """NER + ambient anchor extraction result for a single user message."""

    model_config = ConfigDict(frozen=True)

    text: str
    entities: list[DetectedEntity] = []
    anchors: list[AmbientAnchor] = []
    detected_language: str = "ru"


class AgentMessageAnalysis(BaseModel):
    """Linguistic analysis of an agent message, optionally against its thinking trace.

    Point A schema (§5 of design doc ATMAN_MEMORY_AND_LINGUISTIC_FINAL_v3):
    - message_spans: 13-label agent-specific NER (emotional_anchor, boundary_marker, etc.)
    - stance / cognitive_mode / self_orientation / primary_emotion / cognitive_load_label:
      MiniLM zero-shot classifications
    - divergence_signals: rule-based comparison of thinking vs message
    - boundary_markers: backward-compat list of boundary phrase strings
    """

    model_config = ConfigDict(frozen=True)

    # --- legacy fields (kept for backward compat) ---
    message_entities: list[DetectedEntity] = []
    thinking_entities: list[DetectedEntity] = []
    cognitive_load_high: bool = False
    detected_language: str = "ru"

    # --- point A NER: agent-specific labels ---
    message_spans: list[RawSpan] = Field(
        default=[],
        description="13-label agent NER: emotional_anchor, boundary_marker, etc.",
    )

    # --- point A classifications ---
    stance: str | None = Field(
        default=None,
        description="committed|tentative|resistant|exploring|doubtful|dismissive",
    )
    cognitive_mode: str | None = Field(
        default=None,
        description="analytical|emotional|mixed|defensive",
    )
    self_orientation: str | None = Field(
        default=None,
        description="toward_self|toward_other|toward_task|toward_meta",
    )
    primary_emotion: str | None = Field(
        default=None,
        description="neutral|anxious|frustrated|curious|warm|doubtful|committed|tired",
    )
    cognitive_load_label: str | None = Field(
        default=None,
        description="low|manageable|high|overwhelmed",
    )

    # --- divergence / boundary ---
    divergence_signals: list[str] = Field(
        default=[],
        description="Detected divergence markers between thinking and message",
    )
    boundary_markers: list[str] = Field(
        default=[],
        description="Principle invocations, refusals, identity expressions",
    )
    trust_signals: list[str] = Field(
        default=[],
        description="Positive or negative trust indicators",
    )


class KeyMomentAnalysis(BaseModel):
    """Linguistic analysis of a key moment's narrative fields.

    Point K schema (§5 of design doc ATMAN_MEMORY_AND_LINGUISTIC_FINAL_v3):
    - marker_spans: 4-label NER (recurring_theme, closure_marker, opening_marker,
      contradiction_marker)
    - 8 MiniLM classifications: self-state, relational, meta
    """

    model_config = ConfigDict(frozen=True)

    # --- legacy fields ---
    entities: list[DetectedEntity] = []
    topic_labels: list[str] = []
    cognitive_load: float = Field(default=0.0, ge=0.0, le=1.0)
    boundary_event: bool = False
    trust_signal: str | None = None
    principle_invocations: list[str] = []

    # --- point K NER: narrative marker labels ---
    marker_spans: list[RawSpan] = Field(
        default=[],
        description="4-label NER: recurring_theme, closure_marker, opening_marker, contradiction_marker",
    )

    # --- point K classifications: self-state ---
    agency_level: str | None = Field(
        default=None,
        description="passive|reactive|proactive|initiating",
    )
    confidence_in_self: str | None = Field(
        default=None,
        description="low|moderate|high|inflated",
    )

    # --- point K classifications: relational ---
    trust_signal_category: str | None = Field(
        default=None,
        description="building|stable|wavering|broken",
    )
    boundary_event_category: str | None = Field(
        default=None,
        description="none|respected|tested|crossed|enforced",
    )
    connection_quality: str | None = Field(
        default=None,
        description="distant|functional|warm|deep",
    )

    # --- point K classifications: meta ---
    learning_signal: str | None = Field(
        default=None,
        description="new_understanding|confirmed|rejected|confused",
    )
    growth_indicator: str | None = Field(
        default=None,
        description="regression|static|progress|breakthrough",
    )


class LinguisticAnalyzer(ABC):
    """Hexagonal port for NER and zero-shot classification over conversation text."""

    @abstractmethod
    def analyze_user_message(self, text: str) -> UserMessageAnalysis:
        """Extract entities and ambient anchors from a raw user message."""

    @abstractmethod
    def analyze_agent_message(
        self,
        message: str,
        *,
        thinking: str | None = None,
    ) -> AgentMessageAnalysis:
        """Analyse an agent's outgoing message.

        When thinking is provided, cross-reference it with the message to detect
        divergence signals (e.g. the agent hedged in thinking but stated
        confidently in message).
        """

    @abstractmethod
    def analyze_key_moment(
        self,
        what_happened: str,
        why_it_matters: str,
    ) -> KeyMomentAnalysis:
        """Analyse the two narrative fields of a KeyMoment record.

        Both fields are processed together so the analyzer can reason about
        whether the stated significance is consistent with the event description.
        """
