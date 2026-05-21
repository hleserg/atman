"""Atman — Linguistic Demo · Gradio 6 theme.

Paste above build_ui() (or import: `from theme import theme`).
Pair with style.css via:

    with gr.Blocks(title="Atman Linguistic Demo", theme=theme, css=css) as demo:

IMPORTANT: also remove `theme=gr.themes.Soft()` from demo.launch() — it would
silently override this one.
"""
from __future__ import annotations

import gradio as gr

theme = gr.themes.Base(
    primary_hue="indigo",
    secondary_hue="violet",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "SF Mono", "Menlo", "monospace"],
).set(
    # ── Page surfaces ────────────────────────────────────────────────────
    body_background_fill="#FAFAFA",
    body_background_fill_dark="#0B0B14",            # indigo-tinted near-black
    body_text_color="#0F172A",
    body_text_color_dark="#E2E8F0",
    body_text_color_subdued="#64748B",
    body_text_color_subdued_dark="#94A3B8",

    # ── Block / card surfaces ────────────────────────────────────────────
    # Hits every Textbox, Markdown, HighlightedText, JSON, Dataframe, Label.
    block_background_fill="#FFFFFF",
    block_background_fill_dark="#13131F",           # one step up from page bg
    block_border_color="#E5E7EB",
    block_border_color_dark="#1F2937",
    block_border_width="1px",
    block_radius="12px",
    block_shadow="0 1px 2px rgba(15, 23, 42, 0.04)",
    block_shadow_dark="0 1px 2px rgba(0, 0, 0, 0.30)",
    block_padding="20px",
    block_label_text_color="#64748B",
    block_label_text_color_dark="#94A3B8",
    block_label_text_size="12px",
    block_label_text_weight="500",
    block_label_background_fill="transparent",      # kill the filled chip — restyled as eyebrow in CSS
    block_label_background_fill_dark="transparent",
    block_label_radius="4px",
    block_title_text_color="#0F172A",
    block_title_text_color_dark="#E2E8F0",
    block_title_text_weight="600",
    block_info_text_size="13px",
    block_info_text_color="#64748B",
    block_info_text_color_dark="#94A3B8",

    # ── Panels & tabs body ───────────────────────────────────────────────
    panel_background_fill="#FAFAFA",
    panel_background_fill_dark="#0B0B14",
    panel_border_color="#E5E7EB",
    panel_border_color_dark="#1F2937",
    panel_border_width="0px",                       # underline alone marks active tab

    # ── Inputs (Textbox, Dropdown) ───────────────────────────────────────
    input_background_fill="#FFFFFF",
    input_background_fill_dark="#13131F",
    input_background_fill_focus="#FFFFFF",
    input_background_fill_focus_dark="#13131F",
    input_border_color="#E5E7EB",
    input_border_color_dark="#1F2937",
    input_border_color_focus="#4F46E5",
    input_border_color_focus_dark="#6366F1",
    input_border_width="1px",
    input_radius="8px",
    input_padding="12px 14px",                      # wider hit area for dropdowns
    input_placeholder_color="#94A3B8",
    input_placeholder_color_dark="#64748B",
    input_shadow_focus="0 0 0 2px rgba(79, 70, 229, 0.28)",
    input_shadow_focus_dark="0 0 0 2px rgba(99, 102, 241, 0.36)",

    # ── Buttons ──────────────────────────────────────────────────────────
    button_primary_background_fill="#4F46E5",
    button_primary_background_fill_dark="#6366F1",  # brighter for dark-mode contrast
    button_primary_background_fill_hover="linear-gradient(135deg, #4F46E5 0%, #8B5CF6 100%)",
    button_primary_background_fill_hover_dark="linear-gradient(135deg, #6366F1 0%, #A78BFA 100%)",
    button_primary_text_color="#FFFFFF",
    button_primary_text_color_dark="#FFFFFF",
    button_primary_border_color="#4F46E5",
    button_primary_border_color_dark="#6366F1",
    button_secondary_background_fill="transparent",
    button_secondary_background_fill_dark="transparent",
    button_secondary_background_fill_hover="rgba(79, 70, 229, 0.08)",
    button_secondary_background_fill_hover_dark="rgba(99, 102, 241, 0.12)",
    button_secondary_text_color="#4F46E5",
    button_secondary_text_color_dark="#A5B4FC",
    button_secondary_border_color="#4F46E5",
    button_secondary_border_color_dark="#6366F1",
    button_large_padding="11px 20px",
    button_large_text_weight="500",
    button_large_radius="8px",
    button_shadow="none",                           # quiet at rest
    button_shadow_hover="0 2px 8px rgba(79, 70, 229, 0.18)",

    # ── Slider color (used by gr.Label progress fills in Affect tab) ─────
    slider_color="#4F46E5",
    slider_color_dark="#6366F1",

    # ── Border / radius / spacing tokens ─────────────────────────────────
    border_color_accent="#4F46E5",
    border_color_accent_dark="#6366F1",
    border_color_primary="#E5E7EB",
    border_color_primary_dark="#1F2937",
    radius_size=gr.themes.sizes.radius_md,
    spacing_size=gr.themes.sizes.spacing_md,
    layout_gap="24px",
)
