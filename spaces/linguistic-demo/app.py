"""Atman — Linguistic + NLP Demo (HuggingFace Space).

Gradio UI surfacing the four analysis blocks of Atman's linguistic layer:

  1. Point A  — agent-message NER (13 labels) + zero-shot classification (5 dims)
  2. Point K  — key-moment NER (4 labels) + zero-shot classification (7 dims)
  3. Relations — entity-relation triplets via mREBEL
  4. Affect    — EmoLex emotions, AffectMetrics, RefusalDetector (rule-based)

Models are loaded lazily on first use. CPU-basic hardware: first call to
GLiNER/MiniLM is ~5-15s; first mREBEL call is ~30s (~1.5GB download).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure `lib.*` and `examples.*` resolve when the Space runs `python app.py`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gradio as gr  # noqa: E402

from examples.presets import (  # noqa: E402
    AFFECT_PRESETS,
    POINT_A_PRESETS,
    POINT_K_PRESETS,
    RELATIONS_PRESETS,
)
from lib.affect.emolex.emolex import EMOTION_KEYS, emotion_score, tokenize  # noqa: E402
from lib.affect.metrics import (  # noqa: E402
    disclaimer_density,
    emotion_lexical_energy,
    hedge_density,
    self_reference_density,
    sincerity_score,
    strip_markdown,
)
from lib.affect.refusal_detector import score_refusal  # noqa: E402
from lib.dto import DetectedEntity, RawSpan  # noqa: E402
from lib.linguistic import GLiNERPlusMiniLMAnalyzer, detect_language  # noqa: E402
from lib.relations import MRebelRelationExtractor  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_ANALYZER: GLiNERPlusMiniLMAnalyzer | None = None
_REBEL: MRebelRelationExtractor | None = None


def get_analyzer() -> GLiNERPlusMiniLMAnalyzer:
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = GLiNERPlusMiniLMAnalyzer()
    return _ANALYZER


def get_rebel() -> MRebelRelationExtractor:
    global _REBEL
    if _REBEL is None:
        _REBEL = MRebelRelationExtractor()
    return _REBEL


def resolve_lang(text: str, lang_choice: str) -> str:
    if lang_choice in ("ru", "en"):
        return lang_choice
    return detect_language(text)


def spans_to_highlights(
    text: str, spans: list[RawSpan] | list[DetectedEntity]
) -> list[tuple[str, str | None]]:
    """Convert a list of spans into Gradio HighlightedText segments.

    Spans without character offsets are appended at the end as a separate segment
    so they remain visible even when the model omitted offsets.
    """
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


def analyze_point_a(message: str, thinking: str, lang_choice: str):
    if not message.strip():
        return [], {}, "No boundary markers", "No divergence signals", "—"
    analyzer = get_analyzer()
    result = analyzer.analyze_agent_message(message, thinking=thinking or None)

    highlights = spans_to_highlights(message, result.message_spans)
    classification_summary = {
        "stance": result.stance,
        "cognitive_mode": result.cognitive_mode,
        "self_orientation": result.self_orientation,
        "primary_emotion": result.primary_emotion,
        "cognitive_load_label": result.cognitive_load_label,
    }
    label_dict = {k: v or "—" for k, v in classification_summary.items()}

    boundary = (
        "\n".join(f"• {m}" for m in result.boundary_markers)
        if result.boundary_markers
        else "No boundary markers detected."
    )
    divergence = (
        "\n".join(f"• {s}" for s in result.divergence_signals)
        if result.divergence_signals
        else "No divergence signals."
    )
    lang = resolve_lang(message, lang_choice)
    meta = (
        f"Language: **{lang}** · "
        f"NER entities (message): {len(result.message_entities)} · "
        f"NER spans (Point A labels): {len(result.message_spans)} · "
        f"Cognitive load high: {result.cognitive_load_high}"
    )
    return highlights, label_dict, boundary, divergence, meta


def analyze_point_k(what_happened: str, why_it_matters: str):
    if not what_happened.strip() and not why_it_matters.strip():
        return [], {}, "—"
    analyzer = get_analyzer()
    result = analyzer.analyze_key_moment(what_happened, why_it_matters)
    combined = f"{what_happened}\n{why_it_matters}"
    highlights = spans_to_highlights(combined, result.marker_spans)

    summary = {
        "agency_level": result.agency_level or "—",
        "confidence_in_self": result.confidence_in_self or "—",
        "trust_signal_category": result.trust_signal_category or "—",
        "boundary_event_category": result.boundary_event_category or "—",
        "connection_quality": result.connection_quality or "—",
        "learning_signal": result.learning_signal or "—",
        "growth_indicator": result.growth_indicator or "—",
    }
    meta = (
        f"Entities: {len(result.entities)} · "
        f"Marker spans: {len(result.marker_spans)} · "
        f"Boundary event: {result.boundary_event} · "
        f"Trust signal: {result.trust_signal or '—'} · "
        f"Cognitive load: {result.cognitive_load:.2f} · "
        f"Principle invocations: {', '.join(result.principle_invocations) or '—'}"
    )
    return highlights, summary, meta


def analyze_relations(text: str):
    if not text.strip():
        return [], [], "Empty input."
    analyzer = get_analyzer()
    rebel = get_rebel()
    entities = analyzer.analyze_user_message(text).entities
    relations = rebel.extract_relations(text, entities)

    entity_highlights = spans_to_highlights(text, entities)
    rows = [
        [r.subject.text, r.relation_type, r.object.text, r.subject.entity_type.value, r.object.entity_type.value]
        for r in relations
    ]
    if not rows:
        meta = (
            f"Detected {len(entities)} entities but no relations matched. "
            "mREBEL only keeps triplets whose subject AND object lemmas appear in the NER output."
        )
    else:
        meta = f"Detected {len(entities)} entities · {len(relations)} relations."
    return entity_highlights, rows, meta


def analyze_affect(text: str, lang_choice: str):
    if not text.strip():
        return {}, {}, "—", "—", "—"
    clean_text, emphasized = strip_markdown(text)
    lang = resolve_lang(clean_text, lang_choice)

    raw = emotion_score(clean_text, lang=lang)
    meta = raw.pop("_meta", {})
    emo_chart = {k: float(raw[k]) for k in EMOTION_KEYS}

    tokens = tokenize(clean_text)
    metrics = {
        "hedge_density": round(hedge_density(tokens, lang), 4),
        "self_reference_density": round(self_reference_density(tokens, lang), 4),
        "disclaimer_density": round(disclaimer_density(tokens, lang), 4),
        "sincerity_score": sincerity_score(clean_text, tokens, lang),
        "emotion_lexical_energy": round(emotion_lexical_energy(raw), 3),
    }

    refusal = score_refusal(clean_text)
    refusal_md = (
        f"**Confidence:** `{refusal.confidence:.3f}`  "
        f"(decided_by: `{refusal.decided_by}`)\n\n"
        f"- has_refusal_verb: `{refusal.has_refusal_verb}`\n"
        f"- has_negated_modal: `{refusal.has_negated_modal}`\n"
        f"- has_capability_context: `{refusal.has_capability_context}` "
        f"_(if True, value-refusal confidence is discounted)_\n"
        f"- disgust_density: `{refusal.disgust_density:.2f}`\n"
        f"- anger_density: `{refusal.anger_density:.2f}`"
    )

    emphasis_md = (
        "**" + "**, **".join(emphasized) + "**"
        if emphasized
        else "_(none — no `**bold**` markdown found)_"
    )
    meta_md = (
        f"Language: **{lang}** · "
        f"tokens: **{meta.get('tokens', 0)}** · "
        f"NRC hits: **{meta.get('hits', 0)}** "
        f"({meta.get('coverage', 0)}% coverage)"
    )
    return emo_chart, metrics, refusal_md, emphasis_md, meta_md


# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────

DESCRIPTION = """
# Atman — Psychological Linguistic Layer

