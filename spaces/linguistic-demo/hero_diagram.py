"""Inline SVG hero diagram — 4 linguistic sensors → 4 runtime stores.

Embedded directly into the hero via gr.HTML(). No toolbar, no download
button, no chrome around it — pure inline SVG. Mirrors the spec mock
in `Atman Demo Visual Upgrade.html` (lines ~605–650).
"""
from __future__ import annotations

HERO_DIAGRAM = """
<div class="atman-hero-diagram">
  <svg viewBox="0 0 960 200" xmlns="http://www.w3.org/2000/svg" role="img"
       aria-label="Atman linguistic layer → runtime stores">
    <defs>
      <linearGradient id="atman-grad" x1="0" x2="1" y1="0" y2="0">
        <stop offset="0%" stop-color="#6366F1"></stop>
        <stop offset="100%" stop-color="#A78BFA"></stop>
      </linearGradient>
      <pattern id="atman-dots" x="0" y="0" width="6" height="6"
               patternUnits="userSpaceOnUse">
        <circle cx="1" cy="1" r="0.7" fill="currentColor" opacity="0.18"></circle>
      </pattern>
    </defs>
    <rect x="0" y="0" width="960" height="200" fill="url(#atman-dots)" color="#94A3B8"></rect>
    <g font-family="JetBrains Mono, monospace" font-size="11" font-weight="500">
      <g transform="translate(40 50)">
        <rect width="180" height="100" rx="10" fill="none" stroke="url(#atman-grad)" stroke-width="1.5"></rect>
        <text x="16" y="28" fill="currentColor" opacity="0.85">POINT A</text>
        <text x="16" y="50" fill="currentColor" opacity="0.55" font-size="10">13-label NER</text>
        <text x="16" y="66" fill="currentColor" opacity="0.55" font-size="10">5 zero-shot dims</text>
        <text x="16" y="86" fill="currentColor" opacity="0.4" font-size="9">→ Experience Store</text>
      </g>
      <g transform="translate(245 50)">
        <rect width="180" height="100" rx="10" fill="none" stroke="url(#atman-grad)" stroke-width="1.5"></rect>
        <text x="16" y="28" fill="currentColor" opacity="0.85">POINT K</text>
        <text x="16" y="50" fill="currentColor" opacity="0.55" font-size="10">7 narrative spans</text>
        <text x="16" y="66" fill="currentColor" opacity="0.55" font-size="10">7 zero-shot dims</text>
        <text x="16" y="86" fill="currentColor" opacity="0.4" font-size="9">→ Reflection Engine</text>
      </g>
      <g transform="translate(450 50)">
        <rect width="180" height="100" rx="10" fill="none" stroke="url(#atman-grad)" stroke-width="1.5"></rect>
        <text x="16" y="28" fill="currentColor" opacity="0.85">RELATIONS</text>
        <text x="16" y="50" fill="currentColor" opacity="0.55" font-size="10">mREBEL triplets</text>
        <text x="16" y="66" fill="currentColor" opacity="0.55" font-size="10">subj · rel · obj</text>
        <text x="16" y="86" fill="currentColor" opacity="0.4" font-size="9">→ Identity Store</text>
      </g>
      <g transform="translate(655 50)">
        <rect width="180" height="100" rx="10" fill="none" stroke="url(#atman-grad)" stroke-width="1.5"></rect>
        <text x="16" y="28" fill="currentColor" opacity="0.85">AFFECT</text>
        <text x="16" y="50" fill="currentColor" opacity="0.55" font-size="10">NRC EmoLex · metrics</text>
        <text x="16" y="66" fill="currentColor" opacity="0.55" font-size="10">refusal detector</text>
        <text x="16" y="86" fill="currentColor" opacity="0.4" font-size="9">→ Affective Regulation</text>
      </g>
    </g>
  </svg>
  <div class="atman-hero-diagram-caption">FIG. 01 — LINGUISTIC LAYER SENSORS → RUNTIME STORES</div>
</div>
"""
