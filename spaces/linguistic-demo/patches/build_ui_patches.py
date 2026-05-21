"""Atman — Linguistic Demo · Gradio 6 build_ui() surgical patches.

This is NOT a drop-in app.py. These are the SURGICAL EDITS to apply to your
existing `spaces/linguistic-demo/app.py` on branch `agent/worker-1`.

For each section below:
  • the BEFORE block shows the existing code (matches current app.py)
  • the AFTER block shows what to replace it with
  • only elem_id / elem_classes / gr.Column wrappers are added — function
    signatures, callback wiring, ui_lang_outputs order are UNTOUCHED

──────────────────────────────────────────────────────────────────────────────
PRE-FLIGHT: import the theme + css before `def build_ui()`
──────────────────────────────────────────────────────────────────────────────

# At the top of app.py (after `import gradio as gr`), add:

from theme import theme
from pair_diagram import POINT_A_PAIR, POINT_K_PAIR, RELATIONS_PAIR, AFFECT_PAIR

with open(_HERE / "style.css") as _f:
    css = _f.read()

# Pre-rendered pair diagrams for each tab's About accordion.
# (Defined in pair_diagram.py — these are inline-HTML snippets.)
#     POINT_A_PAIR     → "Point A → Experience Store"
#     POINT_K_PAIR     → "Point K → Reflection Engine"
#     RELATIONS_PAIR   → "Relations → Identity Store"
#     AFFECT_PAIR      → "Affect → Affective Regulation"


──────────────────────────────────────────────────────────────────────────────
PATCH 1 — `gr.Blocks(...)` signature
──────────────────────────────────────────────────────────────────────────────

# BEFORE
with gr.Blocks(title="Atman Linguistic Demo") as demo:
    gr.Markdown("# Atman — Psychological Telemetry for AI Agents")

# AFTER
with gr.Blocks(title="Atman Linguistic Demo", theme=theme, css=css) as demo:
    with gr.Column(elem_id="atman-hero"):
        gr.Markdown("# Atman — Psychological Telemetry for AI Agents")


──────────────────────────────────────────────────────────────────────────────
PATCH 2 — header_md + diagram + lang_radio (move inside the hero column)
──────────────────────────────────────────────────────────────────────────────

# BEFORE  (still inside Blocks, outside any Column)
header_md = gr.Markdown(value=UI_STRINGS["en"]["header_blurb"])

diagram_path = _HERE / "assets" / "runtime-diagram.png"
if diagram_path.exists():
    gr.Image(
        value=str(diagram_path),
        show_label=False,
        interactive=False,
        container=False,
        height=320,
    )

lang_radio = gr.Radio(
    choices=["en", "ru"], value="en", label="Interface Language",
    info=UI_STRINGS["en"]["lang_info"]
)

# AFTER  (inside the `with gr.Column(elem_id="atman-hero"):` started in patch 1)
    header_md = gr.Markdown(
        value=UI_STRINGS["en"]["header_blurb"],
        elem_id="atman-header-md",
    )

    diagram_path = _HERE / "assets" / "runtime-diagram.png"
    if diagram_path.exists():
        gr.Image(
            value=str(diagram_path),
            show_label=False,
            interactive=False,
            container=False,
            height=320,
            elem_id="atman-diagram",
        )

    lang_radio = gr.Radio(
        choices=["en", "ru"], value="en", label="Interface Language",
        info=UI_STRINGS["en"]["lang_info"],
        elem_id="atman-lang",
    )

# Then de-indent back: everything that follows (warmup row, tabs, footer)
# stays at the same level as before — only the title/header/diagram/lang block
# is wrapped in the hero column.


──────────────────────────────────────────────────────────────────────────────
PATCH 3 — warmup row
──────────────────────────────────────────────────────────────────────────────

# BEFORE
with gr.Row():
    warmup_btn = gr.Button(UI_STRINGS["en"]["warmup_btn"], variant="secondary")
    warmup_log = gr.Textbox(label="Status", interactive=False, lines=1,
                            value=UI_STRINGS["en"]["warmup_log"])

# AFTER
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


──────────────────────────────────────────────────────────────────────────────
PATCH 4 — Tab 1 (Point A · Agent Message): About accordion + Report group
──────────────────────────────────────────────────────────────────────────────

# Replace the whole Tab 1 body with this. Logic identical; new elem_id/
# elem_classes, plus the `gr.Group(elem_classes=["atman-report-group"])`
# wrapper around the 6 detail-report Markdown blocks.

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
            a_labels = gr.JSON(
                label="🧠 Zero-Shot Classification Results", value={},
                elem_id="a-labels",
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


──────────────────────────────────────────────────────────────────────────────
PATCH 5 — Tab 2 (Point K · Key Moment): About accordion + elem_ids
──────────────────────────────────────────────────────────────────────────────

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
            k_why  = gr.Textbox(label="Why it matters", lines=3, elem_id="k-why")
            k_run  = gr.Button(
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
            k_labels = gr.JSON(
                label="🧠 Key Moment Classifications", value={},
                elem_id="k-labels",
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


──────────────────────────────────────────────────────────────────────────────
PATCH 6 — Tab 3 (Relations · mREBEL)
──────────────────────────────────────────────────────────────────────────────

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
            r_run  = gr.Button(
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
    r_preset.change(_apply_r_preset, inputs=[r_preset, lang_radio], outputs=r_text)


──────────────────────────────────────────────────────────────────────────────
PATCH 7 — Tab 4 (Affect · Rule-based)
──────────────────────────────────────────────────────────────────────────────

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
            af_run  = gr.Button(
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
    af_preset.change(_apply_af_preset, inputs=[af_preset, lang_radio], outputs=af_text)


──────────────────────────────────────────────────────────────────────────────
PATCH 8 — Footer (final `gr.Markdown(...)` before `demo.queue(...)`)
──────────────────────────────────────────────────────────────────────────────

# BEFORE
gr.Markdown(
    "---\n"
    "_My first project in AI/ML — feedback on models, algorithms, or "
    "architecture is genuinely welcome._\n\n"
    "[GitHub](https://github.com/hleserg/atman) · "
    "[Manifest](https://github.com/hleserg/atman/blob/main/MANIFEST.md) · "
    "[Open an issue](https://github.com/hleserg/atman/issues)"
)

# AFTER
gr.HTML(
    '''
<div id="atman-footer">
  <em>My first project in AI/ML — feedback on models, algorithms,
      or architecture is genuinely welcome.</em>
  <a href="https://github.com/hleserg/atman">GitHub</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/hleserg/atman/blob/main/MANIFEST.md">Manifest</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/hleserg/atman/issues">Open an issue</a>
</div>
    '''
)


──────────────────────────────────────────────────────────────────────────────
PATCH 9 — drop the launch-time theme override
──────────────────────────────────────────────────────────────────────────────

# BEFORE
if __name__ == "__main__":
    preload_models()
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(),     # <-- silently overrides our theme
    )

# AFTER
if __name__ == "__main__":
    preload_models()
    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )


──────────────────────────────────────────────────────────────────────────────
NOT TOUCHED (do not change)
──────────────────────────────────────────────────────────────────────────────

  • UI_STRINGS dict — all localized labels stay as-is (emoji included).
  • update_ui_language() — every gr.update() return preserved, in order.
  • ui_lang_outputs list — order must keep matching update_ui_language().
  • All analyze_* / warmup_models / _apply_*_preset bodies.
  • All .click() / .change() inputs= and outputs= lists.
  • demo.queue(max_size=2, default_concurrency_limit=1) — unchanged.
"""
