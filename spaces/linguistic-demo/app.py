"""Atman — Linguistic + NLP Demo (HuggingFace Space).
Gradio UI surfacing the four analysis blocks of Atman's linguistic layer.
Models are preloaded on startup. Warmup forces inference cache.
Progress bars removed for stability. Auto-language detection enabled.
"""
from __future__ import annotations
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
from lib.linguistic import GLiNERPlusMiniLMAnalyzer, detect_language
from lib.observability import capture_silent_exception, init_sentry_from_env, traced
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
    """Effective UI locale: auto defaults to English."""
    return "ru" if lang_choice == "ru" else "en"


def resolve_analysis_lang(text: str, lang_choice: str) -> str:
    if lang_choice in ("ru", "en"):
        return lang_choice
    return detect_language(text)


def maybe_switch_ui_lang(text: str, lang_choice: str) -> str:
    """In auto mode, switch UI to detected language when it differs from current UI."""
    if not text.strip() or lang_choice in ("ru", "en"):
        return lang_choice
    detected = detect_language(text)
    if detected != effective_ui_lang(lang_choice):
        return detected
    return "auto"

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
    if not message.strip():
        return [], {}, "—", "—", "—", lang_choice

    def _run():
        analyzer = get_analyzer()
        result = analyzer.analyze_agent_message(message, thinking=thinking or None)
        analysis_lang = resolve_analysis_lang(message, lang_choice)
        ui_lang = maybe_switch_ui_lang(message, lang_choice)
        ui = effective_ui_lang(ui_lang)
        strings = UI_STRINGS[ui]

        if result.message_spans:
            highlights = spans_to_highlights(message, result.message_spans)
        else:
            highlights = [(strings["no_highlights"], None)]

        classification_summary = {
            "stance": str(result.stance) if result.stance else "—",
            "cognitive_mode": str(result.cognitive_mode) if result.cognitive_mode else "—",
            "self_orientation": str(result.self_orientation) if result.self_orientation else "—",
            "primary_emotion": str(result.primary_emotion) if result.primary_emotion else "—",
            "cognitive_load_label": str(result.cognitive_load_label) if result.cognitive_load_label else "—",
        }

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
            f"🌐 Language: **{analysis_lang}** | 🏷️ NER: {len(result.message_entities)}"
            f" | 📏 Spans: {len(result.message_spans)} | ⚡ Load: {result.cognitive_load_high}"
        )
        return highlights, classification_summary, boundary, divergence, meta, ui_lang

    return _safe_analyze("point_a", _run)

@traced("nlp.point_k")
def analyze_point_k(what_happened: str, why_it_matters: str, lang_choice: str):
    if not what_happened.strip() and not why_it_matters.strip():
        return [], {}, "—", lang_choice

    def _run():
        analyzer = get_analyzer()
        result = analyzer.analyze_key_moment(what_happened, why_it_matters)
        combined = f"{what_happened}\n{why_it_matters}"
        analysis_lang = resolve_analysis_lang(combined, lang_choice)
        ui_lang = maybe_switch_ui_lang(combined, lang_choice)
        ui = effective_ui_lang(ui_lang)
        strings = UI_STRINGS[ui]
        highlights = spans_to_highlights(combined, result.marker_spans, strings["no_highlights"])

        summary = {
            "agency_level": str(result.agency_level) if result.agency_level else "—",
            "confidence_in_self": str(result.confidence_in_self) if result.confidence_in_self else "—",
            "trust_signal_category": str(result.trust_signal_category) if result.trust_signal_category else "—",
            "boundary_event_category": str(result.boundary_event_category) if result.boundary_event_category else "—",
            "connection_quality": str(result.connection_quality) if result.connection_quality else "—",
            "learning_signal": str(result.learning_signal) if result.learning_signal else "—",
            "growth_indicator": str(result.growth_indicator) if result.growth_indicator else "—",
        }
        meta = f"🌐 Language: **{analysis_lang}** | 📦 Entities: {len(result.entities)} | 📌 Markers: {len(result.marker_spans)} | 🚧 Event: {result.boundary_event}"
        return highlights, summary, meta, ui_lang

    return _safe_analyze("point_k", _run)

