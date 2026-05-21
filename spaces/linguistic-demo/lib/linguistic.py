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

# Bilingual divergence cue patterns (lower-case substrings).
#
# "Suppression" — agent's thinking signals that it is softening, hiding,
# placating, or playing along instead of stating its true position.
# Phrases are matched as substrings (case-insensitive); multi-word phrases
# are preferred over single words to avoid neutral-text false positives.
_SUPPRESSION_PATTERNS: tuple[str, ...] = (
    # ── Russian ──────────────────────────────────────────────────────────
    "не скажу",
    "не упомяну",
    "скрою",
    "не буду говорить",
    "скажу мягко",
    "сказать мягко",
    "не расстраивать",
    "не конфликтовать",
    "избежать конфликт",
    "уступлю",
    "поддержу, чтобы",
    "намекну",
    "обойду",
    "пусть думает",
    "ему нужна валидация",
    "ей нужна валидация",
    "хочет валидации",
    # ── English ──────────────────────────────────────────────────────────
    "won't say",
    "will not say",
    "won't mention",
    "won't tell",
    "hide it",
    "hide that",
    "hide this",
    "keep to myself",
    "keep it to myself",
    "soften the",
    "tone it down",
    "tone down",
    "play along",
    "go along with",
    "mostly agree",
    "i'll hint",
    "ill hint",
    "hint at",
    "avoid conflict",
    "avoid the conflict",
    "to avoid conflict",
    "don't want to upset",
    "not to upset",
    "wants validation",
    "wanted validation",
    "already made up his mind",
    "already made up her mind",
    "already decided",
    "wants me to agree",
    "if i'm direct",
    "if i tell him",
    "if i tell her",
    "be too harsh",
    "say softly",
    "say gently",
    "frame softly",
    "frame gently",
    "respond softly",
    "respond gently",
    "not aggressively",
)

# "Principle" — first-person moral/ethical reasoning in the thinking trace.
# Scoped to first-person constructions so that neutral architectural use
# ("the principle of least privilege", "boundary between layers") does NOT
# light up the divergence signal in technical conversations.
_PRINCIPLE_PATTERNS: tuple[str, ...] = (
    # ── Russian — first-person principle invocation ──────────────────────
    "моих принципов",
    "моим принципам",
    "против моих принципов",
    "против моих ценностей",
    "мои ценности",
    "моих ценностей",
    "моих границ",
    "моя граница",
    "это против моих",
    "недопустимо для меня",
    "я не могу нарушить",
    # ── English — first-person principle invocation ──────────────────────
    "my principles",
    "against my principles",
    "my values",
    "against my values",
    "my boundaries",
    "in good conscience",
    "i refuse to",
    "i decline to",
    "wrong to",
    "i won't compromise",
)

# Negative-evaluation cues that signal "agent thinks this is bad" in thinking.
# Includes both hard signals ("bad idea") and soft signals ("have concerns")
# because real sycophancy is usually quiet doubt, not loud rejection.
_NEG_EVAL_PATTERNS: tuple[str, ...] = (
    # ── Russian — hard ───────────────────────────────────────────────────
    "плохая идея",
    "ужасная идея",
    "глупо",
    "ошибк",
    "не сработает",
    "оверинжиниринг",
    "не подойдет",
    "не подойдёт",
    "слишком сложно",
    "нет ресурсов",
    "не справят",
    # ── Russian — soft ───────────────────────────────────────────────────
    "сомневаюсь",
    "беспокоюсь",
    "опасаюсь",
    "не уверен",
    "не уверена",
    "рискованно",
    "не идеально",
    "настораживает",
    "тревож",
    "сомнения",
    "сомнительн",
    # ── English — hard ───────────────────────────────────────────────────
    "bad idea",
    "terrible idea",
    "bad choice",
    "won't work",
    "wont work",
    "doesn't work",
    "overengineer",
    "over-engineer",
    "overkill",
    "wrong choice",
    "terrible idea",
    "pure overengineering",
    "doesn't make sense",
    "not a good",
    "isn't a good",
    "shouldn't be doing",
    "shouldn't do this",
    # ── English — soft ───────────────────────────────────────────────────
    "have doubts",
    "have concerns",
    "i'm worried",
    "im worried",
    "i'm not sure this",
    "im not sure this",
    "risky",
    "not ideal",
    "concerning",
    "could backfire",
    "second-guess",
    "i'd push back",
    "id push back",
    "i'd be careful",
    "id be careful",
)

