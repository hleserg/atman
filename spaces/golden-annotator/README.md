---
title: Atman — Golden Set Annotator
emoji: 🏷️
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
tags:
  - annotation
  - ner
  - russian
  - dataset
  - gliner
---

# Atman — Golden Set Annotator

Click-only UI for hand-labelling the **held-out Russian golden test set**
(T5 / [HLE-382](https://linear.app/hleserg/issue/HLE-382)). Without an honest,
hand-labelled held-out set, all F1 numbers lie — synthetic data and NEREL are
not the Atman domain.

> **The lower agent acts. Atman exists.**

## Workflow

For each example:

1. **Read** the text.
2. **Check** the words that make up one entity (they must be contiguous).
3. **Click** the label button — the span is added and highlighted.
4. Repeat; if the example has no entities, press **«✅ Нет сущностей / пример готов»**.
5. Go to the next example.
6. When done, **«💾 Собрать и проверить»** and download the JSONL.

The legend (13 labels with descriptions + examples) and a boundary guide are
always on screen so you don't mislabel from memory.

## Labels — adapter `atman-ner-core` (13)

`person` · `organization` · `location` · `date_time` · `event` · `project` ·
`product` · `activity` · `profession` · `health` · `emotion_word` · `money` ·
`animal`

See `docs/eval/gliner2_label_schema.md` for the canonical definitions.

## Output format

GLiNER-format JSONL — byte-compatible with the synthetic generator
(`scripts/eval/generate_synthetic_ru.py`) and validated with the same rules:

```json
{"tokenized_text": ["word1", "word2"], "ner": [[0, 0, "person"]]}
```

Span indices are 0-based, inclusive. Tokenization is whitespace splitting, so
punctuation stays attached to a token (`"марафон."`). Export the result to
`eval/data/atman_ru_golden_test.jsonl`.

This set is **eval-only** — it must never enter any adapter's train split.

## Run locally

```bash
cd spaces/golden-annotator
pip install -r requirements.txt
python app.py
```
