"""Validate a GLiNER2 NER training JSONL file against the T1 schema.

Usage:
    python -m atman.eval.gliner2.validate_jsonl eval/data/atman_ner_ru_train.jsonl

Exit code 0 = valid, 1 = errors found.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from atman.eval.gliner2.schema import NER_LABELS

VALID_LABELS = frozenset(NER_LABELS)


def validate_file(path: Path) -> bool:
    """Return True if file is valid; print errors and return False otherwise."""
    errors: list[str] = []
    label_counter: Counter[str] = Counter()
    n = 0

    with path.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            n += 1

            try:
                record = json.loads(raw)
            except json.JSONDecodeError as e:
                errors.append(f"line {lineno}: invalid JSON — {e}")
                continue

            if not isinstance(record, dict):
                errors.append(f"line {lineno}: expected object, got {type(record).__name__}")
                continue

            if "input" not in record:
                errors.append(f"line {lineno}: missing 'input' field")
            elif not isinstance(record["input"], str):
                errors.append(f"line {lineno}: 'input' must be a string")

            if "output" not in record:
                errors.append(f"line {lineno}: missing 'output' field")
                continue

            output = record["output"]
            if not isinstance(output, dict):
                errors.append(f"line {lineno}: 'output' must be an object")
                continue

            if "entities" not in output:
                errors.append(f"line {lineno}: 'output' missing 'entities'")
                continue

            entities = output["entities"]
            if not isinstance(entities, dict):
                errors.append(f"line {lineno}: 'entities' must be an object")
                continue

            unknown = set(entities.keys()) - VALID_LABELS
            if unknown:
                errors.append(
                    f"line {lineno}: unknown labels {sorted(unknown)} — not in T1 schema"
                )

            for label, mentions in entities.items():
                if label in VALID_LABELS:
                    if not isinstance(mentions, list):
                        errors.append(f"line {lineno}: entities['{label}'] must be a list")
                    else:
                        label_counter[label] += len(mentions)

            if "entity_descriptions" in output:
                descs = output["entity_descriptions"]
                if not isinstance(descs, dict):
                    errors.append(f"line {lineno}: 'entity_descriptions' must be an object")
                else:
                    unknown_desc = set(descs.keys()) - VALID_LABELS
                    if unknown_desc:
                        errors.append(
                            f"line {lineno}: entity_descriptions has unknown labels "
                            f"{sorted(unknown_desc)}"
                        )

            # Truncate error list to avoid overwhelming output
            if len(errors) >= 50:
                errors.append("… (too many errors, truncated)")
                break

    if errors:
        print(f"INVALID: {path}", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return False

    print(f"OK: {n} records validated — {path}")
    print("Label distribution:")
    for label in sorted(NER_LABELS):
        count = label_counter.get(label, 0)
        print(f"  {label:15s}  {count:6d}")
    print(f"Total entity mentions: {sum(label_counter.values())}")
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m atman.eval.gliner2.validate_jsonl <file.jsonl>", file=sys.stderr)
        sys.exit(1)

    ok = True
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            ok = False
            continue
        if not validate_file(path):
            ok = False

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
