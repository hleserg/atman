"""
Ollama implementation of ReflectionModel.

Uses Ollama's local LLM API for structured generation during reflection.
"""

import json
import os
from typing import Any, TypeVar

import httpx
import pydantic

from atman.adapters.reflection.exceptions import OllamaReflectionError
from atman.core.models.experience import SessionExperience
from atman.core.models.identity import Identity
from atman.core.models.narrative import NarrativeDocument
from atman.core.models.reflection import (
    HealthCriterionOutput,
    JahodaCriterion,
    NarrativeUpdateOutput,
    PatternDetectionOutput,
    ReflectionLevel,
    ReframingNoteOutput,
)
from atman.core.ports.reflection import ReflectionModel

T = TypeVar("T", bound=pydantic.BaseModel)


class OllamaReflectionModel(ReflectionModel):
    """
    Ollama-backed implementation of ReflectionModel.

    Reads configuration from environment:
    - ATMAN_OLLAMA_BASE_URL (default: http://localhost:11434)
    - ATMAN_OLLAMA_MODEL (default: qwen3.5:9b)
    """

    def __init__(self) -> None:
        """
        Initialize OllamaReflectionModel with configuration from environment.
        """
        self.base_url = os.getenv("ATMAN_OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("ATMAN_OLLAMA_MODEL", "qwen3.5:9b")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=60.0,
        )

    async def _call_with_retry(
        self,
        messages: list[dict[str, str]],
        output_model: type[T],
    ) -> T:
        """
        Call Ollama API with retry on parsing failures.

        Args:
            messages: List of message dicts with "role" and "content"
            output_model: Pydantic model to parse response into

        Returns:
            Parsed structured output

        Raises:
            OllamaReflectionError: After 2 failed attempts
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0,
                "seed": 42,
            },
        }

        attempts = 0
        last_raw = ""

        for attempt in range(2):
            attempts = attempt + 1
            try:
                response = await self._client.post("/api/chat", json=payload)
                response.raise_for_status()
                response_json = response.json()

                message_content = response_json.get("message", {}).get("content", "")
                last_raw = message_content

                parsed_json = json.loads(message_content)
                return output_model.model_validate(parsed_json)
            except (json.JSONDecodeError, pydantic.ValidationError):
                if attempt == 1:
                    raise OllamaReflectionError(attempts=attempts, last_raw=last_raw) from None
                continue

        raise OllamaReflectionError(attempts=attempts, last_raw=last_raw)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaReflectionModel":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    def generate_reframing_note(
        self,
        experience: SessionExperience,
        context: dict[str, str],
    ) -> ReframingNoteOutput:
        """
        Generate a reframing note for an experience.

        NOT IMPLEMENTED: This is part of E21.2.
        """
        raise NotImplementedError("E21.2: reflection methods")

    def detect_pattern(
        self,
        experiences: list[SessionExperience],
        context: dict[str, str],
    ) -> PatternDetectionOutput:
        """
        Detect and describe a pattern across experiences.

        NOT IMPLEMENTED: This is part of E21.2.
        """
        raise NotImplementedError("E21.2: reflection methods")

    def propose_narrative_update(
        self,
        current_narrative: NarrativeDocument,
        recent_experiences: list[SessionExperience],
        reflection_level: ReflectionLevel,
    ) -> NarrativeUpdateOutput:
        """
        Propose an update to the narrative.

        NOT IMPLEMENTED: This is part of E21.2.
        """
        raise NotImplementedError("E21.2: reflection methods")

    def assess_health_criterion(
        self,
        identity: Identity,
        experiences: list[SessionExperience],
        criterion: JahodaCriterion,
    ) -> HealthCriterionOutput:
        """
        Assess one Jahoda health criterion.

        NOT IMPLEMENTED: This is part of E21.2.
        """
        raise NotImplementedError("E21.2: reflection methods")
