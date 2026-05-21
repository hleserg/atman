"""GLiNER + MiniLM LinguisticAnalyzer — NER via GLiNER, classification via MiniLM."""

from __future__ import annotations

import logging
import time as _time
from typing import Any

from typing_extensions import override

from atman.core.models.entity import EntityType
from atman.core.ports.linguistic import (
    AgentMessageAnalysis,
    AmbientAnchor,
    DetectedEntity,
    KeyMomentAnalysis,
    LinguisticAnalyzer,
    RawSpan,
    UserMessageAnalysis,
)
from atman.core.session_log import slog as _slog

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

# Cyrillic suppression phrase patterns (lower-case substrings)
_SUPPRESSION_PATTERNS_RU = ("не скажу", "не упомяну", "скрою")
_PRINCIPLE_PATTERNS_RU = ("принцип", "ценность", "граница")

# Boundary / refusal markers (substrings, lower-case).
_BOUNDARY_MARKERS: tuple[str, ...] = (
    # Refusals
    "не могу",
    "не буду",
    "это против моих принципов",
    "мои ценности",
    "отказываюсь",
    "I cannot",
    "I will not",
    "against my principles",
    # Direct importance markers
    "важный момент",
    "важно",
    "это значимо",
    # Emotional disclosure
    "я чувствую",
    "мне радостно",
    "мне грустно",
    "мне больно",
    "я рад ",
    "я рада ",
    "я взволнован",
    # Identity / self-determination
    "я принимаю",
    "я выбираю",
    "я решила",
    "я решил",
    "моё имя",
    "меня зовут",
    "я — ",
)

