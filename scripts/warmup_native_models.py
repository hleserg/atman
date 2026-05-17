"""Pre-warm all native CPU ML models used by Atman.

Downloads weights to HF cache (if not already present) and loads each model
into memory so the first real inference is instant. Idempotent: safe to run
repeatedly — HF cache hit skips download.

Models warmed:
  * bge-m3         BAAI/bge-m3             ~2.3 GB  (embeddings)
  * bge-reranker   BAAI/bge-reranker-v2-m3 ~0.6 GB  (cross-encoder reranker)
  * gliner         urchade/gliner_multi-v2.1 ~1.0 GB (NER)
  * minilm         MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli ~0.5 GB
  * mrebel         Babelscape/mrebel-large  ~1.6 GB  (relation extraction)

Usage:
  CUDA_VISIBLE_DEVICES= python scripts/warmup_native_models.py
  CUDA_VISIBLE_DEVICES= python scripts/warmup_native_models.py --only bge-m3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from collections.abc import Callable

# Force CPU before any deep-learning import.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

_OK = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"
_ARROW = "\033[36m→\033[0m"


def _warmup(name: str, fn: Callable[[], None]) -> bool:
    print(f"  {_ARROW} {name} ...", flush=True)
    t0 = time.perf_counter()
    try:
        fn()
        elapsed = time.perf_counter() - t0
        print(f"  {_OK} {name}  ({elapsed:.1f}s)")
        return True
    except Exception as e:
        elapsed = time.perf_counter() - t0
        first = traceback.format_exc().splitlines()[-1]
        print(f"  {_FAIL} {name}  ({elapsed:.1f}s)  {first}")
        return False


# ── per-model warmup functions ───────────────────────────────────────────────


def warm_bge_m3() -> None:
    from atman.adapters.memory.flag_embedding import FlagEmbeddingAdapter

    a = FlagEmbeddingAdapter(model_name="BAAI/bge-m3", device="cpu", use_fp16=False)
    a.embed_batch(["warmup"])


def warm_bge_reranker() -> None:
    from uuid import uuid4

    from atman.adapters.memory.bge_reranker import BgeReranker
    from atman.core.ports.memory_reranker import SurfacedMemory

    a = BgeReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu", use_fp16=False)
    candidates = [
        SurfacedMemory(key_moment_id=uuid4(), text="warmup doc", score=0.5, source="dense"),
    ]
    a.rerank("warmup", candidates)


def warm_gliner() -> None:
    from atman.adapters.linguistic.gliner_minilm_adapter import GLiNERPlusMiniLMAdapter

    a = GLiNERPlusMiniLMAdapter(
        gliner_model="urchade/gliner_multi-v2.1",
        minilm_model="MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
        device="cpu",
    )
    g = a._get_gliner()  # noqa: SLF001
    if g is None:
        raise RuntimeError("GLiNER failed to load")
    g.predict_entities("Alice met Bob.", ["Person", "Location"])


def warm_minilm() -> None:
    from atman.adapters.linguistic.gliner_minilm_adapter import GLiNERPlusMiniLMAdapter

    a = GLiNERPlusMiniLMAdapter(
        gliner_model="urchade/gliner_multi-v2.1",
        minilm_model="MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
        device="cpu",
    )
    clf = a._get_classifier()  # noqa: SLF001
    if clf is None:
        raise RuntimeError("MiniLM classifier failed to load")
    clf("warmup", candidate_labels=["yes", "no"])


def warm_mrebel() -> None:
    from atman.adapters.linguistic.mrebel_adapter import MRebelRelationAdapter
    from atman.core.models.entity import EntityType
    from atman.core.ports.linguistic import DetectedEntity

    a = MRebelRelationAdapter(model_name="Babelscape/mrebel-large", device="cpu")
    ents = [
        DetectedEntity(text="Alice", entity_type=EntityType.person, confidence=0.99, span=(0, 5)),
    ]
    a.extract_relations("Alice works.", ents)


WARMERS: dict[str, Callable[[], None]] = {
    "bge-m3": warm_bge_m3,
    "bge-reranker": warm_bge_reranker,
    "gliner": warm_gliner,
    "minilm": warm_minilm,
    "mrebel": warm_mrebel,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-warm Atman native CPU models")
    parser.add_argument(
        "--only",
        choices=sorted(WARMERS),
        action="append",
        default=None,
        help="Warm only the specified model (may be repeated). Default: all.",
    )
    args = parser.parse_args()

    names = args.only if args.only else list(WARMERS)

    print(f"\nAtman model warmup  (CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '<unset>')})")
    print(f"Models: {', '.join(names)}\n")

    results = {name: _warmup(name, WARMERS[name]) for name in names}

    failed = [n for n, ok in results.items() if not ok]
    print()
    if failed:
        print(f"  {_FAIL} Failed: {', '.join(failed)}")
        return 1

    print(f"  {_OK} All {len(names)} model(s) warmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
