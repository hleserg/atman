"""Cold-start + warm-infer latency measurement for Atman's CPU ML models.

Five models, all on CPU:
  * `bge-m3`         — FlagEmbedding `BAAI/bge-m3`
  * `bge-reranker`   — FlagEmbedding `BAAI/bge-reranker-v2-m3`
  * `gliner`         — gliner `urchade/gliner_multi-v2.1`
  * `minilm`         — transformers zero-shot `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`
  * `mrebel`         — transformers `Babelscape/mrebel-large`

For each model the script measures:
  * `setup_s`         — adapter instantiation (typically near-zero; weights are lazy).
  * `first_infer_s`   — first inference call (includes weight download + load).
  * `second_infer_s`  — second inference call (warm cache; representative of steady-state).
  * `rss_delta_mb`    — RSS growth (rough; psutil).

Per-model errors do NOT abort the run — each block is wrapped in try/except.

Usage:
  CUDA_VISIBLE_DEVICES= python scripts/measure_native_models_cold_start.py
  CUDA_VISIBLE_DEVICES= python scripts/measure_native_models_cold_start.py --only bge-m3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass

# Force CPU before any deep-learning import runs.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


@dataclass
class Result:
    name: str
    status: str  # "PASS" | "FAIL"
    setup_s: float = 0.0
    first_infer_s: float = 0.0
    second_infer_s: float = 0.0
    rss_delta_mb: float = 0.0
    error: str | None = None


def _rss_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def _bench(name: str, build: Callable[[], object], infer: Callable[[object], object]) -> Result:
    rss0 = _rss_mb()
    try:
        t0 = time.perf_counter()
        adapter = build()
        t1 = time.perf_counter()
        infer(adapter)
        t2 = time.perf_counter()
        infer(adapter)
        t3 = time.perf_counter()
        return Result(
            name=name,
            status="PASS",
            setup_s=t1 - t0,
            first_infer_s=t2 - t1,
            second_infer_s=t3 - t2,
            rss_delta_mb=_rss_mb() - rss0,
        )
    except Exception as e:
        return Result(
            name=name,
            status="FAIL",
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            rss_delta_mb=_rss_mb() - rss0,
        )


# ── per-model runners ────────────────────────────────────────────────────────


def run_bge_m3() -> Result:
    def build():
        from atman.adapters.memory.flag_embedding import FlagEmbeddingAdapter

        return FlagEmbeddingAdapter(model_name="BAAI/bge-m3", device="cpu", use_fp16=False)

    def infer(a):  # type: ignore[no-untyped-def]
        return a.embed_batch(["hello world"])

    return _bench("bge-m3", build, infer)


def run_bge_reranker() -> Result:
    def build():
        from atman.adapters.memory.bge_reranker import BgeReranker

        return BgeReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu", use_fp16=False)

    def infer(a):  # type: ignore[no-untyped-def]
        from uuid import uuid4

        from atman.core.ports.memory_reranker import SurfacedMemory

        candidates = [
            SurfacedMemory(key_moment_id=uuid4(), text="candidate one", score=0.5, source="dense"),
            SurfacedMemory(key_moment_id=uuid4(), text="candidate two", score=0.4, source="dense"),
        ]
        return a.rerank("test query", candidates)

    return _bench("bge-reranker", build, infer)


def run_gliner() -> Result:
    def build():
        from atman.adapters.linguistic.gliner_minilm_adapter import GLiNERPlusMiniLMAdapter

        return GLiNERPlusMiniLMAdapter(
            gliner_model="urchade/gliner_multi-v2.1",
            minilm_model="MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
            device="cpu",
        )

    def infer(a):  # type: ignore[no-untyped-def]
        # gliner has analyze_user_message; force model load via NER call.
        gliner = a._get_gliner()
        if gliner is None:
            raise RuntimeError("gliner failed to load")
        return gliner.predict_entities("Alice met Bob in Paris.", ["Person", "Location"])

    return _bench("gliner", build, infer)


def run_minilm() -> Result:
    def build():
        from atman.adapters.linguistic.gliner_minilm_adapter import GLiNERPlusMiniLMAdapter

        return GLiNERPlusMiniLMAdapter(
            gliner_model="urchade/gliner_multi-v2.1",
            minilm_model="MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
            device="cpu",
        )

    def infer(a):  # type: ignore[no-untyped-def]
        clf = a._get_classifier()
        if clf is None:
            raise RuntimeError("minilm classifier failed to load")
        return clf("This is a positive sentence.", candidate_labels=["positive", "negative"])

    return _bench("minilm", build, infer)


def run_mrebel() -> Result:
    def build():
        from atman.adapters.linguistic.mrebel_adapter import MRebelRelationAdapter

        return MRebelRelationAdapter(model_name="Babelscape/mrebel-large", device="cpu")

    def infer(a):  # type: ignore[no-untyped-def]
        from atman.core.models.entity import EntityType
        from atman.core.ports.linguistic import DetectedEntity

        ents = [
            DetectedEntity(
                text="Alice", entity_type=EntityType.person, confidence=0.99, span=(0, 5)
            ),
            DetectedEntity(
                text="Bob", entity_type=EntityType.person, confidence=0.99, span=(10, 13)
            ),
        ]
        return a.extract_relations("Alice met Bob in Paris.", ents)

    return _bench("mrebel", build, infer)


RUNNERS: dict[str, Callable[[], Result]] = {
    "bge-m3": run_bge_m3,
    "bge-reranker": run_bge_reranker,
    "gliner": run_gliner,
    "minilm": run_minilm,
    "mrebel": run_mrebel,
}


def _print_row(r: Result) -> None:
    if r.status == "PASS":
        print(
            f"  {r.name:14s}  PASS   setup={r.setup_s:6.2f}s   "
            f"first={r.first_infer_s:7.2f}s   second={r.second_infer_s:6.3f}s   "
            f"ΔRSS={r.rss_delta_mb:7.1f} MB"
        )
    else:
        err_text = r.error or "?"
        first_line = err_text.splitlines()[0]
        print(f"  {r.name:14s}  FAIL   {first_line[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure CPU cold-start of native ML models")
    parser.add_argument(
        "--only",
        choices=sorted(RUNNERS),
        action="append",
        default=None,
        help="Run only the specified model (may be repeated). Default: all.",
    )
    parser.add_argument(
        "--full-traceback",
        action="store_true",
        help="Print full traceback for any FAIL.",
    )
    args = parser.parse_args()

    names = args.only if args.only else list(RUNNERS)

    print(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '<unset>')}")
    print("Measuring (each block isolated by try/except):\n")

    results: list[Result] = []
    for name in names:
        print(f"→ {name} ...", flush=True)
        r = RUNNERS[name]()
        _print_row(r)
        results.append(r)

    print("\nSummary:")
    for r in results:
        _print_row(r)

    if args.full_traceback:
        for r in results:
            if r.status == "FAIL":
                print(f"\n[{r.name}] traceback:\n{r.error}")

    return 0 if all(r.status == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
