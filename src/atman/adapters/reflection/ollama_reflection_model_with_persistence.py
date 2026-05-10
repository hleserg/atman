"""
Ollama reflection model with automatic persistence to ReflectionStore.

This adapter wraps OllamaReflectionModel and automatically persists
generated reflection content to the PostgreSQL ReflectionStore.
"""

import contextlib
import warnings
from typing import Any
from uuid import UUID

from atman.adapters.reflection.ollama_reflection_model import OllamaReflectionModel
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
from atman.reflection.models import ReflectionEvent as PersistenceReflectionEvent
from atman.reflection.models import ReflectionLevel as PersistenceReflectionLevel
from atman.reflection.store import ReflectionStore


class OllamaReflectionModelWithPersistence(ReflectionModel):
    """
    Ollama-backed reflection model with automatic persistence.

    This wraps OllamaReflectionModel and automatically persists generated
    reflection content to the PostgreSQL ReflectionStore. The persistence
    layer is optional - if the database is not available, it falls back
    to the base behavior without persistence.

    Usage:
        with OllamaReflectionModelWithPersistence() as model:
            output = model.generate_reframing_note(experience, context)
            # Reflection is automatically persisted to database
    """

    def __init__(
        self,
        base_model: OllamaReflectionModel | None = None,
        reflection_store: ReflectionStore | None = None,
    ) -> None:
        """
        Initialize with optional base model and reflection store.

        Args:
            base_model: OllamaReflectionModel instance. If None, creates a new one.
            reflection_store: ReflectionStore instance. If None, creates a new one.
        """
        self.base_model = base_model or OllamaReflectionModel()
        self.reflection_store = reflection_store
        self._persistence_enabled = True

        # Try to initialize reflection store, disable persistence if it fails
        if self.reflection_store is None:
            try:
                self.reflection_store = ReflectionStore()
            except ImportError:
                # psycopg not available, disable persistence
                self._persistence_enabled = False
                self.reflection_store = None

    def _persist_reflection(
        self,
        agent_id: UUID,
        level: ReflectionLevel,
        content: str,
        summary: str | None = None,
        experience_refs: list[UUID] | None = None,
        reframing_note_ids: list[UUID] | None = None,
        session_id: UUID | None = None,
        period_start: Any = None,
        period_end: Any = None,
    ) -> None:
        """
        Persist reflection to database if persistence is enabled.

        Args:
            agent_id: Agent UUID
            level: Reflection level
            content: Reflection content
            summary: Optional summary
            experience_refs: List of experience IDs analyzed
            reframing_note_ids: List of reframing note IDs produced
            session_id: Session ID for micro reflections
            period_start: Start time for daily/deep reflections
            period_end: End time for daily/deep reflections
        """
        if not self._persistence_enabled or self.reflection_store is None:
            return

        # The persistence module owns its own ``ReflectionLevel`` mirror of
        # the domain enum (the StrEnum values are kept identical between
        # ``atman.core.models.reflection`` and ``atman.reflection.models``).
        # Convert at the boundary so Pyright sees a single concrete type.
        event = PersistenceReflectionEvent(
            agent_id=agent_id,
            level=PersistenceReflectionLevel(level.value),
            content=content,
            summary=summary,
            experience_refs=experience_refs or [],
            reframing_note_ids=reframing_note_ids or [],
            session_id=session_id,
            period_start=period_start,
            period_end=period_end,
            model_provider="ollama",
            model_name=self.base_model.model,
        )
        try:
            self.reflection_store.add(event)
        except Exception as exc:
            # Persistence is best-effort: a database outage must not break the
            # reflection pipeline, but the error must still be visible.
            warnings.warn(
                f"ReflectionStore persistence failed: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    def close(self) -> None:
        """Close resources, ensuring both layers are released."""
        try:
            self.base_model.close()
        finally:
            if self.reflection_store is not None:
                self.reflection_store.close()

    def __enter__(self) -> "OllamaReflectionModelWithPersistence":
        """Context manager entry that rolls back if either layer fails to open."""
        self.base_model.__enter__()
        if self.reflection_store is not None:
            try:
                self.reflection_store.connect()
            except Exception:
                # Roll back the base model so its httpx client is not leaked
                # if the reflection store cannot be opened.
                self.base_model.__exit__(None, None, None)
                raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit that always closes both layers."""
        try:
            self.base_model.__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self.reflection_store is not None:
                self.reflection_store.close()

    def generate_reframing_note(
        self,
        experience: SessionExperience,
        context: dict[str, str],
    ) -> ReframingNoteOutput:
        """
        Generate a reframing note and persist it.

        Args:
            experience: Experience to analyze
            context: Additional context

        Returns:
            ReframingNoteOutput with the generated note
        """
        output = self.base_model.generate_reframing_note(experience, context)

        if output.reflection:
            agent_id = context.get("agent_id")
            if agent_id:
                try:
                    agent_uuid = UUID(agent_id)
                    self._persist_reflection(
                        agent_id=agent_uuid,
                        level=ReflectionLevel.MICRO,
                        content=output.reflection,
                        summary=f"Reframing note for experience {experience.id}",
                        experience_refs=[experience.id],
                        session_id=experience.session_id,
                    )
                except (ValueError, TypeError):
                    pass

        return output

    def detect_pattern(
        self,
        experiences: list[SessionExperience],
        context: dict[str, str],
    ) -> PatternDetectionOutput:
        """
        Detect a pattern and persist it.

        Args:
            experiences: Experiences to analyze
            context: Additional context

        Returns:
            PatternDetectionOutput with the detected pattern
        """
        output = self.base_model.detect_pattern(experiences, context)

        if output.description:
            agent_id = context.get("agent_id")
            if agent_id:
                try:
                    agent_uuid = UUID(agent_id)
                    self._persist_reflection(
                        agent_id=agent_uuid,
                        level=ReflectionLevel.DAILY,
                        content=output.description,
                        summary=output.description[:100]
                        if len(output.description) > 100
                        else output.description,
                        experience_refs=[e.id for e in experiences],
                    )
                except (ValueError, TypeError):
                    pass

        return output

    def propose_narrative_update(
        self,
        current_narrative: NarrativeDocument,
        recent_experiences: list[SessionExperience],
        reflection_level: ReflectionLevel,
    ) -> NarrativeUpdateOutput:
        """
        Propose a narrative update and persist it.

        Args:
            current_narrative: Current narrative document
            recent_experiences: Recent experiences to consider
            reflection_level: Level of this reflection

        Returns:
            NarrativeUpdateOutput with the proposed update
        """
        output = self.base_model.propose_narrative_update(
            current_narrative, recent_experiences, reflection_level
        )

        if output.body and current_narrative.identity_id is not None:
            # NOTE: ``NarrativeDocument`` carries ``identity_id``; the
            # PostgreSQL schema treats ``agents.id`` and ``identity.id`` as
            # potentially distinct, but the file-based stores enforce
            # ``identity.id == agent_id``.  We persist using ``identity_id``
            # as the agent identifier; in PostgreSQL deployments the
            # caller is expected to ensure these UUIDs are aligned (or
            # the FK violation will be swallowed by ``_persist_reflection``
            # and logged).
            with contextlib.suppress(ValueError, TypeError):
                self._persist_reflection(
                    agent_id=current_narrative.identity_id,
                    level=reflection_level,
                    content=output.body,
                    summary="Narrative update proposal",
                    experience_refs=[e.id for e in recent_experiences],
                )

        return output

    def assess_health_criterion(
        self,
        identity: Identity,
        experiences: list[SessionExperience],
        criterion: JahodaCriterion,
    ) -> HealthCriterionOutput:
        """
        Assess a health criterion and persist it.

        Args:
            identity: Current identity
            experiences: Experiences to consider
            criterion: Criterion to assess

        Returns:
            HealthCriterionOutput with the assessment
        """
        output = self.base_model.assess_health_criterion(identity, experiences, criterion)

        # Persist health assessment as a reflection.  See the note in
        # ``propose_narrative_update`` about ``identity.id`` vs
        # ``agents.id``: file-based stores keep them aligned, the
        # PostgreSQL schema may not.
        with contextlib.suppress(ValueError, TypeError):
            content = f"Health assessment for {criterion.value}: score={output.score}"
            if output.evidence:
                content += f"\nEvidence: {', '.join(output.evidence)}"
            if output.concerns:
                content += f"\nConcerns: {', '.join(output.concerns)}"

            self._persist_reflection(
                agent_id=identity.id,
                level=ReflectionLevel.DEEP,
                content=content,
                summary=f"Health assessment: {criterion.value}",
                experience_refs=[e.id for e in experiences],
            )

        return output
