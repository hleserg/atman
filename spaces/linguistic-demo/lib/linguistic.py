"""GLiNER + MiniLM linguistic analyzer (Point A / Point K).

Standalone port of `src/atman/adapters/linguistic/gliner_minilm_adapter.py`
for the HuggingFace Space demo. Regenerate with `make sync-demo-linguistic`.
"""

from __future__ import annotations

import hashlib
import logging
import time as _time
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
    # Extended RU markers (memory / values / avoidance discourse)
    "избегает",
    "не обойтись",
    "не называл",
    "эмоционально",
    "ценност",
    "эпизод",
    "понимать человека",
    "против ",
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
        "high cognitive load",
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
    "high cognitive load": "high",
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
    "high cognitive load",
    "boundary event",
    "positive trust",
    "negative trust",
    "principle invocation",
]

_MODEL_TEXT_MAX_CHARS = 1800
_CLASSIFY_TEXT_MAX_CHARS = 768
_NER_CHUNK_CHARS = 1200
_NER_CHUNK_OVERLAP = 150

# Fast rule-based fallback when GLiNER returns nothing (RU + EN discourse cues).
_POINT_A_HEURISTICS: tuple[tuple[str, str], ...] = (
    ("эмоционально", "emotional anchor"),
    ("эпизод", "topic anchor"),
    ("факт", "topic anchor"),
    ("ценност", "value reference"),
    ("принцип", "principle invocation"),
    ("не называл", "hedge"),
    ("не обойтись", "uncertainty marker"),
    ("понимать", "belief marker"),
    ("избегает", "relational reference"),
    ("договорились", "commitment"),
    ("сложност", "intensifier"),
    ("наверное", "hedge"),
    ("может быть", "uncertainty marker"),
    ("против ", "boundary marker"),
    ("i cannot", "boundary marker"),
    ("i will not", "boundary marker"),
    ("maybe", "hedge"),
    ("probably", "hedge"),
    ("understand", "belief marker"),
    ("value", "value reference"),
    ("episode", "topic anchor"),
)


def _pick_top(scores: dict[str, float], threshold: float = 0.5) -> str | None:
    """Return the label with the highest score above threshold, or None."""
    if not scores:
        return None
    top_label, top_score = max(scores.items(), key=lambda kv: kv[1])
    return top_label if top_score >= threshold else None


