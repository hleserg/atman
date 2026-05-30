#!/usr/bin/env python3
"""Generate synthetic Russian NER training data for Atman using Pioneer API.

Outputs eval/data/atman_ner_ru_synth.jsonl in GLiNER training format.

Usage:
    PIONEER_API_KEY=pio_sk_... python3 scripts/eval/generate_synthetic_ru.py

Each output line:
    {"tokenized_text": ["word1", "word2", ...], "ner": [[start, end, "label"], ...]}

NER span indices are 0-based, inclusive, referencing tokenized_text positions.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: uv pip install requests", file=sys.stderr)
    sys.exit(1)

PIONEER_BASE_URL = "https://api.pioneer.ai"
PIONEER_API_KEY = os.environ.get("PIONEER_API_KEY", "")

LABELS = [
    "person",
    "organization",
    "location",
    "date_time",
    "event",
    "project",
    "product",
    "activity",
    "profession",
    "health",
    "emotion_word",
    "money",
    "animal",
]

DOMAIN_DESCRIPTIONS = [
    (
        "Личные заметки и дневниковые записи на русском языке от первого лица. "
        "Автор пишет о повседневной жизни: работе в IT-компании или фрилансе, "
        "встречах с коллегами и друзьями, домашних питомцах, занятиях спортом, "
        "чтении книг, финансовых вопросах, планах на будущее. "
        "Стиль: разговорный, личный, с эмоциями."
    ),
    (
        "Фрагменты переписки и диалоги на русском языке. "
        "Люди обсуждают рабочие проекты, договариваются о встречах, "
        "делятся новостями о здоровье, рассказывают о событиях в жизни. "
        "Упоминаются конкретные люди, организации, места и даты. "
        "Стиль: неформальный, живой разговорный язык."
    ),
    (
        "Рефлексия и самоанализ на русском языке. "
        "Автор осмысляет пережитые события: увольнение или новую работу, "
        "отношения с близкими, личностный рост, болезни и выздоровление, "
        "достижения и провалы в проектах, эмоциональные состояния. "
        "Упоминаются конкретные люди, места, проекты и временные периоды. "
        "Стиль: вдумчивый, глубокий, личный."
    ),
]

OUTPUT_PATH = Path(__file__).parent.parent.parent / "eval" / "data" / "atman_ner_ru_synth.jsonl"

# examples per batch × number of domain description batches
EXAMPLES_PER_BATCH = 600
VALID_LABELS = set(LABELS)


def _tokenize_with_offsets(text: str) -> tuple[list[str], list[int]]:
    tokens: list[str] = []
    offsets: list[int] = []
    for m in re.finditer(r"\S+", text):
        tokens.append(m.group())
        offsets.append(m.start())
    return tokens, offsets


def _find_span(
    tokens: list[str],
    offsets: list[int],
    text: str,
    entity_text: str,
    search_from: int = 0,
) -> tuple[int, int] | None:
    """Find inclusive token-level [start, end] for entity_text substring in text."""
    idx = search_from
    while True:
        char_start = text.find(entity_text, idx)
        if char_start == -1:
            return None
        char_end = char_start + len(entity_text) - 1

        start_tok: int | None = None
        end_tok: int | None = None
        for i, (tok, off) in enumerate(zip(tokens, offsets)):
            tok_end = off + len(tok) - 1
            if start_tok is None and off <= char_start <= tok_end:
                start_tok = i
            if start_tok is not None and off <= char_end <= tok_end:
                end_tok = i
                break
            if off > char_end:
                break

        if start_tok is not None and end_tok is not None:
            return (start_tok, end_tok)
        idx = char_start + 1


def pioneer_to_gliner(row: dict) -> dict | None:
    """Convert a Pioneer NER row to GLiNER training format."""
    text: str = row.get("text", "")
    entities: list = row.get("entities", [])
    if not text.strip():
        return None

    tokens, offsets = _tokenize_with_offsets(text)
    if not tokens:
        return None

    ner_spans: list[list] = []
    seen_spans: set[tuple[int, int, str]] = set()

    for entry in entities:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        entity_text, label = entry
        if not entity_text or not isinstance(label, str):
            continue
        label = label.strip()
        if label not in VALID_LABELS:
            continue
        span = _find_span(tokens, offsets, text, entity_text)
        if span is None:
            continue
        key = (span[0], span[1], label)
        if key in seen_spans:
            continue
        seen_spans.add(key)
        ner_spans.append([span[0], span[1], label])

    return {"tokenized_text": tokens, "ner": ner_spans}


def _pioneer_headers() -> dict[str, str]:
    if not PIONEER_API_KEY:
        raise RuntimeError("PIONEER_API_KEY environment variable is not set")
    return {"Authorization": f"Bearer {PIONEER_API_KEY}", "Content-Type": "application/json"}


def _submit_job(dataset_name: str, num_examples: int, domain_description: str) -> str:
    resp = requests.post(
        f"{PIONEER_BASE_URL}/generate",
        headers=_pioneer_headers(),
        json={
            "task_type": "ner",
            "dataset_name": dataset_name,
            "num_examples": num_examples,
            "labels": LABELS,
            "domain_description": domain_description,
            "generation_profile": "balanced",
            "negative_ratio": 10,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["job_id"]


def _poll_job(job_id: str, max_wait: int = 900) -> str:
    start = time.monotonic()
    interval = 10
    while time.monotonic() - start < max_wait:
        resp = requests.get(
            f"{PIONEER_BASE_URL}/generate/jobs/{job_id}",
            headers=_pioneer_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        elapsed = time.monotonic() - start
        print(f"    [{elapsed:5.0f}s] {status}")
        sys.stdout.flush()
        if status in ("ready", "failed"):
            return status
        time.sleep(interval)
    return "timeout"


def _download_dataset(dataset_name: str) -> list[dict]:
    resp = requests.get(
        f"{PIONEER_BASE_URL}/felix/datasets/{dataset_name}/latest/download",
        headers=_pioneer_headers(),
        params={"format": "jsonl"},
        timeout=120,
    )
    resp.raise_for_status()
    rows: list[dict] = []
    for line in resp.text.strip().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def validate_jsonl(path: Path) -> tuple[int, list[str]]:
    """Validate GLiNER-format JSONL. Returns (valid_count, error_list)."""
    errors: list[str] = []
    count = 0
    with open(path, encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_num}: JSON error: {exc}")
                continue

            toks = row.get("tokenized_text")
            if not isinstance(toks, list) or not toks:
                errors.append(f"line {line_num}: missing or empty 'tokenized_text'")
                continue

            ner = row.get("ner")
            if not isinstance(ner, list):
                errors.append(f"line {line_num}: missing 'ner'")
                continue

            n = len(toks)
            for span in ner:
                if not isinstance(span, list) or len(span) != 3:
                    errors.append(f"line {line_num}: ner span must be [start, end, label]")
                    break
                s, e, lbl = span
                if not isinstance(s, int) or not isinstance(e, int):
                    errors.append(f"line {line_num}: span indices must be int")
                    break
                if s < 0 or e < s or e >= n:
                    errors.append(f"line {line_num}: span [{s},{e}] invalid for {n} tokens")
                    break
                if lbl not in VALID_LABELS:
                    errors.append(f"line {line_num}: unknown label '{lbl}'")
                    break
            else:
                count += 1
    return count, errors


def spot_check(path: Path, n: int = 30) -> None:
    print(f"\nSpot-check: first {n} examples\n{'─'*70}")
    with open(path, encoding="utf-8") as f:
        for i, raw in enumerate(f):
            if i >= n:
                break
            row = json.loads(raw.strip())
            tokens = row["tokenized_text"]
            ner = row["ner"]
            preview = " ".join(tokens[:12]) + ("…" if len(tokens) > 12 else "")
            entity_strs = [
                f"«{' '.join(tokens[s:e+1])}»→{lbl}" for s, e, lbl in ner[:3]
            ]
            extra = f" +{len(ner)-3}" if len(ner) > 3 else ""
            print(f"  [{i+1:3d}] {preview}")
            if entity_strs:
                print(f"       {', '.join(entity_strs)}{extra}")
    print()


def main() -> None:
    if not PIONEER_API_KEY:
        print("ERROR: PIONEER_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_examples: list[dict] = []
    timestamp = int(time.time())

    for batch_idx, domain_desc in enumerate(DOMAIN_DESCRIPTIONS, 1):
        dataset_name = f"atman-ner-ru-synth-v1-b{batch_idx}-{timestamp}"
        print(f"\nBatch {batch_idx}/{len(DOMAIN_DESCRIPTIONS)}: {dataset_name}")
        print(f"  Submitting {EXAMPLES_PER_BATCH} examples...")
        sys.stdout.flush()

        job_id = _submit_job(dataset_name, EXAMPLES_PER_BATCH, domain_desc)
        print(f"  job_id: {job_id}")
        print("  Polling...")
        sys.stdout.flush()

        status = _poll_job(job_id)
        if status != "ready":
            print(f"  ERROR: job ended with status={status}", file=sys.stderr)
            sys.exit(1)

        print(f"  Downloading dataset {dataset_name}...")
        rows = _download_dataset(dataset_name)
        print(f"  Downloaded: {len(rows)} raw rows")

        converted = 0
        for row in rows:
            gliner_row = pioneer_to_gliner(row)
            if gliner_row:
                all_examples.append(gliner_row)
                converted += 1
        print(f"  Converted: {converted} valid GLiNER rows")

    total = len(all_examples)
    print(f"\nTotal examples: {total}")
    if total < 1500:
        print(f"WARNING: {total} < 1500 required examples", file=sys.stderr)

    print(f"Writing to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print("Validating...")
    count, errors = validate_jsonl(OUTPUT_PATH)
    if errors:
        print(f"VALIDATION FAILED ({len(errors)} errors):")
        for err in errors[:30]:
            print(f"  {err}")
        sys.exit(1)

    print(f"✓ Validation passed: {count} examples")
    spot_check(OUTPUT_PATH, n=30)
    print(f"Done → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