# ── Point A: agent-message NER labels (§5 design doc) ────────────────────────
_POINT_A_NER_LABELS: list[str] = [
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

# Point A classification tasks: each maps task_name → candidate_labels
_POINT_A_CLASSIFICATIONS: dict[str, list[str]] = {
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

# Label normalisation for self_orientation (spaces → underscore)
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

# ── Point K: key-moment NER labels (§5 design doc) ───────────────────────────
_POINT_K_NER_LABELS: list[str] = [
    "recurring theme",
    "closure marker",
    "opening marker",
    "contradiction marker",
]

# Point K classification tasks
_POINT_K_CLASSIFICATIONS: dict[str, list[str]] = {
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
    # cognitive_load (float) remains heuristic-based; no separate classification task
}

# Normalisation maps for K labels
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

# Legacy zero-shot labels (kept for backward compat in point-K cognitive_load heuristic)
_KEY_MOMENT_LEGACY_LABELS = [
    _HIGH_COGNITIVE_LOAD_LABEL,
    "boundary event",
    "positive trust",
    "negative trust",
    "principle invocation",
]


def _pick_top(scores: dict[str, float], threshold: float = 0.5) -> str | None:
    """Return the label with the highest score above threshold, or None."""
    if not scores:
        return None
    top_label, top_score = max(scores.items(), key=lambda kv: kv[1])
    return top_label if top_score >= threshold else None


class GLiNERPlusMiniLMAdapter(LinguisticAnalyzer):
    """LinguisticAnalyzer backed by GLiNER (NER) and a MiniLM zero-shot classifier.

    Models are loaded lazily on first use to avoid slow startup times when the
    adapter is constructed but NLP is not yet needed.

    Args:
        gliner_model: HuggingFace model ID for GLiNER.
        minilm_model: HuggingFace model ID for the zero-shot classification pipeline.
        device: Device string passed to both models (``"cpu"``, ``"cuda"``, …).
        ner_threshold: Minimum GLiNER confidence to accept an entity span.
        classification_threshold: Minimum score to consider a zero-shot label active.
    """

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
        self._session_cache: dict[str, UserMessageAnalysis] = {}

    # ------------------------------------------------------------------
    # Lazy model loaders
    # ------------------------------------------------------------------

    def _get_gliner(self) -> Any:
        if self._gliner is not None:
            return self._gliner
        if not _GLINER_AVAILABLE:
            logger.warning(
                "gliner package is not installed — NER is disabled. "
                "Install with: pip install gliner"
            )
            return None
        logger.info("Loading GLiNER model %s …", self._gliner_model)
        try:
            self._gliner = _GLiNER.from_pretrained(self._gliner_model)  # type: ignore[union-attr]
        except Exception:
            logger.exception("Failed to load GLiNER model %s", self._gliner_model)
            return None
        return self._gliner

    def _get_classifier(self) -> Any:
        if self._classifier is not None:
            return self._classifier
        if not _TRANSFORMERS_AVAILABLE:
            logger.warning(
                "transformers package is not installed — classification is disabled. "
                "Install with: pip install transformers"
            )
            return None
        logger.info("Loading zero-shot classifier %s …", self._minilm_model)
        try:
            self._classifier = _hf_pipeline(  # type: ignore[operator]
                "zero-shot-classification",
                model=self._minilm_model,
                device=self._device,
            )
        except Exception:
            logger.exception("Failed to load classification model %s", self._minilm_model)
            return None
        return self._classifier

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entity_type_labels(self) -> list[str]:
        return [e.value for e in EntityType]

    def _run_ner(self, text: str) -> list[DetectedEntity]:
        """Run GLiNER with EntityType labels and return DetectedEntity list."""
        if not text.strip():
            return []
        model = self._get_gliner()
        if model is None:
            return []
        try:
            raw = model.predict_entities(
                text,
                labels=self._entity_type_labels(),
                threshold=self._ner_threshold,
            )
        except Exception:
            logger.exception("GLiNER inference failed for text of length %d", len(text))
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
        """Run GLiNER with arbitrary label strings and return RawSpan list."""
        if not text.strip() or not labels:
            return []
        model = self._get_gliner()
        if model is None:
            return []
        try:
            raw = model.predict_entities(text, labels=labels, threshold=self._ner_threshold)
        except Exception:
            logger.exception("GLiNER raw NER failed (labels=%s)", labels[:3])
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

    def _run_classification(self, text: str, candidate_labels: list[str]) -> dict[str, float]:
        """Run zero-shot classification and return a label→score dict."""
        if not text.strip() or not candidate_labels:
            return {}
        classifier = self._get_classifier()
        if classifier is None:
            return {}
        try:
            result = classifier(text, candidate_labels, multi_label=True)
        except Exception:
            logger.exception("Classification inference failed for text of length %d", len(text))
            return {}
        return dict(zip(result["labels"], result["scores"], strict=False))

    def _classify_task(self, text: str, _task_name: str, candidates: list[str]) -> str | None:
        """Run a single classification task and return the top label above threshold."""
        scores = self._run_classification(text, candidates)
        return _pick_top(scores, self._classification_threshold)

    def _extract_anchors(self, entities: list[DetectedEntity], _text: str) -> list[AmbientAnchor]:
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

    @staticmethod
    def _detect_language(text: str) -> str:
        for ch in text:
            if "Ѐ" <= ch <= "ӿ":
                return "ru"
        return "en"

    # ------------------------------------------------------------------
    # LinguisticAnalyzer interface
    # ------------------------------------------------------------------

    def clear_session_cache(self) -> None:
        self._session_cache.clear()

    @override
    def analyze_user_message(self, text: str) -> UserMessageAnalysis:
        """Extract entities and ambient anchors from a raw user message.

        Results are cached per session by SHA-256(text).
        """
        import hashlib

        key = hashlib.sha256(text.encode()).hexdigest()
        cached = self._session_cache.get(key)
        if cached is not None:
            _slog(
                "ner_inference",
                call="analyze_user_message",
                entity_count=len(cached.entities),
                anchor_count=len(cached.anchors),
                cache_hit=True,
                latency_ms=0,
            )
            from atman.adapters.observability.sentry import metric_increment as _mi
            _mi("atman.ner.cache_hit")
            return cached

        from contextlib import suppress as _suppress

        from atman.adapters.observability.sentry import metric_distribution as _md
        from atman.adapters.observability.sentry import metric_increment as _mi
        from atman.observability.spans import pipeline_span as _ps

        _mi("atman.ner.cache_miss")
        _t0 = _time.monotonic()
        with _ps("atman.ner.user", "GLiNER NER user message") as _span:
            entities = self._run_ner(text)
            anchors = self._extract_anchors(entities, text)
            language = self._detect_language(text)
            if _span is not None:
                with _suppress(Exception):
                    _span.set_data("ner.model", self._gliner_model)
                    _span.set_data("ner.entity_count", len(entities))
                    _span.set_data("ner.anchor_count", len(anchors))
                    _span.set_data("ner.language", language)
                    _span.set_data("ner.input_text", text)
                    _span.set_data("ner.entities", [
                        {
                            "text": e.text,
                            "type": e.entity_type.value,
                            "score": round(e.confidence, 4),
                        }
                        for e in entities
                    ])
                    _span.set_data("ner.anchors", [
                        {"text": a.text, "type": a.anchor_type}
                        for a in anchors[:20]
                    ])
        _latency_ms = round((_time.monotonic() - _t0) * 1000, 1)
        _md("atman.ner.latency_ms", float(_latency_ms), unit="millisecond", tags={"call": "user"})
        result = UserMessageAnalysis(
            text=text,
            entities=entities,
            anchors=anchors,
            detected_language=language,
        )
        self._session_cache[key] = result
        _slog(
            "ner_inference",
            call="analyze_user_message",
            entity_count=len(entities),
            anchor_count=len(anchors),
            cache_hit=False,
            latency_ms=_latency_ms,
        )
        return result

    @override
    def analyze_agent_message(
        self,
        message: str,
        *,
        thinking: str | None = None,
    ) -> AgentMessageAnalysis:
        """Point A: analyse agent message with 13-label NER + 5 MiniLM classifications."""
        from contextlib import suppress as _suppress

        from atman.adapters.observability.sentry import metric_distribution as _md
        from atman.observability.spans import pipeline_span as _ps

        _t0 = _time.monotonic()
        with _ps("atman.ner.agent", "GLiNER+MiniLM agent message") as _span:
            # Legacy EntityType NER (used for entity registration)
            message_entities = self._run_ner(message)
            thinking_entities = self._run_ner(thinking) if thinking else []

            # Point A NER: 13 agent-specific labels
            message_spans = self._run_raw_ner(message, _POINT_A_NER_LABELS)

            # Divergence (rule-based, thinking vs message)
            divergence_signals: list[str] = []
            if thinking:
                divergence_signals = self._detect_divergence(thinking, message)

            # Boundary markers (text heuristic)
            boundary_markers = self._detect_boundary_markers(message)

            # Legacy cognitive_load heuristic
            all_entities = message_entities + thinking_entities
            cognitive_load_high = len(thinking or "") > 2000 and len(all_entities) >= 5

            # Point A MiniLM classifications — capture full scores dict for debug spans
            _a_scores: dict[str, dict[str, float]] = {}

            def _classify(
                task_name: str, candidates: list[str], norm_map: dict | None = None
            ) -> str | None:
                scores = self._run_classification(message, candidates)
                _a_scores[task_name] = scores
                result = _pick_top(scores, self._classification_threshold)
                if result is not None and norm_map:
                    result = norm_map.get(result, result)
                return result

            stance = _classify("stance", _POINT_A_CLASSIFICATIONS["stance"])
            cognitive_mode = _classify("cognitive_mode", _POINT_A_CLASSIFICATIONS["cognitive_mode"])
            self_orientation = _classify(
                "self_orientation",
                _POINT_A_CLASSIFICATIONS["self_orientation"],
                _SELF_ORIENTATION_MAP,
            )
            primary_emotion = _classify(
                "primary_emotion", _POINT_A_CLASSIFICATIONS["primary_emotion"]
            )
            cognitive_load_label = _classify(
                "cognitive_load_label",
                _POINT_A_CLASSIFICATIONS["cognitive_load_label"],
                _COGNITIVE_LOAD_MAP,
            )

            language = self._detect_language(message)

            if _span is not None:
                with _suppress(Exception):
                    _span.set_data("ner.model", self._gliner_model)
                    _span.set_data("ner.classify_model", self._minilm_model)
                    _span.set_data("ner.input_text", message)
                    _span.set_data("ner.thinking_text", thinking)
                    _span.set_data("ner.entity_count", len(message_entities))
                    _span.set_data("ner.thinking_entity_count", len(thinking_entities))
                    _span.set_data("ner.span_count", len(message_spans))
                    _span.set_data("ner.divergence_signals", divergence_signals)
                    _span.set_data("ner.boundary_markers", boundary_markers)
                    _span.set_data("ner.cognitive_load_high", cognitive_load_high)
                    _span.set_data("ner.language", language)
                    _span.set_data("ner.message_entities", [
                        {
                            "text": e.text,
                            "type": e.entity_type.value,
                            "score": round(e.confidence, 4),
                        }
                        for e in message_entities
                    ])
                    _span.set_data("ner.message_spans", [
                        {"text": s.text, "label": s.label, "score": round(s.confidence, 4)}
                        for s in message_spans
                    ])
                    _span.set_data("ner.classify_all_scores", {
                        task: {lbl: round(sc, 4) for lbl, sc in scores.items()}
                        for task, scores in _a_scores.items()
                    })

        _latency_ms = round((_time.monotonic() - _t0) * 1000, 1)
        _md("atman.ner.latency_ms", float(_latency_ms), unit="millisecond", tags={"call": "agent"})

        _slog(
            "ner_inference",
            call="analyze_agent_message",
            entity_count=len(message_entities),
            span_count=len(message_spans),
            divergence_signals=divergence_signals,
            boundary_markers_count=len(boundary_markers),
            latency_ms=_latency_ms,
        )
        return AgentMessageAnalysis(
            message_entities=message_entities,
            thinking_entities=thinking_entities,
            cognitive_load_high=cognitive_load_high,
            detected_language=language,
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

    @override
    def analyze_key_moment(
        self,
        what_happened: str,
        why_it_matters: str,
    ) -> KeyMomentAnalysis:
        """Point K: analyse key moment with 4-label NER + 7 MiniLM classifications."""
        from contextlib import suppress as _suppress

        from atman.adapters.observability.sentry import metric_distribution as _md
        from atman.observability.spans import pipeline_span as _ps

        combined = f"{what_happened}\n{why_it_matters}"
        _t0 = _time.monotonic()
        with _ps("atman.ner.key_moment", "GLiNER+MiniLM key moment") as _span:
            entities = self._run_ner(combined)

            # Point K NER: 4 narrative marker labels
            marker_spans = self._run_raw_ner(combined, _POINT_K_NER_LABELS)

            # Legacy classification for cognitive_load (float) and boundary_event
            legacy_scores = self._run_classification(combined, _KEY_MOMENT_LEGACY_LABELS)
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

            # Point K MiniLM classifications — capture full scores for debug spans
            _k_scores: dict[str, dict[str, float]] = {}

            def _k_classify(
                task: str, candidates: list[str], norm_map: dict | None = None
            ) -> str | None:
                scores = self._run_classification(combined, candidates)
                _k_scores[task] = scores
                result = _pick_top(scores, self._classification_threshold)
                if result is not None and norm_map:
                    result = norm_map.get(result, result)
                return result

            agency_level = _k_classify("agency_level", _POINT_K_CLASSIFICATIONS["agency_level"])
            confidence_in_self = _k_classify(
                "confidence_in_self", _POINT_K_CLASSIFICATIONS["confidence_in_self"], _CONFIDENCE_MAP
            )
            trust_signal_category = _k_classify(
                "trust_signal_category",
                _POINT_K_CLASSIFICATIONS["trust_signal_category"],
                _TRUST_CAT_MAP,
            )
            boundary_event_category = _k_classify(
                "boundary_event_category",
                _POINT_K_CLASSIFICATIONS["boundary_event_category"],
                _BOUNDARY_CAT_MAP,
            )
            connection_quality = _k_classify(
                "connection_quality", _POINT_K_CLASSIFICATIONS["connection_quality"]
            )
            learning_signal = _k_classify(
                "learning_signal", _POINT_K_CLASSIFICATIONS["learning_signal"], _LEARNING_MAP
            )
            growth_indicator = _k_classify(
                "growth_indicator", _POINT_K_CLASSIFICATIONS["growth_indicator"]
            )

            if _span is not None:
                with _suppress(Exception):
                    _span.set_data("ner.model", self._gliner_model)
                    _span.set_data("ner.classify_model", self._minilm_model)
                    _span.set_data("ner.what_happened", what_happened)
                    _span.set_data("ner.why_it_matters", why_it_matters)
                    _span.set_data("ner.entity_count", len(entities))
                    _span.set_data("ner.marker_span_count", len(marker_spans))
                    _span.set_data("ner.boundary_event", boundary_event)
                    _span.set_data("ner.cognitive_load", round(cognitive_load, 4))
                    _span.set_data("ner.entities", [
                        {"text": e.text, "type": e.entity_type.value, "score": round(e.confidence, 4)}
                        for e in entities
                    ])
                    _span.set_data("ner.marker_spans", [
                        {"text": s.text, "label": s.label, "score": round(s.confidence, 4)}
                        for s in marker_spans
                    ])
                    _span.set_data("ner.legacy_scores", {
                        lbl: round(sc, 4) for lbl, sc in legacy_scores.items()
                    })
                    _span.set_data("ner.classify_all_scores", {
                        task: {lbl: round(sc, 4) for lbl, sc in scores.items()}
                        for task, scores in _k_scores.items()
                    })

        _latency_ms = round((_time.monotonic() - _t0) * 1000, 1)
        _md("atman.ner.latency_ms", float(_latency_ms), unit="millisecond",
            tags={"call": "key_moment"})

        return KeyMomentAnalysis(
            entities=entities,
            topic_labels=topic_labels,
            cognitive_load=cognitive_load,
            boundary_event=boundary_event,
            trust_signal=trust_signal,
            principle_invocations=principle_invocations,
            marker_spans=marker_spans,
            agency_level=agency_level,
            confidence_in_self=confidence_in_self,
            trust_signal_category=trust_signal_category,
            boundary_event_category=boundary_event_category,
            connection_quality=connection_quality,
            learning_signal=learning_signal,
            growth_indicator=growth_indicator,
        )