class GLiNERPlusMiniLMAnalyzer:
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
        ner_threshold: float = 0.35,
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
        self._agent_cache: dict[str, AgentMessageAnalysis] = {}

    @staticmethod
    def _sample_text_for_models(text: str, max_chars: int = _MODEL_TEXT_MAX_CHARS) -> str:
        """Head+tail sample so long posts still hit GLiNER/MiniLM limits."""
        cleaned = text.strip()
        if len(cleaned) <= max_chars:
            return cleaned
        head = max_chars - 280
        tail = 280
        return f"{cleaned[:head]}\n…\n{cleaned[-tail:]}"

    @staticmethod
    def _sample_text_for_classification(text: str) -> str:
        """Shorter sample — classification is slower and tolerates truncation."""
        return GLiNERPlusMiniLMAnalyzer._sample_text_for_models(
            text, max_chars=_CLASSIFY_TEXT_MAX_CHARS
        )

    def _heuristic_point_a_spans(self, text: str) -> list[RawSpan]:
        """Substring fallback for Point A labels when GLiNER finds nothing."""
        if not text.strip():
            return []
        text_lower = text.lower()
        hits: list[tuple[int, int, str, str]] = []
        for needle, label in _POINT_A_HEURISTICS:
            start = 0
            while True:
                idx = text_lower.find(needle, start)
                if idx == -1:
                    break
                end = idx + len(needle)
                hits.append((idx, end, text[idx:end], label))
                start = idx + 1
        hits.sort(key=lambda item: item[0])
        spans: list[RawSpan] = []
        last_end = -1
        for start, end, snippet, label in hits:
            if start < last_end:
                continue
            spans.append(
                RawSpan(text=snippet, label=label, confidence=0.55, span=(start, end))
            )
            last_end = end
        return spans

    def _point_a_ner_spans(self, message: str) -> list[RawSpan]:
        """Heuristics first (instant), GLiNER only when cues are sparse."""
        heuristic = self._heuristic_point_a_spans(message)
        if len(heuristic) >= 3:
            return heuristic
        sample = self._sample_text_for_models(message)
        spans = self._run_raw_ner(sample, _POINT_A_NER_LABELS)
        if spans:
            return spans
        if len(message.strip()) > len(sample):
            spans = self._run_raw_ner_chunked(message, _POINT_A_NER_LABELS)
            if spans:
                return spans
        return heuristic

    def _run_raw_ner_chunked(self, text: str, labels: list[str]) -> list[RawSpan]:
        if len(text) <= _NER_CHUNK_CHARS:
            return self._run_raw_ner(text, labels)
        spans: list[RawSpan] = []
        start = 0
        while start < len(text):
            chunk = text[start : start + _NER_CHUNK_CHARS]
            for span in self._run_raw_ner(chunk, labels):
                if span.span is None:
                    spans.append(span)
                    continue
                rel_start, rel_end = span.span
                abs_start, abs_end = rel_start + start, rel_end + start
                spans.append(
                    RawSpan(
                        text=span.text,
                        label=span.label,
                        confidence=span.confidence,
                        span=(abs_start, abs_end),
                    )
                )
            if start + _NER_CHUNK_CHARS >= len(text):
                break
            start += _NER_CHUNK_CHARS - _NER_CHUNK_OVERLAP
        return spans

    def _classify_tasks_batch(
        self,
        text: str,
        tasks: dict[str, list[str]],
        norm_maps: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, str | None]:
        norm_maps = norm_maps or {}
        sample = self._sample_text_for_classification(text)
        all_labels = list(dict.fromkeys(label for labels in tasks.values() for label in labels))
        scores = self._run_classification(sample, all_labels)
        picked: dict[str, str | None] = {}
        for task_name, candidates in tasks.items():
            task_scores = {label: scores[label] for label in candidates if label in scores}
            top = _pick_top(task_scores, self._classification_threshold)
            if top is not None and task_name in norm_maps:
                top = norm_maps[task_name].get(top, top)
            picked[task_name] = top
        return picked

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
        sample = self._sample_text_for_models(text)
        try:
            raw = model.predict_entities(
                sample,
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

    def _classify_task(self, text: str, task_name: str, candidates: list[str]) -> str | None:
        """Run a single classification task and return the top label above threshold."""
        scores = self._run_classification(text, candidates)
        return _pick_top(scores, self._classification_threshold)

    def _extract_anchors(self, entities: list[DetectedEntity], text: str) -> list[AmbientAnchor]:
        del text
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


    # ------------------------------------------------------------------
    # LinguisticAnalyzer interface
    # ------------------------------------------------------------------

    def clear_session_cache(self) -> None:
        self._session_cache.clear()

    def analyze_user_message(self, text: str) -> UserMessageAnalysis:
        """Extract entities and ambient anchors from a raw user message.

        Results are cached per session by SHA-256(text).
        """
        key = hashlib.sha256(text.encode()).hexdigest()
        cached = self._session_cache.get(key)
        if cached is not None:
            logger.debug(
                "analyze_user_message cache hit entities=%d anchors=%d",
                len(cached.entities),
                len(cached.anchors),
            )
            return cached
        _t0 = _time.monotonic()
        entities = self._run_ner(text)
        anchors = self._extract_anchors(entities, text)
        language = detect_language(text)
        result = UserMessageAnalysis(
            text=text,
            entities=entities,
            anchors=anchors,
            detected_language=language,
        )
        self._session_cache[key] = result
        logger.debug(
            "analyze_user_message entities=%d anchors=%d latency_ms=%.1f",
            len(entities),
            len(anchors),
            (_time.monotonic() - _t0) * 1000,
        )
        return result

    def analyze_agent_message(
        self,
        message: str,
        *,
        thinking: str | None = None,
    ) -> AgentMessageAnalysis:
        """Point A: analyse agent message with 13-label NER + 5 MiniLM classifications."""
        cache_key = hashlib.sha256(f"{message}\0{thinking or ''}".encode()).hexdigest()
        cached = self._agent_cache.get(cache_key)
        if cached is not None:
            return cached

        _t0 = _time.monotonic()
        thinking_entities = self._run_ner(thinking) if thinking else []
        message_spans = self._point_a_ner_spans(message)

        divergence_signals: list[str] = []
        if thinking:
            divergence_signals = self._detect_divergence(thinking, message)

        boundary_markers = self._detect_boundary_markers(message)
        cognitive_load_high = len(thinking or "") > 2000 and (
            len(message_spans) + len(thinking_entities) >= 5
        )

        classified = self._classify_tasks_batch(
            message,
            _POINT_A_CLASSIFICATIONS,
            {
                "self_orientation": _SELF_ORIENTATION_MAP,
                "cognitive_load_label": _COGNITIVE_LOAD_MAP,
            },
        )
        stance = classified.get("stance")
        cognitive_mode = classified.get("cognitive_mode")
        self_orientation = classified.get("self_orientation")
        primary_emotion = classified.get("primary_emotion")
        cognitive_load_label = classified.get("cognitive_load_label")

        language = detect_language(message)
        message_entities = [
            DetectedEntity(
                text=s.text,
                entity_type=EntityType.topic,
                confidence=s.confidence,
                span=s.span,
            )
            for s in message_spans
        ]

        logger.debug(
            "analyze_agent_message entities=%d spans=%d latency_ms=%.1f",
            len(message_entities),
            len(message_spans),
            (_time.monotonic() - _t0) * 1000,
        )
        result = AgentMessageAnalysis(
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
        self._agent_cache[cache_key] = result
        return result

    def analyze_key_moment(
        self,
        what_happened: str,
        why_it_matters: str,
    ) -> KeyMomentAnalysis:
        """Point K: analyse key moment with 4-label NER + 7 MiniLM classifications."""
        combined = f"{what_happened}\n{why_it_matters}"
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
        cognitive_load = min(1.0, max(0.0, legacy_scores.get("high cognitive load", 0.0)))

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

        # Point K MiniLM classifications
        def _k_classify(
            task: str, candidates: list[str], norm_map: dict | None = None
        ) -> str | None:
            result = self._classify_task(combined, task, candidates)
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


def detect_language(text: str) -> str:
    """Cyrillic-presence language detection (matches upstream heuristic)."""
    for ch in text:
        if "Ѐ" <= ch <= "ӿ":
            return "ru"
    return "en"
