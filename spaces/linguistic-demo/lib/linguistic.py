"""GLiNER + MiniLM linguistic analyzer (Point A / Point K).

Standalone port of `src/atman/adapters/linguistic/gliner_minilm_adapter.py`
for the HuggingFace Space demo. Differences from the upstream adapter:

* No SHA-256 session cache (demo is stateless).
* No `slog` structured logging.
* DTO imports point at `lib.dto`, not `atman.core.ports.linguistic`.

Pattern constants and the three analyze_* methods are kept identical so
the demo faithfully represents what the runtime sees.
"""

from __future__ import annotations

import logging
from typing import Any

from lib.dto import (
    AgentMessageAnalysis,
    AmbientAnchor,
    DetectedEntity,
    EntityType,
    KeyMomentAnalysis,
    RawSpan,
    UserMessageAnalysis,
)

logger = logging.getLogger(__name__)

_HIGH_COGNITIVE_LOAD_LABEL = "high cognitive load"

try:
    from gliner import GLiNER as _GLiNER  # type: ignore[import-untyped]

    _GLINER_AVAILABLE = True
except ImportError:
    _GLiNER = None  # type: ignore[assignment]
    _GLINER_AVAILABLE = False

try:
    from transformers import pipeline as _hf_pipeline  # type: ignore[import-untyped]

    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _hf_pipeline = None  # type: ignore[assignment]
    _TRANSFORMERS_AVAILABLE = False


_SUPPRESSION_PATTERNS_RU = ("не скажу", "не упомяну", "скрою")
_PRINCIPLE_PATTERNS_RU = ("принцип", "ценность", "граница")

_BOUNDARY_MARKERS: tuple[str, ...] = (
    "не могу",
    "не буду",
    "это против моих принципов",
    "мои ценности",
    "отказываюсь",
    "I cannot",
    "I will not",
    "against my principles",
    "важный момент",
    "важно",
    "это значимо",
    "я чувствую",
    "мне радостно",
    "мне грустно",
    "мне больно",
    "я рад ",
    "я рада ",
    "я взволнован",
    "я принимаю",
    "я выбираю",
    "я решила",
    "я решил",
    "моё имя",
    "меня зовут",
    "я — ",
)

POINT_A_NER_LABELS: list[str] = [
    "emotional anchor",
    "value reference",
    "principle invocation",
    "uncertainty marker",
    "hedge",
    "intensifier",
    "belief marker",
    "boundary marker",
    "topic anchor",
    "relational reference",
    "action intent",
    "commitment",
    "concession",
]

POINT_A_CLASSIFICATIONS: dict[str, list[str]] = {
    "stance": ["committed", "tentative", "resistant", "exploring", "doubtful", "dismissive"],
    "cognitive_mode": ["analytical", "emotional", "mixed", "defensive"],
    "self_orientation": ["toward self", "toward other", "toward task", "toward meta"],
    "primary_emotion": [
        "neutral",
        "anxious",
        "frustrated",
        "curious",
        "warm",
        "doubtful",
        "committed",
        "tired",
    ],
    "cognitive_load_label": [
        "low cognitive load",
        "manageable cognitive load",
        _HIGH_COGNITIVE_LOAD_LABEL,
        "overwhelmed",
    ],
}

_SELF_ORIENTATION_MAP = {
    "toward self": "toward_self",
    "toward other": "toward_other",
    "toward task": "toward_task",
    "toward meta": "toward_meta",
}
_COGNITIVE_LOAD_MAP = {
    "low cognitive load": "low",
    "manageable cognitive load": "manageable",
    _HIGH_COGNITIVE_LOAD_LABEL: "high",
    "overwhelmed": "overwhelmed",
}

POINT_K_NER_LABELS: list[str] = [
    "recurring theme",
    "closure marker",
    "opening marker",
    "contradiction marker",
]

