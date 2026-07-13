# E1 Evaluation Runner Framework

## Purpose

E1 introduces a minimal but runnable benchmark orchestration layer in `src/atman/eval/` that stays isolated from production runtime paths.

Key goals:

- run benchmarks via module-only CLI (`python -m atman.eval.benchmark_runner`)
- keep benchmark registration simple (`registry.py` + decorator, no entry points)
- reuse existing eval DB schema (`eval.benchmark_runs`, `eval.run_items`) and put extra context into `metadata` JSONB
- provide reproducible local output (JSONL reporter + demo script)

## Module Map

- `benchmark_runner.py` - Click CLI with `list` / `run`
- `runner_core.py` - benchmark lifecycle, deterministic app-level idempotency when `git_sha` is provided
- `run_context.py` - typed run context + `to_db_metadata()`
- `registry.py` - benchmark register/get/list
- `reporters/base.py` - reporter protocol
- `reporters/db_reporter.py` - writer for `eval.benchmark_runs` and `eval.run_items`
- `reporters/jsonl_reporter.py` - JSONL sink for local artifacts
- `seed_manager.py` - deterministic seed resolution and global seed apply
- `hardware.py` - CPU/memory/GPU probe with graceful fallback when `psutil`/`pynvml` or NVML are unavailable
- `benchmarks/noop.py` - smoke benchmark used by demo and CLI checks

## Eval Family Quick Reference

The E1 runner is the registry-based benchmark path. Some eval tools are standalone scripts because they need optional model downloads, external APIs, or a fixed research dataset.

| Question | Tool | Label source / output |
| --- | --- | --- |
| Is the eval runner wired correctly? | `python -m atman.eval.benchmark_runner list` / `run noop` | Built-in `noop` benchmark via `registry.py` |
| Is production GLiNER+MiniLM good enough today? | `python3 scripts/eval/eval_linguistic_quality.py --adapter gliner` | Runtime `EntityType` / linguistic adapter labels |
| Should Atman fine-tune GLiNER2 for Russian NER-core? | `python -m atman.eval.gliner2.baseline --model fastino/gliner2-multi-v1` | T1 `atman-ner-core` 13-label schema, results in `eval/results/gliner2_baseline_ru.json` |
| How was the synthetic RU NER corpus generated? | `PIONEER_API_KEY=... python3 scripts/eval/generate_synthetic_ru.py` | GLiNER training JSONL at `eval/data/atman_ner_ru_synth.jsonl` |

The GLiNER2 baseline is intentionally **not** registered in `atman.eval.registry`: it is a fixed zero-shot research runner that downloads HuggingFace models on first use and writes a merged JSON artifact.

## CLI Usage

List benchmarks:

```bash
python -m atman.eval.benchmark_runner list
```

Run benchmark:

```bash
python -m atman.eval.benchmark_runner run noop --git-sha "$(git rev-parse --short HEAD)" --jsonl-output /tmp/atman-eval.jsonl
```

Optional DB write (existing eval schema):

```bash
python -m atman.eval.benchmark_runner run noop --db-dsn "$POSTGRES_URL"
```

Run the standalone GLiNER2 baseline (requires the `eval` extra and model downloads on first use):

```bash
python -m atman.eval.gliner2.baseline --model fastino/gliner2-multi-v1
python -m atman.eval.gliner2.baseline --model urchade/gliner_multi-v2.1
```

Current committed results use 130 gold Russian examples from `src/atman/eval/gliner2/dataset.py` and conclude both baseline models are in the `F1 0.4-0.7` band, so fine-tuning is needed.

## Makefile Aliases

- `make eval-list`
- `make eval-run`
- `make demo-eval-runner`
- `make demo-eval-runner-fast`

There is no Makefile alias for the GLiNER2 baseline; use the module command above so the expensive model choice stays explicit.

## Synthetic RU NER Data

`scripts/eval/generate_synthetic_ru.py` regenerates the committed corpus at `eval/data/atman_ner_ru_synth.jsonl`.

Constraints:

- requires `PIONEER_API_KEY` and network access to the Pioneer API
- emits GLiNER training rows: `{"tokenized_text": [...], "ner": [[start, end, "label"], ...]}`
- uses 0-based inclusive token spans
- validates labels and span bounds before writing success output
- is not part of `make check` or the E1 registry path

## Demo

`src/demo_eval_runner.py` demonstrates:

1. benchmark discovery via registry
2. one noop run with JSONL reporting
3. second run with same `git_sha` returning idempotent `skipped` outcome

Run:

```bash
make demo-eval-runner
```

## Safety / Isolation Notes

- no production entry point is added for eval runner
- `atman.eval` remains optional and guarded by dependency check
- `make lint-boundary` and `make verify-prod-isolation` remain required gates
