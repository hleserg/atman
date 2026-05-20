"""Standalone DTOs for the Atman linguistic demo.

Vendored from `src/atman/core/ports/linguistic.py`, `entity_relations.py`
and `core/models/entity.py` to keep the HuggingFace Space free of the
full `atman` package (which pulls psycopg, textual, pydantic-ai-slim, etc).

Keep field shapes in sync with the originals — this is presentation-only
code and the upstream models are the source of truth.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EntityType(StrEnum):
    person = "person"
    place = "place"
    organization = "organization"
    object = "object"
    topic = "topic"
    event = "event"
    tool = "tool"
    health_condition = "health_condition"
    skill = "skill"
    core_value = "value"
    principle = "principle"


class AmbientAnchor(BaseModel):
    model_config = ConfigDict(frozen=True)

    anchor_type: str
    text: str
    entity_type: EntityType | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    span: tuple[int, int] | None = None


class DetectedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    entity_type: EntityType
    confidence: float = Field(ge=0.0, le=1.0)
    span: tuple[int, int] | None = None


class RawSpan(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    span: tuple[int, int] | None = None


class UserMessageAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    entities: list[DetectedEntity] = []
    anchors: list[AmbientAnchor] = []
    detected_language: str = "ru"


class AgentMessageAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_entities: list[DetectedEntity] = []
    thinking_entities: list[DetectedEntity] = []
    cognitive_load_high: bool = False
    detected_language: str = "ru"
    message_spans: list[RawSpan] = []
    stance: str | None = None
    cognitive_mode: str | None = None
    self_orientation: str | None = None
    primary_emotion: str | None = None
    cognitive_load_label: str | None = None
    divergence_signals: list[str] = []
    boundary_markers: list[str] = []
    trust_signals: list[str] = []


class KeyMomentAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: list[DetectedEntity] = []
    topic_labels: list[str] = []
    cognitive_load: float = Field(default=0.0, ge=0.0, le=1.0)
    boundary_event: bool = False
    trust_signal: str | None = None
    principle_invocations: list[str] = []
    marker_spans: list[RawSpan] = []
    agency_level: str | None = None
    confidence_in_self: str | None = None
    trust_signal_category: str | None = None
    boundary_event_category: str | None = None
    connection_quality: str | None = None
    learning_signal: str | None = None
    growth_indicator: str | None = None


class ExtractedRelation(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: DetectedEntity
    object: DetectedEntity
    relation_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    learned_by: str = "mrebel"
