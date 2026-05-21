"""Atman — Linguistic Demo · pair diagram helper.

A compact two-card flow diagram that goes inside each About-accordion:

    [ Point A ]  →  [ Experience Store ]
     agent message      episodic memory
     NER · 13 labels    write

Mirrors the larger architecture diagram. Drop into the accordion body via:

    with gr.Accordion(...):
        gr.HTML(pair_diagram(
            "Point A", "agent message", "NER · 13 labels",
            "Experience Store", "episodic memory", "write",
        ))
        gr.Markdown(value=UI_STRINGS["en"]["about_point_a"])

Light/dark aware — styling lives in style.css under `.apd-*`.

The arrow is rendered as CSS (a gradient bar + a triangular border-head) rather
than inline SVG — Gradio's HTML sanitizer strips <defs>/<linearGradient> in
some versions, which would leave the line invisible.
"""
from __future__ import annotations

import html


def pair_diagram(
    left_name: str,
    left_sub: str,
    left_tag: str,
    right_name: str,
    right_sub: str,
    right_tag: str,
) -> str:
    """Return inline HTML for one analysis → runtime pair card."""
    esc = html.escape
    return f"""
<div class="apd-pair" aria-label="{esc(left_name)} feeds {esc(right_name)}">
  <div class="apd-card apd-left">
    <span class="apd-stripe"></span>
    <div class="apd-card-body">
      <div class="apd-card-head">
        <div class="apd-name">{esc(left_name)}</div>
        <div class="apd-tag">{esc(left_tag)}</div>
      </div>
      <div class="apd-sub">{esc(left_sub)}</div>
    </div>
  </div>

  <div class="apd-arrow" aria-hidden="true">
    <span class="apd-arrow-line"></span>
    <span class="apd-arrow-head"></span>
  </div>

  <div class="apd-card apd-right">
    <span class="apd-stripe"></span>
    <div class="apd-card-body">
      <div class="apd-card-head">
        <div class="apd-name">{esc(right_name)}</div>
        <div class="apd-tag">{esc(right_tag)}</div>
      </div>
      <div class="apd-sub">{esc(right_sub)}</div>
    </div>
  </div>
</div>
"""


# Pre-rendered pair HTMLs for the 4 tabs — matches the Architecture Diagram order.
POINT_A_PAIR = pair_diagram(
    "Point A", "agent message", "NER · 13 labels",
    "Experience Store", "episodic memory", "write",
)
POINT_K_PAIR = pair_diagram(
    "Point K", "key moment", "zero-shot",
    "Reflection Engine", "consolidation", "trigger",
)
RELATIONS_PAIR = pair_diagram(
    "Relations", "mREBEL", "triplets",
    "Identity Store", "self-graph", "upsert",
)
AFFECT_PAIR = pair_diagram(
    "Affect", "rule-based", "lexicon",
    "Affective Regulation", "state vector", "update",
)
