"""
OpenAI-compatible implementation of ReflectionModel.

Uses any OpenAI-compatible API endpoint for structured generation during reflection.
Connection details from OpenAILLMConfig.
"""

import json
from typing import TypeVar
from uuid import UUID

import httpx
import pydantic

from atman.adapters.reflection.exceptions import OllamaReflectionError
from atman.adapters.reflection.prompts import (
    OllamaMessage,
    build_entity_merge_messages,
    build_entity_relation_messages,
    build_health_messages,
    build_narrative_messages,
    build_pattern_messages,
    build_reframing_messages,
    build_stance_formulation_messages,
)
from atman.config import OpenAILLMConfig
from atman.core.models.entity import Entity
from atman.core.models.experience import KeyMoment, SessionExperience
from atman.core.models.identity import Identity
from atman.core.models.narrative import NarrativeDocument
from atman.core.models.reflection import (
    EntityRelationFormulationOutput,
    HealthCriterionOutput,
    JahodaCriterion,
    MergeDecisionOutput,
    NarrativeUpdateOutput,
    PatternDetectionOutput,
    ReflectionLevel,
    ReframingNoteOutput,
    StanceFormulationOutput,
)
from atman.core.ports.reflection import ReflectionModel
from atman.observability.spans import ai_chat_span

T = TypeVar("T", bound=pydantic.BaseModel)


class OpenAIReflectionModel(ReflectionModel):
    """
    Generic adapter for any OpenAI-compatible endpoint.
    Connection details entirely from OpenAILLMConfig.
    """

    def __init__(self, config: OpenAILLMConfig | None = None) -> None:
        """
        Initialize OpenAIReflectionModel with configuration.

        Args:
            config: OpenAI LLM configuration. If None, uses defaults from environment.
        """
        self._config = config or OpenAILLMConfig()
        self._client = httpx.Client(
            timeout=httpx.Timeout(self._config.timeout, connect=5.0),
        )

    def _call_with_retry(
        self,
        messages: list[OllamaMessage],
        output_model: type[T],
    ) -> T:
        """
        Call OpenAI-compatible API with retry on parsing failures.

        Args:
            messages: List of message dicts with "role" and "content"
            output_model: Pydantic model to parse response into

        Returns:
            Parsed structured output

        Raises:
            OllamaReflectionError: After configured max_retries failed attempts
        """
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._config.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "seed": 42,
        }
        headers = {"Authorization": f"Bearer {self._config.api_key}"}

        last_raw = ""

        for attempt in range(self._config.max_retries):
            attempts = attempt + 1
            try:
                with ai_chat_span(
                    "openai-compat", self._config.model, op_name="reflection"
                ) as span:
                    if span is not None:
                        span.set_data("reflection.output_model", output_model.__name__)
                        span.set_data("reflection.attempt", attempt + 1)
                    response = self._client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    response_json = response.json()

                    content = response_json["choices"][0]["message"]["content"]
                    last_raw = content

                    parsed_json = json.loads(content)
                    return output_model.model_validate(parsed_json)
            except (
                json.JSONDecodeError,
                pydantic.ValidationError,
                httpx.HTTPStatusError,
                httpx.RequestError,
                KeyError,
                IndexError,
                ValueError,
            ):
                if attempt == self._config.max_retries - 1:
                    raise OllamaReflectionError(attempts=attempts, last_raw=last_raw) from None
                continue

        raise AssertionError("Unreachable: loop should exit via return or raise")

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        self._client.close()

    def __enter__(self) -> "OpenAIReflectionModel":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

    def generate_reframing_note(
        self,
        experience: SessionExperience,
        context: dict[str, str],
        *,
        key_moments_by_session: dict[UUID, list[KeyMoment]] | None = None,
    ) -> ReframingNoteOutput:
        """Generate a reframing note for an experience via OpenAI-compatible API."""
        messages = build_reframing_messages(
            experience, context, key_moments_by_session=key_moments_by_session
        )
        return self._call_with_retry(messages, ReframingNoteOutput)

    def detect_pattern(
        self,
        experiences: list[SessionExperience],
        context: dict[str, str],
        *,
        key_moments_by_session: dict[UUID, list[KeyMoment]] | None = None,
    ) -> PatternDetectionOutput:
        """Detect and describe a pattern across experiences via OpenAI-compatible API."""
        messages = build_pattern_messages(
            experiences, context, key_moments_by_session=key_moments_by_session
        )
        return self._call_with_retry(messages, PatternDetectionOutput)

    def propose_narrative_update(
        self,
        current_narrative: NarrativeDocument,
        recent_experiences: list[SessionExperience],
        reflection_level: ReflectionLevel,
        *,
        key_moments_by_session: dict[UUID, list[KeyMoment]] | None = None,
    ) -> NarrativeUpdateOutput:
        """Propose an update to the narrative via OpenAI-compatible API."""
        messages = build_narrative_messages(
            current_narrative,
            recent_experiences,
            reflection_level,
            key_moments_by_session=key_moments_by_session,
        )
        return self._call_with_retry(messages, NarrativeUpdateOutput)

    def assess_health_criterion(
        self,
        identity: Identity,
        experiences: list[SessionExperience],
        criterion: JahodaCriterion,
        *,
        key_moments_by_session: dict[UUID, list[KeyMoment]] | None = None,
    ) -> HealthCriterionOutput:
        """Assess one Jahoda health criterion via OpenAI-compatible API."""
        messages = build_health_messages(
            identity, experiences, criterion, key_moments_by_session=key_moments_by_session
        )
        return self._call_with_retry(messages, HealthCriterionOutput)

    def formulate_entity_stance(
        self,
        entity: Entity,
        moments: list[KeyMoment],
        structured_markers: dict[str, int] | None = None,
    ) -> StanceFormulationOutput:
        """Formulate entity stance via OpenAI-compatible API (R7)."""
        messages = build_stance_formulation_messages(entity, moments, structured_markers)
        return self._call_with_retry(messages, StanceFormulationOutput)

    def formulate_entity_relation(
        self,
        entity_a: Entity,
        entity_b: Entity,
        shared_moments: list[KeyMoment],
    ) -> EntityRelationFormulationOutput:
        """Formulate typed relation between two entities via OpenAI-compatible API (R9)."""
        messages = build_entity_relation_messages(entity_a, entity_b, shared_moments)
        return self._call_with_retry(messages, EntityRelationFormulationOutput)

    def decide_entity_merge(
        self,
        entity_a: Entity,
        entity_b: Entity,
        contexts_a: list[KeyMoment],
        contexts_b: list[KeyMoment],
    ) -> MergeDecisionOutput:
        """Decide whether two near-duplicate entities should merge via OpenAI-compatible API (R10)."""
        messages = build_entity_merge_messages(entity_a, entity_b, contexts_a, contexts_b)
        return self._call_with_retry(messages, MergeDecisionOutput)
