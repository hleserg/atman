"""Zero-shot GLiNER2 baseline evaluation for Russian NER (T2 / HLE-379).

Run:
    python -m atman.eval.gliner2.baseline --model fastino/gliner2-multi-v1
    python -m atman.eval.gliner2.baseline --model urchade/gliner_multi-v2.1

Each run appends/updates its model entry in the output JSON file so both results
accumulate in eval/results/gliner2_baseline_ru.json.

Conclusion thresholds (per label schema, T1 / HLE-378):
    F1 > 0.7   → fine-tune опционален
    F1 0.4–0.7 → fine-tune нужен
    F1 < 0.4   → рассмотреть смену базовой модели

Model loading strategy:
    • fastino/gliner2-multi-v1 uses the GLiNER2 format → loaded via `gliner2` package.
    • urchade/gliner_multi-v2.1 uses standard GLiNER format → loaded via `gliner` package.
    The script auto-detects which package to use (tries gliner2 first, falls back to gliner).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
from rich.markup import escape
from rich.table import Table

from atman.eval.gliner2.dataset import LABELS, load_dataset
from atman.term import console, print_banner, print_err, print_info, print_ok, print_section

_DEFAULT_OUTPUT = Path("eval/results/gliner2_baseline_ru.json")
_DEFAULT_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Model loading — supports both GLiNER2 (fastino) and standard GLiNER (urchade)
# ---------------------------------------------------------------------------


def _load_gliner(model_id: str) -> tuple[Any, str]:
    """Load model; return (model, model_type) where model_type is 'gliner2' or 'gliner'."""
    # Try GLiNER2 first — required for fastino/gliner2-multi-v1 (config.json extractor format).
    try:
        from gliner2 import GLiNER2  # type: ignore[import-untyped]

        print_info(f"Loading {escape(model_id)} via gliner2 …")
        try:
            return GLiNER2.from_pretrained(model_id), "gliner2"
        except Exception as exc:
            print_info(f"gliner2 load failed ({exc}), falling back to gliner …")
    except ImportError:
        pass

    # Fall back to standard GLiNER — required for urchade/gliner_multi-v2.1 (gliner_config.json).
    try:
        from gliner import GLiNER  # type: ignore[import-untyped]

        print_info(f"Loading {escape(model_id)} via gliner …")
        return GLiNER.from_pretrained(model_id), "gliner"
    except ImportError:
        pass

    print_err("Neither gliner2 nor gliner is installed. Run: pip install 'atman[eval]'")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def _run_predictions(
    model: Any,
    model_type: str,
    dataset: list[dict[str, Any]],
    threshold: float,
) -> list[list[dict[str, Any]]]:
    all_preds: list[list[dict[str, Any]]] = []

    for ex in dataset:
        text: str = ex["text"]

        if model_type == "gliner2":
            result = model.extract_entities(
                text,
                LABELS,
                threshold=threshold,
                include_spans=True,
            )
            spans: list[dict[str, Any]] = []
            for label, entities in result.get("entities", {}).items():
                for ent in entities:
                    spans.append({"label": label, "start": ent["start"], "end": ent["end"]})
        else:
            predictions = model.predict_entities(text, LABELS, threshold=threshold)
            spans = [
                {"label": p["label"], "start": p["start"], "end": p["end"]} for p in predictions
            ]

        all_preds.append(spans)

    return all_preds


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _compute_metrics(
    gold: list[list[dict[str, Any]]],
    pred: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        from nervaluate import Evaluator  # type: ignore[import-untyped]
    except ImportError:
        print_err("nervaluate is not installed. Run: pip install 'atman[eval]'")
        sys.exit(1)

    evaluator = Evaluator(gold, pred, tags=LABELS)
    results = evaluator.evaluate()

    # nervaluate returns {"overall": {mode: EvaluationResult}, "entities": {tag: {mode: EvaluationResult}}, ...}
    strict = results["overall"]["strict"]
    overall = {
        "precision": round(float(strict.precision), 4),
        "recall": round(float(strict.recall), 4),
        "f1": round(float(strict.f1), 4),
    }

    per_entity: dict[str, dict[str, float]] = {}
    entities_by_tag = results.get("entities", {})
    for tag in LABELS:
        tag_strict = (entities_by_tag.get(tag) or {}).get("strict")
        if tag_strict is not None:
            per_entity[tag] = {
                "precision": round(float(tag_strict.precision), 4),
                "recall": round(float(tag_strict.recall), 4),
                "f1": round(float(tag_strict.f1), 4),
            }
        else:
            per_entity[tag] = {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    return {"overall": overall, "per_entity": per_entity}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _conclusion(f1: float) -> str:
    if f1 > 0.7:
        return "F1 > 0.7: fine-tune опционален"
    if f1 >= 0.4:
        return "F1 0.4–0.7: fine-tune нужен"
    return "F1 < 0.4: рассмотреть смену базовой модели"


def _print_results(model_id: str, metrics: dict[str, Any]) -> None:
    overall = metrics["overall"]
    per_entity: dict[str, dict[str, float]] = metrics["per_entity"]

    print_section(f"Results — {escape(model_id)}")
    print_info(
        f"Overall  P={overall['precision']:.3f}  R={overall['recall']:.3f}  F1={overall['f1']:.3f}"
    )
    verdict = _conclusion(overall["f1"])
    if overall["f1"] > 0.7:
        console.print(f"[bold green]{escape(verdict)}[/bold green]")
    elif overall["f1"] >= 0.4:
        console.print(f"[bold yellow]{escape(verdict)}[/bold yellow]")
    else:
        console.print(f"[bold red]{escape(verdict)}[/bold red]")

    table = Table(title="Per-entity F1 (strict)", show_header=True, header_style="bold cyan")
    table.add_column("Entity", style="bold", no_wrap=True)
    table.add_column("Precision", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1", justify="right")

    for tag in sorted(per_entity):
        m = per_entity[tag]
        f1_val = m["f1"]
        f1_color = "green" if f1_val >= 0.7 else ("yellow" if f1_val >= 0.4 else "red")
        table.add_row(
            tag,
            f"{m['precision']:.3f}",
            f"{m['recall']:.3f}",
            f"[{f1_color}]{f1_val:.3f}[/{f1_color}]",
        )

    console.print(table)


def _save_results(
    output: Path,
    model_id: str,
    metrics: dict[str, Any],
    n_examples: int,
    threshold: float,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if output.exists() and output.stat().st_size > 0:
        with output.open(encoding="utf-8") as fh:
            existing = json.load(fh)

    existing[model_id] = {
        "model": model_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "threshold": threshold,
        "n_examples": n_examples,
        "overall": metrics["overall"],
        "per_entity": metrics["per_entity"],
        "conclusion": _conclusion(metrics["overall"]["f1"]),
    }

    with output.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=2)

    print_ok(f"Results saved → {output}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command(name="gliner2-baseline")
@click.option(
    "--model",
    required=True,
    help="GLiNER model ID from HuggingFace Hub (e.g. fastino/gliner2-multi-v1).",
)
@click.option(
    "--threshold",
    default=_DEFAULT_THRESHOLD,
    show_default=True,
    type=float,
    help="NER confidence threshold.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=_DEFAULT_OUTPUT,
    show_default=True,
    help="Path to output JSON file (merged across model runs).",
)
def main(model: str, threshold: float, output: Path) -> None:
    """Zero-shot GLiNER2 baseline evaluation on 130 Russian NER examples."""
    print_banner("GLiNER2 Baseline Eval", f"model={model}  threshold={threshold}")

    dataset = load_dataset()
    print_info(f"Dataset: {len(dataset)} examples, {len(LABELS)} labels")

    gliner_model, model_type = _load_gliner(model)
    print_info(f"Model type: {model_type}")

    gold_nerval = [
        [{"label": e["label"], "start": e["start"], "end": e["end"]} for e in ex["entities"]]
        for ex in dataset
    ]

    print_info("Running predictions …")
    pred_nerval = _run_predictions(gliner_model, model_type, dataset, threshold)

    metrics = _compute_metrics(gold_nerval, pred_nerval)

    _print_results(model, metrics)
    _save_results(output, model, metrics, len(dataset), threshold)


if __name__ == "__main__":
    main()