@traced("nlp.relations_mrebel")
def analyze_relations(text: str, lang_choice: str):
    if not text.strip():
        return [], [], "Empty input.", lang_choice

    def _run():
        analyzer = get_analyzer()
        rebel = get_rebel()
        entities = analyzer.analyze_user_message(text).entities
        relations = rebel.extract_relations(text, entities)
        analysis_lang = resolve_analysis_lang(text, lang_choice)
        ui_lang = maybe_switch_ui_lang(text, lang_choice)
        ui = effective_ui_lang(ui_lang)
        strings = UI_STRINGS[ui]
        entity_highlights = spans_to_highlights(text, entities, strings["no_highlights"])
        rows = [[r.subject.text, r.relation_type, r.object.text, r.subject.entity_type.value, r.object.entity_type.value] for r in relations]
        meta = f"🌐 Language: **{analysis_lang}** | 📦 Entities: {len(entities)} | 🔗 Relations: {len(relations)}" if rows else f"🌐 Language: **{analysis_lang}** | 📦 {len(entities)} entities found, but no relations matched schema."
        return entity_highlights, rows, meta, ui_lang

    return _safe_analyze("relations", _run)

@traced("nlp.affect_rules")
def analyze_affect(text: str, lang_choice: str):
    if not text.strip():
        return {}, "—", "—", "—", "—", lang_choice

    def _run():
        clean_text, emphasized = strip_markdown(text)
        analysis_lang = resolve_analysis_lang(clean_text, lang_choice)
        ui_lang = maybe_switch_ui_lang(clean_text, lang_choice)
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
        refusal_md = f"**Confidence:** `{refusal.confidence:.3f}` ({refusal.decided_by})\n- refusal_verb: `{refusal.has_refusal_verb}`\n- disgust/anger: `{refusal.disgust_density:.2f}` / `{refusal.anger_density:.2f}`"
        emphasis_md = "**" + "**, **".join(emphasized) + "**" if emphasized else "_(none)_"
        meta_md = f"🌐 Language: **{analysis_lang}** | 📝 Tokens: **{meta.get('tokens', 0)}** | 🎯 NRC Hits: **{meta.get('hits', 0)}**"
        return emo_chart, metrics_md, refusal_md, emphasis_md, meta_md, ui_lang

    return _safe_analyze("affect", _run)

def warmup_models():
    global _ANALYZER, _REBEL
    if _ANALYZER is not None and _REBEL is not None:
        return "✅ Models already warmed up and ready."
    try:
        get_analyzer().analyze_agent_message("Warmup test.")
        get_rebel().extract_relations("Warmup test.", [])
        return "✅ Models warmed up successfully. Inference cache is hot."
    except Exception as e:
        return f"❌ Warmup failed: {e}"

