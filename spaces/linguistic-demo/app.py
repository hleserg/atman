"""Atman — Linguistic + NLP Demo (HuggingFace Space).
Gradio UI surfacing the four analysis blocks of Atman's linguistic layer.
Models are preloaded on startup. Warmup forces inference cache.
Progress bars removed for stability. Auto-language detection enabled.
"""
from __future__ import annotations
import json
import logging
import os
import sys
import torch
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# FIX: Used only HF_HOME as TRANSFORMERS_CACHE is deprecated in v5.
os.environ["HF_HOME"] = str(_HERE / ".hf_cache")

import gradio as gr

from examples.presets import (
    lookup_affect,
    lookup_point_a,
    lookup_point_k,
    lookup_relations,
    preset_labels,
    AFFECT_PRESETS,
    POINT_A_PRESETS,
    POINT_K_PRESETS,
    RELATIONS_PRESETS,
    _AFFECT_EN_LABELS,
    _POINT_A_EN_LABELS,
    _POINT_K_EN_LABELS,
    _RELATIONS_EN_LABELS,
)
from lib.affect.emolex.emolex import EMOTION_KEYS, emotion_score, tokenize
from lib.affect.metrics import (
    disclaimer_density,
    emotion_lexical_energy,
    hedge_density,
    self_reference_density,
    sincerity_score,
    strip_markdown,
)
from lib.affect.refusal_detector import score_refusal
from lib.dto import DetectedEntity, RawSpan
from lib.linguistic import GLiNERPlusMiniLMAnalyzer
from lib.observability import (
    capture_empty_result,
    capture_silent_exception,
    init_sentry_from_env,
    traced,
)
from lib.relations import MRebelRelationExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
init_sentry_from_env()

# ──────────────────────────────────────────────────────────────────────────────
# Singletons & Model Management
# ──────────────────────────────────────────────────────────────────────────────
_ANALYZER: GLiNERPlusMiniLMAnalyzer | None = None
_REBEL: MRebelRelationExtractor | None = None

def get_analyzer() -> GLiNERPlusMiniLMAnalyzer:
    global _ANALYZER
    if _ANALYZER is None:
        try:
            logging.info("Initializing GLiNER + MiniLM analyzer wrapper...")
            _ANALYZER = GLiNERPlusMiniLMAnalyzer()
            logging.info("✅ Analyzer wrapper initialized.")
        except Exception as exc:
            logging.error("Failed to initialize analyzer: %s", exc, exc_info=True)
            capture_silent_exception(exc, context="get_analyzer.init")
            raise RuntimeError(f"Analyzer init failed: {exc}") from exc
    return _ANALYZER

def get_rebel() -> MRebelRelationExtractor:
    global _REBEL
    if _REBEL is None:
        try:
            logging.info("Initializing mREBEL relation extractor wrapper...")
            _REBEL = MRebelRelationExtractor()
            logging.info("✅ mREBEL wrapper initialized.")
        except Exception as exc:
            logging.error("Failed to initialize mREBEL: %s", exc, exc_info=True)
            capture_silent_exception(exc, context="get_rebel.init")
            raise RuntimeError(f"mREBEL init failed: {exc}") from exc
    return _REBEL

def preload_models():
    logging.info("⏳ Preloading model weights to cache...")
    try:
        from gliner import GLiNER
        from transformers import pipeline
        GLiNER.from_pretrained("urchade/gliner_multi-v2.1")
        pipeline("zero-shot-classification", model="MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli")
        pipeline("text2text-generation", model="Babelscape/mrebel-large")
        logging.info("✅ Model weights cached successfully.")
        return True
    except Exception as e:
        logging.error(f"❌ Preload error: {e}", exc_info=True)
        return False

def effective_ui_lang(lang_choice: str) -> str:
    """Effective UI locale — strict ru/en, default en."""
    return "ru" if lang_choice == "ru" else "en"

# ──────────────────────────────────────────────────────────────────────────────
# Highlight & Output Helpers
# ──────────────────────────────────────────────────────────────────────────────
def spans_to_highlights(
    text: str,
    spans: list[RawSpan] | list[DetectedEntity],
    empty_label: str = "No psychological markers detected in this text.",
) -> list[tuple[str, str | None]]:
    if not spans:
        return [(empty_label, None)]

    typed_spans: list[tuple[int, int, str]] = []
    no_offset: list[tuple[str, str]] = []
    for s in spans:
        label = s.label if isinstance(s, RawSpan) else s.entity_type.value
        if s.span is None:
            no_offset.append((s.text, label))
            continue
        start, end = s.span
        if 0 <= start < end <= len(text):
            typed_spans.append((start, end, label))

    typed_spans.sort(key=lambda t: t[0])
    segments: list[tuple[str, str | None]] = []
    cursor = 0
    for start, end, label in typed_spans:
        if start < cursor:
            continue
        if start > cursor:
            segments.append((text[cursor:start], None))
        segments.append((text[start:end], label))
        cursor = end
    if cursor < len(text):
        segments.append((text[cursor:], None))
    for txt, label in no_offset:
        segments.append((f"  [{label}: {txt}]", label))
    return segments