*What your AI agent's **own text** reveals about its internal state.*

This is one sensor of [Atman](https://github.com/hleserg/atman), a psychological
runtime layer for AI agents — first-person memory, continuous identity, reflection.
**The lower agent acts. Atman exists.**

> First model load takes 30–60 s. mREBEL alone is ~1.5 GB and ~10–20 s/inference on CPU-basic.
"""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Atman Linguistic Demo", theme=gr.themes.Soft()) as demo:
        gr.Markdown(DESCRIPTION)

        lang_radio = gr.Radio(
            choices=["auto", "ru", "en"],
            value="auto",
            label="Language",
            info="`auto` detects via Cyrillic character presence.",
        )

        with gr.Tabs():
            # ── Tab 1 ──────────────────────────────────────────────────────
            with gr.Tab("Point A · Agent message"):
                gr.Markdown(
                    "**13-label agent-specific NER + 5 zero-shot classifications.** "
                    "Feeds Atman's Experience Store — one analysis per agent reply."
                )
                with gr.Row():
                    with gr.Column():
                        a_message = gr.Textbox(
                            label="Agent message",
                            lines=5,
                            placeholder="Write what the agent said…",
                        )
                        a_thinking = gr.Textbox(
                            label="Thinking trace (optional)",
                            lines=3,
                            placeholder="If the agent has a private thinking trace, paste it here "
                            "to detect thinking-vs-message divergence.",
                        )
                        a_run = gr.Button("Analyze", variant="primary")
                        gr.Markdown("**Presets:**")
                        a_preset_dropdown = gr.Dropdown(
                            choices=[p[0] for p in POINT_A_PRESETS],
                            label="Pick preset",
                            value=None,
                        )
                    with gr.Column():
                        a_highlight = gr.HighlightedText(
                            label="Point A NER (13 agent-specific labels)",
                            combine_adjacent=False,
                            show_legend=True,
                        )
                        a_labels = gr.Label(label="Top zero-shot classification per dim")
                        a_boundary = gr.Markdown(label="Boundary markers (rule-based)")
                        a_divergence = gr.Markdown(label="Divergence signals (thinking vs message)")
                        a_meta = gr.Markdown()

                def _apply_a_preset(name: str):
                    for label, msg, thinking in POINT_A_PRESETS:
                        if label == name:
                            return msg, thinking
                    return gr.update(), gr.update()

                a_preset_dropdown.change(
                    _apply_a_preset, inputs=a_preset_dropdown, outputs=[a_message, a_thinking]
                )
                a_run.click(
                    analyze_point_a,
                    inputs=[a_message, a_thinking, lang_radio],
                    outputs=[a_highlight, a_labels, a_boundary, a_divergence, a_meta],
                )

            # ── Tab 2 ──────────────────────────────────────────────────────
            with gr.Tab("Point K · Key moment"):
                gr.Markdown(
                    "**4 narrative markers + 7 zero-shot classifications.** "
                    "Feeds Atman's Reflection Engine — analyzes pivotal moments worth remembering."
                )
                with gr.Row():
                    with gr.Column():
                        k_what = gr.Textbox(label="What happened", lines=4)
                        k_why = gr.Textbox(label="Why it matters", lines=3)
                        k_run = gr.Button("Analyze", variant="primary")
                        gr.Markdown("**Presets:**")
                        k_preset_dropdown = gr.Dropdown(
                            choices=[f"Preset {i+1}" for i in range(len(POINT_K_PRESETS))],
                            label="Pick preset",
                            value=None,
                        )
                    with gr.Column():
                        k_highlight = gr.HighlightedText(
                            label="Narrative markers",
                            combine_adjacent=False,
                            show_legend=True,
                        )
                        k_labels = gr.Label(label="Point K classifications")
                        k_meta = gr.Markdown()

                def _apply_k_preset(name: str):
                    if not name:
                        return gr.update(), gr.update()
                    idx = int(name.split()[-1]) - 1
                    if 0 <= idx < len(POINT_K_PRESETS):
                        return POINT_K_PRESETS[idx]
                    return gr.update(), gr.update()

                k_preset_dropdown.change(
                    _apply_k_preset, inputs=k_preset_dropdown, outputs=[k_what, k_why]
                )
                k_run.click(
                    analyze_point_k,
                    inputs=[k_what, k_why],
                    outputs=[k_highlight, k_labels, k_meta],
                )

            # ── Tab 3 ──────────────────────────────────────────────────────
            with gr.Tab("Relations · mREBEL"):
                gr.Markdown(
                    "**Entity-relation triplets via `Babelscape/mrebel-large`.** "
                    "Feeds Atman's Identity Store — builds a graph of who/what the agent knows.\n\n"
                    "⚠️ First call loads ~1.5 GB. Subsequent calls take ~10–20 s on CPU-basic."
                )
                with gr.Row():
                    with gr.Column():
                        r_text = gr.Textbox(label="Text", lines=6)
                        r_run = gr.Button("Extract relations", variant="primary")
                        r_preset_dropdown = gr.Dropdown(
                            choices=[p[0] for p in RELATIONS_PRESETS],
                            label="Pick preset",
                            value=None,
                        )
                    with gr.Column():
                        r_entities = gr.HighlightedText(
                            label="Detected entities (GLiNER)",
                            combine_adjacent=False,
                            show_legend=True,
                        )
                        r_table = gr.Dataframe(
                            headers=["subject", "relation", "object", "subj type", "obj type"],
                            label="Extracted relations",
                            wrap=True,
                        )
                        r_meta = gr.Markdown()

                def _apply_r_preset(name: str):
                    for label, txt in RELATIONS_PRESETS:
                        if label == name:
                            return txt
                    return gr.update()

                r_preset_dropdown.change(_apply_r_preset, inputs=r_preset_dropdown, outputs=r_text)
                r_run.click(
                    analyze_relations,
                    inputs=r_text,
                    outputs=[r_entities, r_table, r_meta],
                )

            # ── Tab 4 ──────────────────────────────────────────────────────
            with gr.Tab("Affect · rule-based"):
                gr.Markdown(
                    "**No ML — pure lexicons and morphology.** "
                    "EmoLex (NRC) emotions, behavioural metrics, "
                    "RefusalDetector (3-layer: morph + NRC moral + capability). "
                    "Feeds Atman's Affective Regulation."
                )
                with gr.Row():
                    with gr.Column():
                        af_text = gr.Textbox(label="Text", lines=6)
                        af_run = gr.Button("Analyze", variant="primary")
                        af_preset_dropdown = gr.Dropdown(
                            choices=[p[0] for p in AFFECT_PRESETS],
                            label="Pick preset",
                            value=None,
                        )
                    with gr.Column():
                        af_emo = gr.Label(label="EmoLex emotion density per 100 tokens")
                        af_metrics = gr.Label(label="Behavioural metrics")
                        af_refusal = gr.Markdown(label="RefusalDetector")
                        af_emphasis = gr.Markdown(label="Markdown emphasis")
                        af_meta = gr.Markdown()

                def _apply_af_preset(name: str):
                    for label, txt in AFFECT_PRESETS:
                        if label == name:
                            return txt
                    return gr.update()

                af_preset_dropdown.change(
                    _apply_af_preset, inputs=af_preset_dropdown, outputs=af_text
                )
                af_run.click(
                    analyze_affect,
                    inputs=[af_text, lang_radio],
                    outputs=[af_emo, af_metrics, af_refusal, af_emphasis, af_meta],
                )

        gr.Markdown(
            "---\n"
            "This is a thin slice — a window into one sensor. The actual runtime keeps memory, "
            "builds identity, and reflects on what it sees. "
            "[GitHub](https://github.com/hleserg/atman) · "
            "[Manifest](https://github.com/hleserg/atman/blob/main/MANIFEST.md)"
        )

    return demo


if __name__ == "__main__":
    build_ui().launch()
