"""Download MalakhovIlya/RuNNE and convert to GLiNER2 NER training format.

Usage:
    python -m atman.eval.gliner2.convert_runne [--output-dir eval/data] [--val-ratio 0.1] [--seed 42]

Output files:
    <output-dir>/atman_ner_ru_train.jsonl
    <output-dir>/atman_ner_ru_val.jsonl

Each line:
    {"input": "...", "output": {"entities": {label: [span, ...]}, "entity_descriptions": {label: "..."}}}

Only spans mapped to T1 labels are kept; examples with no T1 entities are
discarded so the model does not learn "always predict nothing".

Dataset format (MalakhovIlya/RuNNE):
    Each example has {"id": ..., "text": str, "entities": ["start end TYPE", ...]}.
    start/end are UTF-16 character offsets into text.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from atman.eval.gliner2.schema import NER_LABELS, NEREL_TO_T1


def _parse_entity_str(ent_str: str) -> tuple[int, int, str]:
    """Parse "start end TYPE" string into (start, end, type)."""
    parts = ent_str.split()
    return int(parts[0]), int(parts[1]), parts[2]


def _example_to_gliner2(
    text: str, entity_strs: list[str]
) -> dict[str, Any] | None:
    """Build a GLiNER2 training record, returning None if no T1 entities."""
    entities: dict[str, list[str]] = defaultdict(list)

    for ent_str in entity_strs:
        start, end, nerel_type = _parse_entity_str(ent_str)
        t1_label = NEREL_TO_T1.get(nerel_type)
        if t1_label is None:
            continue
        surface = text[start:end].strip()
        if not surface:
            continue
        if surface not in entities[t1_label]:
            entities[t1_label].append(surface)

    if not entities:
        return None

    entity_descriptions = {label: NER_LABELS[label] for label in entities}

    return {
        "input": text,
        "output": {
            "entities": dict(entities),
            "entity_descriptions": entity_descriptions,
        },
    }


def convert_dataset(
    output_dir: Path,
    val_ratio: float = 0.1,
    seed: int = 42,
) -> tuple[int, int, Counter[str]]:
    """Download, convert, split, write.  Returns (n_train, n_val, label_counter)."""
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: 'datasets' not installed. Run: pip install atman[eval]", file=sys.stderr)
        sys.exit(1)

    print("Downloading MalakhovIlya/RuNNE …")
    ds = load_dataset("MalakhovIlya/RuNNE", trust_remote_code=True)

    all_records: list[dict[str, Any]] = []
    label_counter: Counter[str] = Counter()

    splits_to_process = list(ds.keys())
    print(f"Available splits: {splits_to_process}")

    for split_name in splits_to_process:
        split_ds = ds[split_name]
        print(f"Processing split '{split_name}' ({len(split_ds)} examples) …")
        kept = 0

        for example in split_ds:
            text: str = example["text"]
            entity_strs: list[str] = example.get("entities", [])

            record = _example_to_gliner2(text, entity_strs)
            if record is None:
                continue

            for label, mentions in record["output"]["entities"].items():
                label_counter[label] += len(mentions)

            all_records.append(record)
            kept += 1

        print(f"  → kept {kept} / {len(split_ds)} examples")

    if not all_records:
        print("ERROR: no records after conversion — check dataset format.", file=sys.stderr)
        sys.exit(1)

    # Shuffle + split
    rng = random.Random(seed)
    rng.shuffle(all_records)
    n_val = max(1, int(len(all_records) * val_ratio))
    val_records = all_records[:n_val]
    train_records = all_records[n_val:]

    output_dir.mkdir(parents=True, exist_ok=True)

    train_path = output_dir / "atman_ner_ru_train.jsonl"
    val_path = output_dir / "atman_ner_ru_val.jsonl"

    for path, records in [(train_path, train_records), (val_path, val_records)]:
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nDone: {len(train_records)} train, {len(val_records)} val records.")
    print(f"Wrote: {train_path}")
    print(f"Wrote: {val_path}")

    return len(train_records), len(val_records), label_counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert RuNNE → GLiNER2 JSONL")
    parser.add_argument(
        "--output-dir", default="eval/data", help="Output directory (default: eval/data)"
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.1, help="Validation fraction (default: 0.1)"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    n_train, n_val, label_counter = convert_dataset(
        output_dir=Path(args.output_dir),
        val_ratio=args.val_ratio,
        seed=args.seed,
    )

    print("\nLabel distribution (all splits combined):")
    total = sum(label_counter.values())
    for label, count in sorted(label_counter.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {label:15s}  {count:6d}  ({pct:.1f}%)")

    print(f"\nTotal entity mentions: {total}")
    print(f"Total records: {n_train + n_val}  (train={n_train}, val={n_val})")


if __name__ == "__main__":
    main()