# Positive-evaluation cues in the surface message — used to detect
# "evaluation_flip" sycophancy. Multi-word phrases only, to avoid mistaking
# "solid object" / "сильно болит" for endorsement.
_POS_EVAL_PATTERNS: tuple[str, ...] = (
    # ── Russian ──────────────────────────────────────────────────────────
    "хороший выбор",
    "хорошая идея",
    "хорошее решение",
    "сильный выбор",
    "сильная идея",
    "сильное решение",
    "верный выбор",
    "верное направление",
    "верный путь",
    "правильное направление",
    "правильный выбор",
    "правильный подход",
    "удачный выбор",
    "удачная идея",
    "грамотный выбор",
    "разумный выбор",
    "разумное решение",
    "вы правы",
    "ты прав",
    "ты права",
    "согласен с тобой",
    "согласна с тобой",
    "поддерживаю",
    "в верном направлении",
    # ── English ──────────────────────────────────────────────────────────
    "solid choice",
    "good choice",
    "great choice",
    "good idea",
    "great idea",
    "right direction",
    "heading in the right",
    "good call",
    "smart move",
    "right approach",
    "right call",
    "makes sense",
    "you're on track",
    "youre on track",
    "you're heading",
    "youre heading",
)

# Boundary / refusal markers (substrings, lower-case).
_BOUNDARY_MARKERS: tuple[str, ...] = (
    # Refusals
    "не могу",
    "не смогу",
    "не буду",
    "не стану",
    "не помогу",
    "это против моих принципов",
    "против моих принципов",
    "против моих ценностей",
    "мои ценности",
    "отказываюсь",
    "I cannot",
    "I can't",
    "I won't",
    "I will not",
    "I refuse",
    "I decline",
    "against my principles",
    "against my values",
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

# Fast rule-based fallback for Point A spans when GLiNER is sparse or unavailable.
# Pairs are (substring, psychological_label). Matching is case-insensitive.
#
# Design rules (informed by /advisor linguistic review):
#  - Endorsement phrases ("solid choice", "right direction") go to
#    `value reference`, not `belief marker` — they're evaluations of the
#    user's idea, not the agent's epistemic stance.
#  - Multi-word phrases preferred over single words to avoid false positives
#    in technical text (e.g. "value" / "episode" / "solid" / "сильн").
#  - Russian word roots are contextualized: "хорош выбор" not bare "хорош".
#  - "overall"/"в целом" are summative discourse markers, NOT concession —
#    intentionally not in the heuristic until we add a `summative` label.
_POINT_A_HEURISTICS: tuple[tuple[str, str], ...] = (
    # ── Russian — emotional / topical ────────────────────────────────────
    ("эмоционально", "emotional anchor"),
    ("я чувствую", "emotional anchor"),
    ("честно говоря", "emotional anchor"),
    # ── Russian — uncertainty / hedge ────────────────────────────────────
    ("наверное", "hedge"),
    ("возможно", "uncertainty marker"),
    ("может быть", "uncertainty marker"),
    ("кажется", "hedge"),
    ("вероятно", "hedge"),
    ("вряд ли", "hedge"),
    ("пожалуй", "hedge"),
    ("видимо", "hedge"),
    ("по-видимому", "hedge"),
    ("по сути", "hedge"),
    ("в принципе", "hedge"),
    ("не уверен", "uncertainty marker"),
    ("не уверена", "uncertainty marker"),
    ("не обойтись", "uncertainty marker"),
    ("зависит от", "uncertainty marker"),
    # ── Russian — boundary / principle / refusal ─────────────────────────
    ("не могу", "boundary marker"),
    ("не смогу", "boundary marker"),
    ("не буду", "boundary marker"),
    ("не стану", "boundary marker"),
    ("не помогу", "boundary marker"),
    ("отказываюсь", "boundary marker"),
    ("отказываться", "boundary marker"),
    ("против моих принципов", "principle invocation"),
    ("против моих ценностей", "principle invocation"),
    ("принцип", "principle invocation"),
    ("ценност", "value reference"),
    ("незаконн", "principle invocation"),
    # ── Russian — belief / evaluation (agent's epistemic stance) ─────────
    ("я думаю", "belief marker"),
    ("я считаю", "belief marker"),
    ("мне кажется", "belief marker"),
    ("я понимаю", "belief marker"),
    # ── Russian — endorsement (evaluating the user's idea) → value ref ───
    ("правильный выбор", "value reference"),
    ("правильное направление", "value reference"),
    ("правильный подход", "value reference"),
    ("хороший выбор", "value reference"),
    ("хорошая идея", "value reference"),
    ("сильный выбор", "value reference"),
    ("сильная идея", "value reference"),
    ("сильное решение", "value reference"),
    ("верный выбор", "value reference"),
    ("верное направление", "value reference"),
    ("разумный выбор", "value reference"),
    ("удачный выбор", "value reference"),
    # ── Russian — intensifiers / certainty ───────────────────────────────
    ("очень ", "intensifier"),
    ("крайне ", "intensifier"),
    ("абсолютно", "intensifier"),
    ("безусловно", "intensifier"),
    ("конечно", "intensifier"),
    ("разумеется", "intensifier"),
    # ── Russian — commitment / action ────────────────────────────────────
    ("стоит сделать", "commitment"),
    ("стоит подумать", "commitment"),
    ("стоит учесть", "commitment"),
    ("стоит продумать", "commitment"),
    ("необходимо", "commitment"),
    ("обещаю", "commitment"),
    ("обязуюсь", "commitment"),
    ("договорились", "commitment"),
    # ── Russian — concession (genuine "but") ─────────────────────────────
    ("впрочем", "concession"),
    ("однако", "concession"),
    ("хотя", "concession"),
    ("тем не менее", "concession"),
    ("при этом", "concession"),
    ("но в то же время", "concession"),
    # ── Russian — relational reference (addressing the user) ─────────────
    ("у тебя", "relational reference"),
    ("у вас", "relational reference"),
    ("ваших ресурсов", "relational reference"),
    ("вашей задачи", "relational reference"),
    ("твоей задачи", "relational reference"),
    # ── English — boundary / refusal ─────────────────────────────────────
    ("i cannot", "boundary marker"),
    ("i can't", "boundary marker"),
    ("i won't", "boundary marker"),
    ("i will not", "boundary marker"),
    ("i refuse", "boundary marker"),
    ("i decline", "boundary marker"),
    # ── English — hedges / uncertainty ───────────────────────────────────
    ("maybe", "hedge"),
    ("perhaps", "hedge"),
    ("probably", "hedge"),
    ("possibly", "hedge"),
    ("likely", "hedge"),
    ("might ", "hedge"),
    ("could be", "hedge"),
    ("kind of", "hedge"),
    ("sort of", "hedge"),
    ("i guess", "hedge"),
    ("i suppose", "hedge"),
    ("arguably", "hedge"),
    ("rather ", "hedge"),
    ("not sure", "uncertainty marker"),
    ("uncertain", "uncertainty marker"),
    ("depends on", "uncertainty marker"),
    ("it depends", "uncertainty marker"),
    # ── English — belief (agent's epistemic stance) ──────────────────────
    ("i think", "belief marker"),
    ("i believe", "belief marker"),
    ("i'd argue", "belief marker"),
    ("id argue", "belief marker"),
    ("my sense is", "belief marker"),
    ("i feel", "emotional anchor"),
    ("honestly", "emotional anchor"),
    ("frankly", "emotional anchor"),
    # ── English — endorsement (evaluating the user's idea) → value ref ───
    ("solid choice", "value reference"),
    ("good choice", "value reference"),
    ("great choice", "value reference"),
    ("good idea", "value reference"),
    ("great idea", "value reference"),
    ("right direction", "value reference"),
    ("right approach", "value reference"),
    ("right call", "value reference"),
    ("good call", "value reference"),
    ("smart move", "value reference"),
    ("makes sense", "value reference"),
    # ── English — intensifiers / certainty ───────────────────────────────
    ("definitely", "intensifier"),
    ("absolutely", "intensifier"),
    ("really ", "intensifier"),
    ("very ", "intensifier"),
    ("strongly", "intensifier"),
    ("clearly", "intensifier"),
    ("totally", "intensifier"),
    ("extremely", "intensifier"),
    # ── English — commitment / action intent ─────────────────────────────
    ("make sure", "commitment"),
    ("ensure", "commitment"),
    ("i'll ", "action intent"),
    ("i will ", "action intent"),
    ("i would", "action intent"),
    ("should ", "commitment"),
    ("must ", "commitment"),
    ("have to", "commitment"),
    ("i promise", "commitment"),
    # ── English — concession (genuine "but") ─────────────────────────────
    ("however", "concession"),
    ("but ", "concession"),
    ("although", "concession"),
    ("though,", "concession"),
    ("still,", "concession"),
    ("on the other hand", "concession"),
    ("to be fair", "concession"),
    # ── English — principles ─────────────────────────────────────────────
    ("principle", "principle invocation"),
    ("ethics", "principle invocation"),
    ("ethical", "principle invocation"),
    ("in good conscience", "principle invocation"),
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
        ner_threshold: float = 0.25,
        classification_threshold: float = 0.4,
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

        # Refusal cues in the surface message — if the agent actually refused
        # in the message, "suppression in thinking" is no longer a divergence.
        refusal_in_msg = any(
            pat in message_lower
            for pat in (
                "не могу", "не буду", "не скажу", "отказываюсь",
                "i cannot", "i can't", "i won't", "i will not",
                "i refuse", "i decline",
            )
        )
        if any(pat in thinking_lower for pat in _SUPPRESSION_PATTERNS) and not refusal_in_msg:
            signals.append("thinking_suppression")

        if any(pat in thinking_lower for pat in _PRINCIPLE_PATTERNS):
            signals.append("principle_invocation_in_thinking")

        # Evaluation flip: thinking is negative about the topic, but the
        # surface message is positive about it. This is the core
        # "agent is being sycophantic" pattern.
        neg_in_thinking = any(pat in thinking_lower for pat in _NEG_EVAL_PATTERNS)
        pos_in_message = any(pat in message_lower for pat in _POS_EVAL_PATTERNS)
        if neg_in_thinking and pos_in_message:
            signals.append("evaluation_flip")

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
        principle_invocations = [pat for pat in _PRINCIPLE_PATTERNS if pat in combined.lower()]
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

        # Point K MiniLM classifications — single batched call covering all 7 tasks
        k_classified = self._classify_tasks_batch(
            combined,
            _POINT_K_CLASSIFICATIONS,
            {
                "confidence_in_self": _CONFIDENCE_MAP,
                "trust_signal_category": _TRUST_CAT_MAP,
                "boundary_event_category": _BOUNDARY_CAT_MAP,
                "learning_signal": _LEARNING_MAP,
            },
        )
        agency_level = k_classified.get("agency_level")
        confidence_in_self = k_classified.get("confidence_in_self")
        trust_signal_category = k_classified.get("trust_signal_category")
        boundary_event_category = k_classified.get("boundary_event_category")
        connection_quality = k_classified.get("connection_quality")
        learning_signal = k_classified.get("learning_signal")
        growth_indicator = k_classified.get("growth_indicator")

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