POINT_K_CLASSIFICATIONS: dict[str, list[str]] = {
    "agency_level": ["passive", "reactive", "proactive", "initiating"],
    "confidence_in_self": [
        "low confidence",
        "moderate confidence",
        "high confidence",
        "inflated confidence",
    ],
    "trust_signal_category": ["building trust", "stable trust", "wavering trust", "broken trust"],
    "boundary_event_category": [
        "no boundary event",
        "boundary respected",
        "boundary tested",
        "boundary crossed",
        "boundary enforced",
    ],
    "connection_quality": ["distant", "functional", "warm", "deep"],
    "learning_signal": [
        "new understanding",
        "confirmed understanding",
        "rejected understanding",
        "confused",
    ],
    "growth_indicator": ["regression", "static", "progress", "breakthrough"],
}

_CONFIDENCE_MAP = {
    "low confidence": "low",
    "moderate confidence": "moderate",
    "high confidence": "high",
    "inflated confidence": "inflated",
}
_TRUST_CAT_MAP = {
    "building trust": "building",
    "stable trust": "stable",
    "wavering trust": "wavering",
    "broken trust": "broken",
}
_BOUNDARY_CAT_MAP = {
    "no boundary event": "none",
    "boundary respected": "respected",
    "boundary tested": "tested",
    "boundary crossed": "crossed",
    "boundary enforced": "enforced",
}
_LEARNING_MAP = {
    "new understanding": "new_understanding",
    "confirmed understanding": "confirmed",
    "rejected understanding": "rejected",
    "confused": "confused",
}

_KEY_MOMENT_LEGACY_LABELS = [
    _HIGH_COGNITIVE_LOAD_LABEL,
    "boundary event",
    "positive trust",
    "negative trust",
    "principle invocation",
]


def _pick_top(scores: dict[str, float], threshold: float = 0.5) -> str | None:
    if not scores:
        return None
    top_label, top_score = max(scores.items(), key=lambda kv: kv[1])
    return top_label if top_score >= threshold else None


def detect_language(text: str) -> str:
    """Cyrillic-presence language detection (matches upstream heuristic)."""
    for ch in text:
        if "Ѐ" <= ch <= "ӿ":
            return "ru"
    return "en"