# ──────────────────────────────────────────────────────────────────────────────
# Localization & UI Builder
# ──────────────────────────────────────────────────────────────────────────────
UI_STRINGS = {
    "en": {
        "warmup_btn": "🔥 Warmup Models",
        "warmup_log": "⏸️ Status: Waiting...",
        "lang_info": "`auto` = English UI; detects language on analyze and switches UI when needed.",
        "analyze_btn": "▶️ Analyze",
        "extract_relations_btn": "▶️ Extract relations",
        "point_a_tab": "Point A · Agent Message",
        "point_k_tab": "Point K · Key Moment",
        "relations_tab": "Relations · mREBEL",
        "affect_tab": "Affect · Rule-based",
        "presets": "**📥 Presets:**",
        "preset_label": "Pick preset",
        "no_highlights": "No psychological markers detected.",
        "no_boundary": "No boundary markers detected.",
        "no_divergence": "No divergence between thinking and message.",
        "no_thinking_trace": "Provide a thinking trace to compare against the message.",
        "boundary_title": "🚧 Boundary & Resistance Markers (Rule-Based)",
        "divergence_title": "🔍 Thinking vs Message Divergence",
        "meta_title": "📊 System Metadata",
    },
    "ru": {
        "warmup_btn": "🔥 Прогреть модели",
        "warmup_log": "⏸️ Статус: Ожидание...",
        "lang_info": "`auto` = английский UI; при анализе определяет язык и переключает интерфейс.",
        "analyze_btn": "▶️ Анализировать",
        "extract_relations_btn": "▶️ Извлечь связи",
        "point_a_tab": "Point A · Сообщение агента",
        "point_k_tab": "Point K · Ключевой момент",
        "relations_tab": "Связи · mREBEL",
        "affect_tab": "Аффект · Правила",
        "presets": "**📥 Пресеты:**",
        "preset_label": "Выберите пресет",
        "no_highlights": "Психологические маркеры не найдены.",
        "no_boundary": "Маркеры границ не найдены.",
        "no_divergence": "Расхождений между мыслями и сообщением нет.",
        "no_thinking_trace": "Добавьте thinking trace для сравнения с сообщением.",
        "boundary_title": "🚧 Маркеры границ и сопротивления (Правила)",
        "divergence_title": "🔍 Расхождение мыслей и сообщения",
        "meta_title": "📊 Метаданные системы",
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
        gr.update(choices=preset_labels(POINT_A_PRESETS, target), value=None, label=s["preset_label"]),
        gr.update(choices=preset_labels(POINT_K_PRESETS, target), value=None, label=s["preset_label"]),
        gr.update(choices=preset_labels(RELATIONS_PRESETS, target), value=None, label=s["preset_label"]),
        gr.update(choices=preset_labels(AFFECT_PRESETS, target), value=None, label=s["preset_label"]),
    ]


def _attach_ui_language_updates(handler):
    """Apply UI locale using handler's returned ui_lang (avoids stale lang_radio in .then())."""

    def wrapped(*args):
        *content, ui_lang = handler(*args)
        return (*content, *update_ui_language(ui_lang))

    return wrapped

def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Atman Linguistic Demo", theme=gr.themes.Soft()) as demo:
        gr.Markdown("Atman — Psychological Telemetry for AI Agents")
        
        lang_radio = gr.Radio(
            choices=["auto", "ru", "en"], value="auto", label="Interface Language",
            info=UI_STRINGS["en"]["lang_info"]
        )
        
        with gr.Row():
            warmup_btn = gr.Button(UI_STRINGS["en"]["warmup_btn"], variant="secondary")
            warmup_log = gr.Textbox(label="Status", interactive=False, lines=1, value=UI_STRINGS["en"]["warmup_log"])
            
        warmup_btn.click(fn=warmup_models, outputs=warmup_log)

        with gr.Tabs():
            # ── Tab 1 ──────────────────────────────────────────────────────
            with gr.Tab(UI_STRINGS["en"]["point_a_tab"]) as tab_a:
                with gr.Row():
                    with gr.Column():
                        a_message = gr.Textbox(label="Agent message", lines=5, placeholder="What the agent said…")
                        a_thinking = gr.Textbox(label="Thinking trace (optional)", lines=3)
                        a_run = gr.Button(UI_STRINGS["en"]["analyze_btn"], variant="primary")
                        gr.Markdown(UI_STRINGS["en"]["presets"])
                        a_preset = gr.Dropdown(
                            choices=preset_labels(POINT_A_PRESETS, "en"),
                            label=UI_STRINGS["en"]["preset_label"],
                        )
                    with gr.Column():
                        a_highlight = gr.HighlightedText(label="Point A NER (13 psychological labels)", combine_adjacent=False, show_legend=True)
                        a_labels = gr.JSON(label="🧠 Zero-Shot Classification Results", value={})
                        
                        with gr.Group():
                            gr.Markdown("### 📑 Detailed Analysis Report")
                            a_boundary_hdr = gr.Markdown(value=UI_STRINGS["en"]["boundary_title"])
                            a_boundary = gr.Markdown(value="—")
                            a_divergence_hdr = gr.Markdown(value=UI_STRINGS["en"]["divergence_title"])
                            a_divergence = gr.Markdown(value="—")
                            a_meta_hdr = gr.Markdown(value=UI_STRINGS["en"]["meta_title"])
                            a_meta = gr.Markdown(value="—")

                def _apply_a_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update(), gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_point_a(locale, name)
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
                with gr.Row():
                    with gr.Column():
                        k_what = gr.Textbox(label="What happened", lines=4)
                        k_why = gr.Textbox(label="Why it matters", lines=3)
                        k_run = gr.Button(UI_STRINGS["en"]["analyze_btn"], variant="primary")
                        gr.Markdown(UI_STRINGS["en"]["presets"])
                        k_preset = gr.Dropdown(
                            choices=preset_labels(POINT_K_PRESETS, "en"),
                            label=UI_STRINGS["en"]["preset_label"],
                        )
                    with gr.Column():
                        k_highlight = gr.HighlightedText(label="Narrative markers", combine_adjacent=False, show_legend=True)
                        k_labels = gr.JSON(label="🧠 Key Moment Classifications", value={})
                        k_meta = gr.Markdown(value=UI_STRINGS["en"]["meta_title"])
                def _apply_k_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update(), gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_point_k(locale, name)
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
                with gr.Row():
                    with gr.Column():
                        r_text = gr.Textbox(label="Text", lines=6)
                        r_run = gr.Button(UI_STRINGS["en"]["extract_relations_btn"], variant="primary")
                        r_preset = gr.Dropdown(
                            choices=preset_labels(RELATIONS_PRESETS, "en"),
                            label=UI_STRINGS["en"]["preset_label"],
                        )
                    with gr.Column():
                        r_entities = gr.HighlightedText(label="Detected entities", combine_adjacent=False, show_legend=True)
                        r_table = gr.Dataframe(headers=["subject", "relation", "object", "subj type", "obj type"], label="Extracted relations", wrap=True)
                        r_meta = gr.Markdown(value=UI_STRINGS["en"]["meta_title"])
                def _apply_r_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_relations(locale, name)
                    return found if found is not None else gr.update()
                r_preset.change(
                    _apply_r_preset,
                    inputs=[r_preset, lang_radio],
                    outputs=r_text,
                )

            # ── Tab 4 ──────────────────────────────────────────────────────
            with gr.Tab(UI_STRINGS["en"]["affect_tab"]) as tab_af:
                with gr.Row():
                    with gr.Column():
                        af_text = gr.Textbox(label="Text", lines=6)
                        af_run = gr.Button(UI_STRINGS["en"]["analyze_btn"], variant="primary")
                        af_preset = gr.Dropdown(
                            choices=preset_labels(AFFECT_PRESETS, "en"),
                            label=UI_STRINGS["en"]["preset_label"],
                        )
                    with gr.Column():
                        af_emo = gr.Label(label="EmoLex emotion density", num_top_classes=10)
                        af_metrics = gr.Markdown(label="Behavioural metrics")
                        af_refusal = gr.Markdown(label="RefusalDetector")
                        af_emphasis = gr.Markdown(label="Markdown emphasis")
                        af_meta = gr.Markdown(value=UI_STRINGS["en"]["meta_title"])
                def _apply_af_preset(name: str, lang_choice: str):
                    if not name:
                        return gr.update()
                    locale = effective_ui_lang(lang_choice)
                    found = lookup_affect(locale, name)
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
        ]
        lang_radio.change(update_ui_language, inputs=lang_radio, outputs=ui_lang_outputs)

        a_run.click(
            _attach_ui_language_updates(analyze_point_a),
            inputs=[a_message, a_thinking, lang_radio],
            outputs=[a_highlight, a_labels, a_boundary, a_divergence, a_meta] + ui_lang_outputs,
        )
        k_run.click(
            _attach_ui_language_updates(analyze_point_k),
            inputs=[k_what, k_why, lang_radio],
            outputs=[k_highlight, k_labels, k_meta] + ui_lang_outputs,
        )
        r_run.click(
            _attach_ui_language_updates(analyze_relations),
            inputs=[r_text, lang_radio],
            outputs=[r_entities, r_table, r_meta] + ui_lang_outputs,
        )
        af_run.click(
            _attach_ui_language_updates(analyze_affect),
            inputs=[af_text, lang_radio],
            outputs=[af_emo, af_metrics, af_refusal, af_emphasis, af_meta] + ui_lang_outputs,
        )

        gr.Markdown("---\n[GitHub](https://github.com/hleserg/atman) · [Manifest](https://github.com/hleserg/atman/blob/main/MANIFEST.md)")

    demo.queue(max_size=2, default_concurrency_limit=1)
    return demo

if __name__ == "__main__":
    preload_models()
    demo = build_ui()
    demo.launch()
    demo.launch(server_name="0.0.0.0", server_port=7860)