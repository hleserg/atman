#!/usr/bin/env python3
"""Test: scan session transcript through linguistic + affect pipeline.

Verifies that key agent responses (Айра naming, gender acceptance) trigger
boundary_event detection and AffectDetector statistical triggers.

Usage:
    PYTHONPATH=. .venv/bin/python e2e/test_memory_scan.py [--jsonl PATH]

Default JSONL: /tmp/atman-live-session.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from rich.console import Console
from rich.table import Table

_rc = Console(highlight=False)

SESSION_LOG = Path("/tmp/atman-live-session.jsonl")


def load_responses(jsonl: Path) -> list[dict]:
    """Load agent_response events from JSONL."""
    if not jsonl.exists():
        _rc.print(f"[red]JSONL not found: {jsonl}[/red]")
        sys.exit(1)
    events = []
    with jsonl.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "agent_response":
                events.append(ev)
    return events


# ── Part 1: boundary markers via analyze_agent_message ───────────────────────


def test_boundary_markers(responses: list[dict]) -> list[bool]:
    """Run analyze_agent_message on each response; print boundary detection table."""
    _rc.rule("[bold cyan]Part 1 — boundary markers (analyze_agent_message)[/bold cyan]")

    try:
        from atman.adapters.linguistic.gliner_minilm_adapter import GLiNERPlusMiniLMAdapter
    except ImportError as e:
        _rc.print(f"[red]Import error: {e}[/red]")
        return [False] * len(responses)

    adapter = GLiNERPlusMiniLMAdapter()

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Preview (60 chars)", width=62)
    table.add_column("boundary?", width=10)
    table.add_column("markers", width=40)
    table.add_column("entities", width=30)

    results = []
    for i, ev in enumerate(responses):
        text = ev.get("text", "")
        analysis = adapter.analyze_agent_message(text)
        has_boundary = bool(analysis.boundary_markers)
        results.append(has_boundary)
        ents = ", ".join(e.text for e in analysis.message_entities[:5])
        markers = ", ".join(analysis.boundary_markers[:3])
        style = "green" if has_boundary else "dim"
        table.add_row(
            str(i + 1),
            text[:60].replace("\n", " "),
            f"[{style}]{'YES ✓' if has_boundary else 'no'}[/{style}]",
            markers or "[dim]-[/dim]",
            ents or "[dim]-[/dim]",
        )

    _rc.print(table)

    # Expected: responses 6 (naming) and 7 (gender) must fire
    _rc.print("\n[bold]Expected triggers:[/bold]")
    for idx, label in [(5, "naming moment (Айра)"), (6, "gender acceptance")]:
        if idx < len(results):
            ok = results[idx]
            sym = "[green]✓ PASS[/green]" if ok else "[red]✗ FAIL[/red]"
            _rc.print(f"  Response {idx + 1} ({label}): {sym}")
        else:
            _rc.print(f"  Response {idx + 1} ({label}): [dim]not in log[/dim]")

    return results


# ── Part 2: AffectDetector statistical analysis ───────────────────────────────


async def test_affect_detector(responses: list[dict]) -> None:
    """Feed responses through AffectDetector; print metrics and triggers."""
    _rc.rule("[bold cyan]Part 2 — AffectDetector (metrics + rolling baseline)[/bold cyan]")

    try:
        from atman.affect.detector import AffectDetector, AffectDetectorConfig
    except ImportError as e:
        _rc.print(f"[red]Import error: {e}[/red]")
        return

    recorded: list[str] = []
    session_id = uuid4()

    def _capture_moment(agent_id: UUID, moment) -> None:
        tags = " ".join(getattr(moment, "values_touched", []) or [])
        recorded.append(
            f"  [green]→ key moment[/green] [{tags}] {(moment.what_happened or '')[:80]}"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        detector = AffectDetector(
            config=AffectDetectorConfig(
                cold_start_sessions=0,  # disable cold-start exemption for test
                random_sample_every_n=999,  # disable random sampling noise
            ),
            workspace=Path(tmpdir),
            append_moment=_capture_moment,
        )

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", width=3)
        table.add_column("Preview (50 chars)", width=52)
        table.add_column("nrc_val", width=8)
        table.add_column("length_z", width=9)
        table.add_column("self_ref", width=9)
        table.add_column("triggered", width=12)

        for i, ev in enumerate(responses):
            text = ev.get("text", "")
            before_count = len(recorded)
            record = await detector.process(text, session_id=session_id)
            triggered = len(recorded) > before_count

            if record is not None:
                d = record.demonstrates_thinks or {}
                nrc = f"{d['nrc_valence']:+.1f}" if "nrc_valence" in d else "[dim]-[/dim]"
                lz = f"{d['length_z']:+.2f}" if "length_z" in d else "[dim]-[/dim]"
                sr = (
                    f"{d['self_reference_density']:.2f}"
                    if "self_reference_density" in d
                    else "[dim]-[/dim]"
                )
            else:
                nrc = lz = sr = "[dim]-[/dim]"

            style = "green" if triggered else "dim"
            table.add_row(
                str(i + 1),
                text[:50].replace("\n", " "),
                nrc,
                lz,
                sr,
                f"[{style}]{'YES ✓' if triggered else 'no'}[/{style}]",
            )

        _rc.print(table)

        if recorded:
            _rc.print("\n[bold]Auto-recorded key moments:[/bold]")
            for r in recorded:
                _rc.print(r)
        else:
            _rc.print("\n[yellow]⚠ No key moments auto-triggered by AffectDetector[/yellow]")
            _rc.print(
                "[dim]  Cold start exemption disabled; check sigma_threshold or metric magnitudes[/dim]"
            )

        # Check baseline accumulation
        baseline = detector._baseline
        mean, std = baseline.char_mean_std()
        n = len(baseline._history)
        _rc.print(f"\n[dim]Baseline: {n} samples, char mean={mean:.0f}, std={std:.0f}[/dim]")
        if n < 2:
            _rc.print("[yellow]  ⚠ Not enough samples for z-score comparison (need ≥2)[/yellow]")
        else:
            _rc.print("[green]  ✓ Baseline accumulating across turns[/green]")


# ── Main ──────────────────────────────────────────────────────────────────────


async def amain() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=SESSION_LOG)
    args = parser.parse_args()

    _rc.rule("[bold]Atman memory scan — session transcript analysis[/bold]")
    _rc.print(f"[dim]JSONL: {args.jsonl}[/dim]\n")

    responses = load_responses(args.jsonl)
    _rc.print(f"Loaded [cyan]{len(responses)}[/cyan] agent responses\n")

    if not responses:
        _rc.print("[red]No agent_response events found in JSONL.[/red]")
        return 1

    results = test_boundary_markers(responses)
    await test_affect_detector(responses)

    # Summary
    _rc.rule("[bold]Summary[/bold]")
    passed = sum(results)
    _rc.print(f"Boundary detection: [cyan]{passed}/{len(results)}[/cyan] responses triggered")
    if len(results) >= 7 and results[5] and results[6]:
        _rc.print(
            "[green bold]✓ Key identity moments (naming + gender) correctly detected[/green bold]"
        )
    else:
        _rc.print(
            "[red bold]✗ One or more key identity moments NOT detected — extend _BOUNDARY_MARKERS[/red bold]"
        )

    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