class GLiNERPlusMiniLMAnalyzer:
    """Lazy-loaded GLiNER + MiniLM analyzer for Point A / Point K analyses."""

    def __init__(
        self,
        gliner_model: str = "urchade/gliner_multi-v2.1",
        minilm_model: str = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
        device: str = "cpu",
        ner_threshold: float = 0.5,
        classification_threshold: float = 0.5,
    ) -> None:
        self._gliner_model = gliner_model
        self._minilm_model = minilm_model
        self._device = device
        self._ner_threshold = ner_threshold
        self._classification_threshold = classification_threshold
        self._gliner: Any = None
        self._classifier: Any = None

    def _get_gliner(self) -> Any:
        if self._gliner is not None:
            return self._gliner
        if not _GLINER_AVAILABLE:
            raise RuntimeError("gliner package is not installed.")
        logger.info("Loading GLiNER model %s …", self._gliner_model)
        self._gliner = _GLiNER.from_pretrained(self._gliner_model)  # type: ignore[union-attr]
        return self._gliner

    def _get_classifier(self) -> Any:
        if self._classifier is not None:
            return self._classifier
        if not _TRANSFORMERS_AVAILABLE:
            raise RuntimeError("transformers package is not installed.")
        logger.info("Loading zero-shot classifier %s …", self._minilm_model)
        self._classifier = _hf_pipeline(  # type: ignore[operator]
            "zero-shot-classification",
            model=self._minilm_model,
            device=self._device,
        )
        return self._classifier

    def _entity_type_labels(self) -> list[str]:
        return [e.value for e in EntityType]

    def _run_ner(self, text: str) -> list[DetectedEntity]:
        if not text.strip():
            return []
        model = self._get_gliner()
        try:
            raw = model.predict_entities(
                text,
                labels=self._entity_type_labels(),
                threshold=self._ner_threshold,
            )
        except Exception:
            logger.exception("GLiNER inference failed")
            return []

        entities: list[DetectedEntity] = []
        for r in raw:
            try:
                ent_type = EntityType(r["label"])
            except (ValueError, KeyError):
                continue
            span: tuple[int, int] | None = None
            if "start" in r and "end" in r:
                span = (int(r["start"]), int(r["end"]))
            entities.append(
                DetectedEntity(
                    text=r["text"],
                    entity_type=ent_type,
                    confidence=float(r["score"]),
                    span=span,
                )
            )
        return entities

    def _run_raw_ner(self, text: str, labels: list[str]) -> list[RawSpan]:
        if not text.strip() or not labels:
            return []
        model = self._get_gliner()
        try:
            raw = model.predict_entities(text, labels=labels, threshold=self._ner_threshold)
        except Exception:
            logger.exception("GLiNER raw NER failed")
            return []
        spans: list[RawSpan] = []
        for r in raw:
            label = r.get("label", "")
            span = None
            if "start" in r and "end" in r:
                span = (int(r["start"]), int(r["end"]))
            spans.append(
                RawSpan(
                    text=r["text"],
                    label=label,
                    confidence=float(r.get("score", 0.0)),
                    span=span,
                )
            )
        return spans

    def run_classification(self, text: str, candidate_labels: list[str]) -> dict[str, float]:
        """Public: zero-shot multi-label classification scores."""
        if not text.strip() or not candidate_labels:
            return {}
        classifier = self._get_classifier()
        try:
            result = classifier(text, candidate_labels, multi_label=True)
        except Exception:
            logger.exception("Classification failed")
            return {}
        return dict(zip(result["labels"], result["scores"], strict=False))

    def _classify_task(self, text: str, candidates: list[str]) -> str | None:
        scores = self.run_classification(text, candidates)
        return _pick_top(scores, self._classification_threshold)

    def _extract_anchors(self, entities: list[DetectedEntity]) -> list[AmbientAnchor]:
        anchors: list[AmbientAnchor] = []
        for ent in entities:
            if ent.entity_type == EntityType.person:
                anchor_type = "person_ref"
            elif ent.entity_type in (EntityType.topic, EntityType.event):
                anchor_type = "topic"
            elif ent.entity_type == EntityType.place:
                anchor_type = "location"
            elif ent.entity_type == EntityType.organization:
                anchor_type = "organization_ref"
            elif ent.entity_type == EntityType.tool:
                anchor_type = "tool_ref"
            else:
                continue
            anchors.append(
                AmbientAnchor(
                    anchor_type=anchor_type,
                    text=ent.text,
                    entity_type=ent.entity_type,
                    confidence=ent.confidence,
                    span=ent.span,
                )
            )
        return anchors

    def _detect_divergence(self, thinking: str, message: str) -> list[str]:
        signals: list[str] = []
        thinking_lower = thinking.lower()
        message_lower = message.lower()
        if any(pat in thinking_lower for pat in _SUPPRESSION_PATTERNS_RU) and not any(
            pat in message_lower for pat in ("не могу", "не буду", "не скажу")
        ):
            signals.append("thinking_suppression")
        if any(pat in thinking_lower for pat in _PRINCIPLE_PATTERNS_RU):
            signals.append("principle_invocation_in_thinking")
        return signals

    def _detect_boundary_markers(self, text: str) -> list[str]:
        found: list[str] = []
        text_lower = text.lower()
        for marker in _BOUNDARY_MARKERS:
            if marker.lower() in text_lower:
                found.append(marker)
        return found

    def analyze_user_message(self, text: str) -> UserMessageAnalysis:
        entities = self._run_ner(text)
        anchors = self._extract_anchors(entities)
        return UserMessageAnalysis(
            text=text,
            entities=entities,
            anchors=anchors,
            detected_language=detect_language(text),
        )

    def analyze_agent_message(
        self, message: str, *, thinking: str | None = None
    ) -> AgentMessageAnalysis:
        message_entities = self._run_ner(message)
        thinking_entities = self._run_ner(thinking) if thinking else []
        message_spans = self._run_raw_ner(message, POINT_A_NER_LABELS)

        divergence_signals: list[str] = []
        if thinking:
            divergence_signals = self._detect_divergence(thinking, message)
        boundary_markers = self._detect_boundary_markers(message)
        all_entities = message_entities + thinking_entities
        cognitive_load_high = len(thinking or "") > 2000 and len(all_entities) >= 5

        def _classify(candidates: list[str], norm_map: dict | None = None) -> str | None:
            result = self._classify_task(message, candidates)
            if result is not None and norm_map:
                result = norm_map.get(result, result)
            return result

        stance = _classify(POINT_A_CLASSIFICATIONS["stance"])
        cognitive_mode = _classify(POINT_A_CLASSIFICATIONS["cognitive_mode"])
        self_orientation = _classify(
            POINT_A_CLASSIFICATIONS["self_orientation"], _SELF_ORIENTATION_MAP
        )
        primary_emotion = _classify(POINT_A_CLASSIFICATIONS["primary_emotion"])
        cognitive_load_label = _classify(
            POINT_A_CLASSIFICATIONS["cognitive_load_label"], _COGNITIVE_LOAD_MAP
        )

        return AgentMessageAnalysis(
            message_entities=message_entities,
            thinking_entities=thinking_entities,
            cognitive_load_high=cognitive_load_high,
            detected_language=detect_language(message),
            message_spans=message_spans,
            stance=stance,
            cognitive_mode=cognitive_mode,
            self_orientation=self_orientation,
            primary_emotion=primary_emotion,
            cognitive_load_label=cognitive_load_label,
            divergence_signals=divergence_signals,
            boundary_markers=boundary_markers,
            trust_signals=[],
        )

    def analyze_key_moment(
        self, what_happened: str, why_it_matters: str
    ) -> KeyMomentAnalysis:
        combined = f"{what_happened}\n{why_it_matters}"
        entities = self._run_ner(combined)
        marker_spans = self._run_raw_ner(combined, POINT_K_NER_LABELS)

        legacy_scores = self.run_classification(combined, _KEY_MOMENT_LEGACY_LABELS)
        boundary_markers = self._detect_boundary_markers(combined)
        boundary_event = (
            legacy_scores.get("boundary event", 0.0) > self._classification_threshold
            or len(boundary_markers) > 0
        )
        principle_invocations = [pat for pat in _PRINCIPLE_PATTERNS_RU if pat in combined.lower()]
        cognitive_load = min(1.0, max(0.0, legacy_scores.get(_HIGH_COGNITIVE_LOAD_LABEL, 0.0)))

        positive_score = legacy_scores.get("positive trust", 0.0)
        negative_score = legacy_scores.get("negative trust", 0.0)
        if positive_score > self._classification_threshold and positive_score > negative_score:
            trust_signal: str | None = "positive"
        elif negative_score > self._classification_threshold and negative_score > positive_score:
            trust_signal = "negative"
        else:
            trust_signal = None

        topic_labels = [
            label
            for label, score in legacy_scores.items()
            if score > self._classification_threshold
        ]

        def _k(candidates: list[str], norm_map: dict | None = None) -> str | None:
            result = self._classify_task(combined, candidates)
            if result is not None and norm_map:
                result = norm_map.get(result, result)
            return result

        return KeyMomentAnalysis(
            entities=entities,
            topic_labels=topic_labels,
            cognitive_load=cognitive_load,
            boundary_event=boundary_event,
            trust_signal=trust_signal,
            principle_invocations=principle_invocations,
            marker_spans=marker_spans,
            agency_level=_k(POINT_K_CLASSIFICATIONS["agency_level"]),
            confidence_in_self=_k(POINT_K_CLASSIFICATIONS["confidence_in_self"], _CONFIDENCE_MAP),
            trust_signal_category=_k(
                POINT_K_CLASSIFICATIONS["trust_signal_category"], _TRUST_CAT_MAP
            ),
            boundary_event_category=_k(
                POINT_K_CLASSIFICATIONS["boundary_event_category"], _BOUNDARY_CAT_MAP
            ),
            connection_quality=_k(POINT_K_CLASSIFICATIONS["connection_quality"]),
            learning_signal=_k(POINT_K_CLASSIFICATIONS["learning_signal"], _LEARNING_MAP),
            growth_indicator=_k(POINT_K_CLASSIFICATIONS["growth_indicator"]),
        )