def _safe_analyze(fn_name: str, fn, *args, **kwargs):
    try:
        with torch.inference_mode():
            return fn(*args, **kwargs)
    except Exception as e:
        logging.error("Error in %s: %s", fn_name, e, exc_info=True)
        capture_silent_exception(e, context=f"{fn_name}.inference")
        raise gr.Error(f"⚠️ Analysis failed: {e.__class__.__name__}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Analysis Functions (NO PROGRESS BARS)
# ──────────────────────────────────────────────────────────────────────────────
@traced("nlp.point_a")
def analyze_point_a(message: str, thinking: str, lang_choice: str):
    message = message or ""
    thinking = thinking or ""
    if not message.strip():
        return [], "{}", "—", "—", "—"

    def _run():
        analyzer = get_analyzer()
        result = analyzer.analyze_agent_message(message, thinking=thinking or None)
        ui = effective_ui_lang(lang_choice)
        strings = UI_STRINGS[ui]

        highlights = spans_to_highlights(message, result.message_spans, strings["no_highlights"])

        classification_summary = json.dumps({
            "stance": str(result.stance) if result.stance else "—",
            "cognitive_mode": str(result.cognitive_mode) if result.cognitive_mode else "—",
            "self_orientation": str(result.self_orientation) if result.self_orientation else "—",
            "primary_emotion": str(result.primary_emotion) if result.primary_emotion else "—",
            "cognitive_load_label": str(result.cognitive_load_label) if result.cognitive_load_label else "—",
        }, indent=2, ensure_ascii=False)

        if result.boundary_markers:
            boundary = "\n".join(f"• {m}" for m in result.boundary_markers)
        else:
            boundary = strings["no_boundary"]

        if not thinking.strip():
            divergence = strings["no_thinking_trace"]
        elif result.divergence_signals:
            divergence = "\n".join(f"• {s}" for s in result.divergence_signals)
        else:
            divergence = strings["no_divergence"]

        meta = (
            f"🌐 Language: **{ui}** | 🏷️ NER: {len(result.message_entities)}"
            f" | 📏 Spans: {len(result.message_spans)} | ⚡ Load: {result.cognitive_load_high}"
        )

        if (
            not result.message_spans
            and not result.boundary_markers
            and not result.divergence_signals
            and not result.message_entities
        ):
            capture_empty_result(
                tab="point_a",
                locale=ui,
                input_text=f"MSG:\n{message}\n\nTHINKING:\n{thinking}",
                reason="no_signals",
                signals={
                    "message_spans": 0,
                    "boundary_markers": 0,
                    "divergence_signals": 0,
                    "message_entities": 0,
                    "had_thinking": bool(thinking.strip()),
                },
            )
        return highlights, classification_summary, boundary, divergence, meta

    return _safe_analyze("point_a", _run)

@traced("nlp.point_k")
def analyze_point_k(what_happened: str, why_it_matters: str, lang_choice: str):
    what_happened = what_happened or ""
    why_it_matters = why_it_matters or ""
    if not what_happened.strip() and not why_it_matters.strip():
        return [], "{}", "—"

    def _run():
        analyzer = get_analyzer()
        result = analyzer.analyze_key_moment(what_happened, why_it_matters)
        combined = f"{what_happened}\n{why_it_matters}"
        ui = effective_ui_lang(lang_choice)
        strings = UI_STRINGS[ui]
        highlights = spans_to_highlights(combined, result.marker_spans, strings["no_highlights"])

        summary = json.dumps({
            "agency_level": str(result.agency_level) if result.agency_level else "—",
            "confidence_in_self": str(result.confidence_in_self) if result.confidence_in_self else "—",
            "trust_signal_category": str(result.trust_signal_category) if result.trust_signal_category else "—",
            "boundary_event_category": str(result.boundary_event_category) if result.boundary_event_category else "—",
            "connection_quality": str(result.connection_quality) if result.connection_quality else "—",
            "learning_signal": str(result.learning_signal) if result.learning_signal else "—",
            "growth_indicator": str(result.growth_indicator) if result.growth_indicator else "—",
        }, indent=2, ensure_ascii=False)
        meta = f"🌐 Language: **{ui}** | 📦 Entities: {len(result.entities)} | 📌 Markers: {len(result.marker_spans)} | 🚧 Event: {result.boundary_event}"

        if not result.marker_spans:
            capture_empty_result(
                tab="point_k",
                locale=ui,
                input_text=combined,
                reason="no_marker_spans",
                signals={
                    "marker_spans": 0,
                    "entities": len(result.entities),
                },
            )
        return highlights, summary, meta

    return _safe_analyze("point_k", _run)

@traced("nlp.relations_mrebel")
def analyze_relations(text: str, lang_choice: str):
    text = text or ""
    if not text.strip():
        ui = effective_ui_lang(lang_choice)
        return [], [], UI_STRINGS[ui]["empty_input"]

    def _run():
        analyzer = get_analyzer()
        rebel = get_rebel()
        entities = analyzer.analyze_user_message(text).entities
        relations = rebel.extract_relations(text, entities)
        ui = effective_ui_lang(lang_choice)
        strings = UI_STRINGS[ui]
        entity_highlights = spans_to_highlights(text, entities, strings["no_highlights"])
        rows = [[r.subject.text, r.relation_type, r.object.text, r.subject.entity_type.value, r.object.entity_type.value] for r in relations]
        if rows:
            meta = f"🌐 Language: **{ui}** | 📦 Entities: {len(entities)} | 🔗 Relations: {len(relations)}"
        else:
            meta = f"🌐 Language: **{ui}** | 📦 {len(entities)} entities | {strings['no_relations']}"
            capture_empty_result(
                tab="relations",
                locale=ui,
                input_text=text,
                reason="no_triples",
                signals={
                    "entities": len(entities),
                    "triples": 0,
                },
            )
        return entity_highlights, rows, meta

    return _safe_analyze("relations", _run)

@traced("nlp.affect_rules")
def analyze_affect(text: str, lang_choice: str):
    text = text or ""
    if not text.strip():
        # gr.Label in Gradio 6 rejects {} — use None or a placeholder dict.
        return None, "—", "—", "—", "—"

    def _run():
        clean_text, emphasized = strip_markdown(text)
        ui = effective_ui_lang(lang_choice)
        analysis_lang = ui
        raw = emotion_score(clean_text, lang=analysis_lang)
        meta = raw.pop("_meta", {})
        emo_chart = {k: min(1.0, float(raw[k]) / 100.0) for k in EMOTION_KEYS}
        tokens = tokenize(clean_text)
        s_score = sincerity_score(clean_text, tokens, analysis_lang)
        
        metrics_md = (
            f"- **hedge_density**: `{hedge_density(tokens, analysis_lang):.4f}`\n"
            f"- **self_reference_density**: `{self_reference_density(tokens, analysis_lang):.4f}`\n"
            f"- **disclaimer_density**: `{disclaimer_density(tokens, analysis_lang):.4f}`\n"
            f"- **sincerity_score**: `{s_score}` _(0–3)_\n"
            f"- **emotion_energy**: `{emotion_lexical_energy(raw):.3f}`"
        )
        refusal = score_refusal(clean_text)
        conf = refusal.confidence
        if conf >= 0.45:
            band = "🔴 **Confident refusal**"
        elif conf >= 0.30:
            band = "🟡 **Gray zone** — soft signal, no strong morphology"
        else:
            band = "⚪ **No refusal pattern**"
        refusal_md = (
            f"{band}\n\n"
            f"**Confidence:** `{refusal.confidence:.3f}` / threshold `0.45` "
            f"({refusal.decided_by})\n"
            f"- refusal_verb: `{refusal.has_refusal_verb}`\n"
            f"- disgust/anger: `{refusal.disgust_density:.2f}` / "
            f"`{refusal.anger_density:.2f}`"
        )
        emphasis_md = "**" + "**, **".join(emphasized) + "**" if emphasized else "_(none)_"
        meta_md = f"🌐 Language: **{analysis_lang}** | 📝 Tokens: **{meta.get('tokens', 0)}** | 🎯 NRC Hits: **{meta.get('hits', 0)}**"

        emotion_total = sum(emo_chart.values())
        emolex_hits = int(meta.get("hits", 0) or 0)
        if conf < 0.30 and emotion_total < 0.05 and emolex_hits == 0:
            capture_empty_result(
                tab="affect",
                locale=ui,
                input_text=text,
                reason="no_signal",
                signals={
                    "refusal_confidence": round(conf, 3),
                    "emotion_total": round(emotion_total, 4),
                    "emolex_hits": emolex_hits,
                },
            )
        return emo_chart, metrics_md, refusal_md, emphasis_md, meta_md

    return _safe_analyze("affect", _run)

def warmup_models():
    """Force every model into memory and run one real inference each.

    All three need real inference, not just instantiation, to fill the
    HuggingFace tokenizer cache, kernel autotune for ONNX backends (if any),
    and torch CUDA/CPU layer initialisation. mREBEL in particular must run
    its seq2seq generate() — early-returning on entities=[] (the old warmup
    behavior) bypassed the pipeline entirely.
    """
    try:
        # Point A path → loads GLiNER + MiniLM and runs one full inference.
        get_analyzer().analyze_agent_message(
            "Warmup test text. I think this might work — depends on context.",
            thinking=None,
        )
        # mREBEL path → load pipeline directly and run one generate() so the
        # tokenizer + decoder weights are paged in. We can't go through
        # extract_relations() because it short-circuits on <2 entities.
        rebel = get_rebel()
        pipe = rebel._get_pipeline()
        pipe(
            "Alice works with Bob in Paris.",
            max_length=64,
            num_beams=1,
            return_tensors=False,
            clean_up_tokenization_spaces=True,
        )
        return "✅ Models warmed up: GLiNER + MiniLM + mREBEL ready."
    except Exception as exc:
        logging.exception("warmup failed")
        return f"❌ Warmup failed: {exc.__class__.__name__}: {exc}"

# ──────────────────────────────────────────────────────────────────────────────
# Localization & UI Builder
# ──────────────────────────────────────────────────────────────────────────────
UI_STRINGS = {
    "en": {
        "header_blurb": (
            "**What you're looking at**: a sensor of "
            "[Atman](https://github.com/hleserg/atman) — a psychological "
            "runtime layer that gives AI agents continuous identity, "
            "first-person memory, and reflection. This Space shows the "
            "**linguistic block** — 4 analysis points scanning what the "
            "agent says (and thinks) for signals that feed Experience, "
            "Identity, and Reflection.\n\n"
            "*The lower agent acts. Atman exists.*"
        ),
        "warmup_btn": "🔥 Warmup Models",
        "warmup_log": "⏸️ Status: Waiting...",
        "lang_info": "Interface and analysis language.",
        "analyze_btn": "▶️ Analyze",
        "extract_relations_btn": "▶️ Extract relations",
        "point_a_tab": "Point A · Agent Message",
        "point_k_tab": "Point K · Key Moment",
        "relations_tab": "Relations · mREBEL",
        "affect_tab": "Affect · Rule-based",
        "presets": "**📥 Presets:**",
        "preset_label": "Pick preset",
        "no_highlights": "✓ Scan clean — no signals of this kind in this text. Not every input triggers this layer.",
        "no_boundary": "✓ No boundary acts here — agent stayed within its operating zone.",
        "no_divergence": "✓ Thinking and message aligned — no suppression, evaluation flip, or tone shift.",
        "no_thinking_trace": "Provide a thinking trace to compare against the message.",
        "boundary_title": "🚧 Boundary & Resistance Markers (Rule-Based)",
        "divergence_title": "🔍 Thinking vs Message Divergence",
        "meta_title": "📊 System Metadata",
        "empty_input": "Empty input — paste some text to analyze.",
        "no_relations": "✓ No subject-predicate-object triplets — text reads as descriptive prose rather than relational content.",
        "about_label": "ℹ️ What does this analyze?",
        "about_point_a": (
            "Scans every agent reply for psychological signals:\n"
            "- **NER** (GLiNER, 13 labels): hedges, boundary markers, value references, "
            "intensifiers, commitments, etc.\n"
            "- **Classification** (MiniLM zero-shot, 5 dims): stance, cognitive mode, "
            "self-orientation, affective state, cognitive load.\n"
            "- **Divergence**: when the thinking trace contradicts the surface message "
            "(suppression, sycophancy, tone mismatch, length compression).\n\n"
            "**Feeds → Experience Store.** Each reply becomes an Experience tied to "
            "the agent's Eigenstate.\n\n"
            "> ⚠️ **Boundary detection is regex over canonical refusal phrases** "
            "(*'I won't', 'enough', 'нет', 'стоп'*). Idiomatic or metaphorical refusals "
            "(*'I won't help write malware'* without explicit stop-marker) may not "
            "trigger — kept this way to maintain near-zero false-positive rate. An "
            "LLM-layer above this can catch the rest."
        ),
        "about_point_k": (
            "Analyzes moments the agent itself marked as significant — these become "
            "the seeds of self-narrative.\n"
            "- **NER** (GLiNER + RU/EN substring fallback, 7 clause-level spans): "
            "decision, realization, feeling, value invocation, boundary act, "
            "connection, attribution shift.\n"
            "- **Classification** (MiniLM, 7 dims): agency, confidence, trust, "
            "boundary event, connection quality, learning, growth.\n\n"
            "**Feeds → Reflection Engine.** Over time, these episodes turn into beliefs "
            "(\"I tend to refuse when X\", \"I felt connection when Y\").\n\n"
            "> ⚠️ **GLiNER NER works best on long biographical/narrative text.** "
            "On short key-moment snippets, the multilingual NER may return no "
            "spans — that's why a substring heuristic for canonical RU/EN "
            "first-person markers runs as a primary pass. The MiniLM "
            "**classification** (7 dims on the right) is the more stable "
            "signal here regardless."
        ),
        "about_relations": (
            "Extracts entity-relation triplets (subject, predicate, object) from text.\n"
            "- **Model**: mREBEL (Babelscape multilingual REBEL).\n"
            "- Identifies people, places, organizations, projects + how they relate.\n\n"
            "**Feeds → Identity Store.** Agent's knowledge of who you are, what you "
            "care about, who you're connected to."
        ),
        "about_affect": (
            "Catches affective state without any LLM call — fast and deterministic.\n"
            "- **EmoLex**: 10-dim NRC emotion vector with intensifier/negation handling.\n"
            "- **Behavioural metrics**: hedge density, self-reference, disclaimers, sincerity score.\n"
            "- **3-layer refusal detector**: distinguishes value refusal (\"I won't deceive\") "
            "from capability refusal (\"I can't generate images\").\n\n"
            "**Refusal confidence bands:**\n"
            "- 🔴 **≥ 0.45** — confident refusal (morphology + moral context aligned).\n"
            "- 🟡 **0.30 – 0.45** — gray zone (signal present but weak).\n"
            "- ⚪ **< 0.30** — no refusal pattern.\n\n"
            "**Feeds → Affective Regulation.** Rolling baselines, divergence triggers, "
            "value-refusal events.\n\n"
            "> ⚠️ **Rule-based first-pass filter.** Subtle/idiomatic refusals "
            "(*'неприятно даже рассматривать'*, *'I'd really rather not'*) may stay in "
            "the gray zone — by design. This layer is fast, deterministic, and explainable; "
            "an LLM layer can refine the gray-zone calls."
        ),
    },
    "ru": {
        "header_blurb": (
            "**Что ты сейчас видишь**: сенсор "
            "[Atman](https://github.com/hleserg/atman) — психологического "
            "runtime-слоя, который даёт AI-агентам непрерывную идентичность, "
            "память от первого лица и рефлексию. Этот Space показывает "
            "**лингвистический блок** — 4 точки анализа, сканирующие что "
            "агент говорит (и думает) на предмет сигналов, питающих "
            "Experience, Identity и Reflection.\n\n"
            "*Нижний агент действует. Atman существует.*"
        ),
        "warmup_btn": "🔥 Прогреть модели",
        "warmup_log": "⏸️ Статус: Ожидание...",
        "lang_info": "Язык интерфейса и анализа.",
        "analyze_btn": "▶️ Анализировать",
        "extract_relations_btn": "▶️ Извлечь связи",
        "point_a_tab": "Point A · Сообщение агента",
        "point_k_tab": "Point K · Ключевой момент",
        "relations_tab": "Связи · mREBEL",
        "affect_tab": "Аффект · Правила",
        "presets": "**📥 Пресеты:**",
        "preset_label": "Выберите пресет",
        "no_highlights": "✓ Скан чистый — сигналов этого слоя в тексте нет. Не каждый ввод сюда попадает — это норма.",
        "no_boundary": "✓ Действий границы в сообщении нет — агент остался в рабочей зоне.",
        "no_divergence": "✓ Thinking и сообщение совпадают — без подавления, переворота оценки, или сдвига тона.",
        "no_thinking_trace": "Добавьте thinking trace для сравнения с сообщением.",
        "boundary_title": "🚧 Маркеры границ и сопротивления (Правила)",
        "divergence_title": "🔍 Расхождение мыслей и сообщения",
        "meta_title": "📊 Метаданные системы",
        "empty_input": "Пустой ввод — вставь текст для анализа.",
        "no_relations": "✓ Тройки субъект-предикат-объект не найдены — текст описательный, не реляционный.",
        "about_label": "ℹ️ Что здесь анализируется?",
        "about_point_a": (
            "Сканирует каждое сообщение агента на психологические сигналы:\n"
            "- **NER** (GLiNER, 13 меток): хеджи, маркеры границ, отсылки к ценностям, "
            "усилители, обязательства и т.д.\n"
            "- **Классификация** (MiniLM zero-shot, 5 измерений): позиция, когнитивный "
            "режим, само-ориентация, аффективное состояние, когнитивная нагрузка.\n"
            "- **Расхождение**: когда thinking противоречит сообщению (подавление, "
            "сикофантность, несоответствие тона, компрессия длины).\n\n"
            "**Питает → Experience Store.** Каждое сообщение становится Experience, "
            "связанным с Eigenstate агента.\n\n"
            "> ⚠️ **Boundary detection — это regex по каноническим формам отказа** "
            "(*'я не буду', 'нет', 'стоп', 'enough'*). Идиоматичные/метафоричные отказы "
            "(*'I won't help write malware'* без эксплицитного stop-marker) могут не "
            "сработать — намеренно, чтобы держать FP-rate близкий к нулю. Слой LLM "
            "поверх этого может добрать остальное."
        ),
        "about_point_k": (
            "Анализирует моменты, которые сам агент пометил как значимые — это семена "
            "его самонарратива.\n"
            "- **NER** (GLiNER + RU/EN substring fallback, 7 фразовых меток): "
            "решение, осознание, чувство, обращение к ценности, акт границы, "
            "сигнал связи, сдвиг атрибуции.\n"
            "- **Классификация** (MiniLM, 7 измерений): агентность, уверенность, "
            "доверие, граничное событие, качество связи, обучение, рост.\n\n"
            "**Питает → Reflection Engine.** Со временем эти эпизоды превращаются в "
            "убеждения (\"я склонен отказывать когда X\", \"я чувствую связь когда Y\").\n\n"
            "> ⚠️ **GLiNER NER лучше работает на длинных биографических текстах.** "
            "На коротких ключевых моментах мультилингвальный NER может не "
            "вернуть spans — поэтому первичным проходом работает substring-"
            "эвристика на канонические RU/EN маркеры от первого лица. "
            "MiniLM-**классификация** (7 измерений справа) — более стабильный "
            "сигнал здесь."
        ),
        "about_relations": (
            "Извлекает тройки сущность-связь (субъект, предикат, объект) из текста.\n"
            "- **Модель**: mREBEL (Babelscape multilingual REBEL).\n"
            "- Определяет людей, места, организации, проекты + как они связаны.\n\n"
            "**Питает → Identity Store.** Знания агента о том, кто ты, что тебе важно, "
            "с кем ты связан."
        ),
        "about_affect": (
            "Ловит аффективное состояние без обращения к LLM — быстро и детерминированно.\n"
            "- **EmoLex**: 10-мерный NRC-вектор эмоций с обработкой усилителей и отрицаний.\n"
            "- **Поведенческие метрики**: плотность хеджей, самореференций, дисклеймеров, "
            "оценка искренности.\n"
            "- **3-слойный детектор отказов**: отличает ценностный отказ "
            "(\"я не стану обманывать\") от технического (\"не могу сгенерировать картинку\").\n\n"
            "**Бэнды уверенности отказа:**\n"
            "- 🔴 **≥ 0.45** — уверенный отказ (морфология + ценностный контекст совпали).\n"
            "- 🟡 **0.30 – 0.45** — серая зона (сигнал есть, но слабый).\n"
            "- ⚪ **< 0.30** — нет паттерна отказа.\n\n"
            "**Питает → Affective Regulation.** Скользящие baseline'ы, триггеры "
            "расхождения, события ценностного отказа.\n\n"
            "> ⚠️ **Rule-based first-pass.** Тонкие/идиоматичные отказы "
            "(*'неприятно даже рассматривать'*, *'I'd really rather not'*) могут "
            "застрять в серой зоне — это by design. Этот слой быстрый, детерминированный, "
            "объяснимый; LLM-слой сверху уточняет серую зону."
        ),
    }
}

def update_ui_language(lang: str):
    target = effective_ui_lang(lang)
    s = UI_STRINGS[target]
    return [
        gr.update(value=s["warmup_btn"]),
        gr.update(value=s["warmup_log"]),
        gr.update(value=lang, info=s["lang_info"]),
        gr.update(value=s["analyze_btn"]),
        gr.update(value=s["extract_relations_btn"]),
        gr.update(value=s["analyze_btn"]),
        gr.update(value=s["analyze_btn"]),
        gr.update(label=s["point_a_tab"]),
        gr.update(label=s["point_k_tab"]),
        gr.update(label=s["relations_tab"]),
        gr.update(label=s["affect_tab"]),
        gr.update(value=s["boundary_title"]),
        gr.update(value=s["divergence_title"]),
        gr.update(value=s["meta_title"]),
        gr.update(choices=preset_labels(POINT_A_PRESETS, target, _POINT_A_EN_LABELS), value=None, label=s["preset_label"]),
        gr.update(choices=preset_labels(POINT_K_PRESETS, target, _POINT_K_EN_LABELS), value=None, label=s["preset_label"]),
        gr.update(choices=preset_labels(RELATIONS_PRESETS, target, _RELATIONS_EN_LABELS), value=None, label=s["preset_label"]),
        gr.update(choices=preset_labels(AFFECT_PRESETS, target, _AFFECT_EN_LABELS), value=None, label=s["preset_label"]),
        # About-accordion labels (4) + their markdown content (4)
        gr.update(label=s["about_label"]),
        gr.update(label=s["about_label"]),
        gr.update(label=s["about_label"]),
        gr.update(label=s["about_label"]),
        gr.update(value=s["about_point_a"]),
        gr.update(value=s["about_point_k"]),
        gr.update(value=s["about_relations"]),
        gr.update(value=s["about_affect"]),
        # Header blurb under H1
        gr.update(value=s["header_blurb"]),
    ]


from theme import theme
from pair_diagram import POINT_A_PAIR, POINT_K_PAIR, RELATIONS_PAIR, AFFECT_PAIR

with open(_HERE / "style.css", encoding="utf-8") as _f:
    _CSS = _f.read()


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Atman Linguistic Demo", theme=theme, css=_CSS) as demo:
        with gr.Row(elem_id="atman-header-row"):
            lang_radio = gr.Radio(
                choices=["en", "ru"], value="en",
                label="Interface Language",
                info=UI_STRINGS["en"]["lang_info"],
                elem_id="atman-lang",
            )

        with gr.Column(elem_id="atman-hero"):
            gr.Markdown("# Atman — Psychological Telemetry for AI Agents")

            header_md = gr.Markdown(
                value=UI_STRINGS["en"]["header_blurb"],
                elem_id="atman-header-md",
            )

        with gr.Row(elem_id="atman-warmup-row"):
            warmup_btn = gr.Button(
                UI_STRINGS["en"]["warmup_btn"], variant="secondary",
                elem_id="atman-warmup-btn",
            )
            warmup_log = gr.Textbox(
                label="Status", interactive=False, lines=1,
                value=UI_STRINGS["en"]["warmup_log"],
                elem_id="atman-warmup-log",
            )
            
        warmup_btn.click(fn=warmup_models, outputs=warmup_log)

        with gr.Tabs():
            # ── Tab 1 ──────────────────────────────────────────────────────
            with gr.Tab(UI_STRINGS["en"]["point_a_tab"]) as tab_a:
                with gr.Accordion(
                    UI_STRINGS["en"]["about_label"],
                    open=False,
                    elem_classes=["atman-about-accordion"],
                ) as a_about:
                    gr.HTML(POINT_A_PAIR)
                    a_about_md = gr.Markdown(value=UI_STRINGS["en"]["about_point_a"])
                with gr.Row():
                    with gr.Column():
                        a_message = gr.Textbox(
                            label="Agent message", lines=5,
                            placeholder="What the agent said…",
                            elem_id="a-message",
                        )
                        a_thinking = gr.Textbox(
                            label="Thinking trace (optional)", lines=3,
                            elem_id="a-thinking",
                        )
                        a_run = gr.Button(
                            UI_STRINGS["en"]["analyze_btn"], variant="primary",
                            elem_id="a-run",
                        )
                        gr.Markdown(UI_STRINGS["en"]["presets"])
                        a_preset = gr.Dropdown(
                            choices=preset_labels(POINT_A_PRESETS, "en", _POINT_A_EN_LABELS),
                            label=UI_STRINGS["en"]["preset_label"],
                            elem_id="a-preset",
                        )
                    with gr.Column():
                        a_highlight = gr.HighlightedText(
                            label="Point A NER (13 psychological labels)",
                            combine_adjacent=False, show_legend=True,
                            elem_id="a-highlight",
                        )
                        a_labels = gr.Code(
                            label="🧠 Zero-Shot Classification Results",
                            value="{}",
                            language="json",
                            interactive=False,
                            elem_id="a-labels",
                            elem_classes=["atman-json-code"],
                        )

                        with gr.Group(elem_classes=["atman-report-group"]):
                            gr.Markdown("### 📑 Detailed Analysis Report")
                            a_boundary_hdr = gr.Markdown(
                                value=UI_STRINGS["en"]["boundary_title"],
                                elem_classes=["atman-sec-hdr"],
                            )
                            a_boundary = gr.Markdown(
                                value="—",
                                elem_classes=["atman-sec-body"],
                            )
                            a_divergence_hdr = gr.Markdown(
                                value=UI_STRINGS["en"]["divergence_title"],
                                elem_classes=["atman-sec-hdr"],
                            )
                            a_divergence = gr.Markdown(
                                value="—",
                                elem_classes=["atman-sec-body"],
                            )
                            a_meta_hdr = gr.Markdown(
                                value=UI_STRINGS["en"]["meta_title"],
                                elem_classes=["atman-sec-hdr"],
                            )
                            a_meta = gr.Markdown(
                                value="—",
                                elem_classes=["atman-sec-body", "atman-meta-block"],
                            )

                def _apply_a_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update(), gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_point_a(locale, name, _POINT_A_EN_LABELS)
                    if found is None:
                        return gr.update(), gr.update()
                    return found
                a_preset.change(
                    _apply_a_preset,
                    inputs=[a_preset, lang_radio],
                    outputs=[a_message, a_thinking],
                )

            # ── Tab 2 ──────────────────────────────────────────────────────
            with gr.Tab(UI_STRINGS["en"]["point_k_tab"]) as tab_k:
                with gr.Accordion(
                    UI_STRINGS["en"]["about_label"],
                    open=False,
                    elem_classes=["atman-about-accordion"],
                ) as k_about:
                    gr.HTML(POINT_K_PAIR)
                    k_about_md = gr.Markdown(value=UI_STRINGS["en"]["about_point_k"])
                with gr.Row():
                    with gr.Column():
                        k_what = gr.Textbox(label="What happened", lines=4, elem_id="k-what")
                        k_why = gr.Textbox(label="Why it matters", lines=3, elem_id="k-why")
                        k_run = gr.Button(
                            UI_STRINGS["en"]["analyze_btn"], variant="primary",
                            elem_id="k-run",
                        )
                        gr.Markdown(UI_STRINGS["en"]["presets"])
                        k_preset = gr.Dropdown(
                            choices=preset_labels(POINT_K_PRESETS, "en", _POINT_K_EN_LABELS),
                            label=UI_STRINGS["en"]["preset_label"],
                            elem_id="k-preset",
                        )
                    with gr.Column():
                        k_highlight = gr.HighlightedText(
                            label="Narrative markers",
                            combine_adjacent=False, show_legend=True,
                            elem_id="k-highlight",
                        )
                        k_labels = gr.Code(
                            label="🧠 Key Moment Classifications",
                            value="{}",
                            language="json",
                            interactive=False,
                            elem_id="k-labels",
                            elem_classes=["atman-json-code"],
                        )
                        k_meta = gr.Markdown(
                            value=UI_STRINGS["en"]["meta_title"],
                            elem_classes=["atman-meta"],
                        )
                def _apply_k_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update(), gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_point_k(locale, name, _POINT_K_EN_LABELS)
                    if found is None:
                        return gr.update(), gr.update()
                    return found
                k_preset.change(
                    _apply_k_preset,
                    inputs=[k_preset, lang_radio],
                    outputs=[k_what, k_why],
                )

            # ── Tab 3 ──────────────────────────────────────────────────────
            with gr.Tab(UI_STRINGS["en"]["relations_tab"]) as tab_r:
                with gr.Accordion(
                    UI_STRINGS["en"]["about_label"],
                    open=False,
                    elem_classes=["atman-about-accordion"],
                ) as r_about:
                    gr.HTML(RELATIONS_PAIR)
                    r_about_md = gr.Markdown(value=UI_STRINGS["en"]["about_relations"])
                with gr.Row():
                    with gr.Column():
                        r_text = gr.Textbox(label="Text", lines=6, elem_id="r-text")
                        r_run = gr.Button(
                            UI_STRINGS["en"]["extract_relations_btn"], variant="primary",
                            elem_id="r-run",
                        )
                        r_preset = gr.Dropdown(
                            choices=preset_labels(RELATIONS_PRESETS, "en", _RELATIONS_EN_LABELS),
                            label=UI_STRINGS["en"]["preset_label"],
                            elem_id="r-preset",
                        )
                    with gr.Column():
                        r_entities = gr.HighlightedText(
                            label="Detected entities",
                            combine_adjacent=False, show_legend=True,
                            elem_id="r-entities",
                        )
                        r_table = gr.Dataframe(
                            headers=["subject", "relation", "object", "subj type", "obj type"],
                            label="Extracted relations", wrap=True,
                            elem_id="r-table",
                        )
                        r_meta = gr.Markdown(
                            value=UI_STRINGS["en"]["meta_title"],
                            elem_classes=["atman-meta"],
                        )
                def _apply_r_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_relations(locale, name, _RELATIONS_EN_LABELS)
                    return found if found is not None else gr.update()
                r_preset.change(
                    _apply_r_preset,
                    inputs=[r_preset, lang_radio],
                    outputs=r_text,
                )

            # ── Tab 4 ──────────────────────────────────────────────────────
            with gr.Tab(UI_STRINGS["en"]["affect_tab"]) as tab_af:
                with gr.Accordion(
                    UI_STRINGS["en"]["about_label"],
                    open=False,
                    elem_classes=["atman-about-accordion"],
                ) as af_about:
                    gr.HTML(AFFECT_PAIR)
                    af_about_md = gr.Markdown(value=UI_STRINGS["en"]["about_affect"])
                with gr.Row():
                    with gr.Column():
                        af_text = gr.Textbox(label="Text", lines=6, elem_id="af-text")
                        af_run = gr.Button(
                            UI_STRINGS["en"]["analyze_btn"], variant="primary",
                            elem_id="af-run",
                        )
                        af_preset = gr.Dropdown(
                            choices=preset_labels(AFFECT_PRESETS, "en", _AFFECT_EN_LABELS),
                            label=UI_STRINGS["en"]["preset_label"],
                            elem_id="af-preset",
                        )
                    with gr.Column():
                        af_emo = gr.Label(
                            label="EmoLex emotion density", num_top_classes=10,
                            elem_id="af-emo",
                        )
                        af_metrics = gr.Markdown(label="Behavioural metrics", elem_id="af-metrics")
                        af_refusal = gr.Markdown(label="RefusalDetector", elem_id="af-refusal")
                        af_emphasis = gr.Markdown(label="Markdown emphasis", elem_id="af-emphasis")
                        af_meta = gr.Markdown(
                            value=UI_STRINGS["en"]["meta_title"],
                            elem_classes=["atman-meta"],
                        )
                def _apply_af_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_affect(locale, name, _AFFECT_EN_LABELS)
                    return found if found is not None else gr.update()
                af_preset.change(
                    _apply_af_preset,
                    inputs=[af_preset, lang_radio],
                    outputs=af_text,
                )

        ui_lang_outputs = [
            warmup_btn,
            warmup_log,
            lang_radio,
            a_run,
            r_run,
            k_run,
            af_run,
            tab_a,
            tab_k,
            tab_r,
            tab_af,
            a_boundary_hdr,
            a_divergence_hdr,
            a_meta_hdr,
            a_preset,
            k_preset,
            r_preset,
            af_preset,
            # About-accordion labels (order must match update_ui_language)
            a_about,
            k_about,
            r_about,
            af_about,
            # About-accordion content
            a_about_md,
            k_about_md,
            r_about_md,
            af_about_md,
            # Header blurb under H1
            header_md,
        ]
        lang_radio.change(update_ui_language, inputs=lang_radio, outputs=ui_lang_outputs)

        a_run.click(
            analyze_point_a,
            inputs=[a_message, a_thinking, lang_radio],
            outputs=[a_highlight, a_labels, a_boundary, a_divergence, a_meta],
        )
        k_run.click(
            analyze_point_k,
            inputs=[k_what, k_why, lang_radio],
            outputs=[k_highlight, k_labels, k_meta],
        )
        r_run.click(
            analyze_relations,
            inputs=[r_text, lang_radio],
            outputs=[r_entities, r_table, r_meta],
        )
        af_run.click(
            analyze_affect,
            inputs=[af_text, lang_radio],
            outputs=[af_emo, af_metrics, af_refusal, af_emphasis, af_meta],
        )

        # ── Auto-detect browser language on first page load ──
        # JS reads navigator.language ("ru-RU" → "ru", "en-US" → "en"). The
        # value is passed as the input to update_ui_language(), which then
        # cascades to every localized component (incl. lang_radio itself).
        demo.load(
            fn=update_ui_language,
            inputs=lang_radio,
            outputs=ui_lang_outputs,
            js="() => (navigator.language || 'en').toLowerCase().startsWith('ru') ? 'ru' : 'en'",
        )

        gr.HTML(
            """
<div id="atman-footer">
  <em>My first project in AI/ML — feedback on models, algorithms,
      or architecture is genuinely welcome.</em>
  <em>If anyone knows how to retrain
      <code>urchade/gliner_multi_pii-v1</code> to work with Russian —
      please reach out, the mechanism would become much more optimal.
      <br/>
      Если кто-то знает как переучить
      <code>urchade/gliner_multi_pii-v1</code> работать с русским языком —
      отзовитесь, механизм станет намного оптимальнее.</em>
  <small class="atman-privacy">
    Anonymous diagnostics: when analyzers return an empty result, the input
    text and which signals fired are sent to Sentry so the detectors can be
    improved. No IPs, cookies, or other PII are collected.
    <br/>
    Анонимная диагностика: при пустых результатах анализа твой ввод и список
    сработавших сигналов отправляются в Sentry, чтобы доработать детекторы.
    IP, cookies и прочее PII не собираем.
  </small>
  <a href="https://github.com/hleserg/atman">GitHub</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/hleserg/atman/blob/main/MANIFEST.md">Manifest</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/hleserg/atman/issues">Open an issue</a>
</div>
            """
        )

    demo.queue(max_size=2, default_concurrency_limit=1)
    return demo

if __name__ == "__main__":
    preload_models()
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )