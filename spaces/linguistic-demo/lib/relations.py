"""mREBEL relation extraction (Babelscape/mrebel-large).

Standalone port of `src/atman/adapters/linguistic/mrebel_adapter.py` for
the HuggingFace Space demo.

mREBEL output format:
    <s>tp_XX<triplet> ENTITY1 <TYPE> ENTITY2 <TYPE> RELATION</s>

Entity type separator tokens (mark entity boundaries):
    <per>, <loc>, <org>, <misc>, <time>, <num>, <date>,
    <eve>, <cel>, <media>, <dis>, <concept>

The model must be called with forced_bos_token_id set to the tp_XX
token (id 250058) — without it the decoder degenerates into repeated
garbage characters.
"""

from __future__ import annotations

import logging
from typing import Any

from lib.dto import DetectedEntity, ExtractedRelation

logger = logging.getLogger(__name__)

# mREBEL entity-type separator tokens
_MREBEL_TYPE_TOKENS: frozenset[str] = frozenset({
    "<per>", "<loc>", "<org>", "<misc>", "<time>", "<num>", "<date>",
    "<eve>", "<cel>", "<media>", "<dis>", "<concept>",
})

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM  # type: ignore[import-untyped]
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    AutoTokenizer = None  # type: ignore[assignment]
    AutoModelForSeq2SeqLM = None  # type: ignore[assignment]
    _TRANSFORMERS_AVAILABLE = False


class MRebelRelationExtractor:
    """Lazy-loaded multilingual REBEL relation extractor."""

    def __init__(
        self,
        model_name: str = "Babelscape/mrebel-large",
        device: str = "cpu",
    ) -> None:
        if not _TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "transformers is not installed. Install with: pip install transformers"
            )
        self._model_name = model_name
        self._device = device
        self._tokenizer: Any = None
        self._model: Any = None
        self._tp_xx_id: int = 250058  # fallback; overwritten on load

    def _load(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading mREBEL model %s …", self._model_name)
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)  # type: ignore[operator]
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self._model_name)  # type: ignore[operator]
        self._model.eval()
        tp_id = self._tokenizer.convert_tokens_to_ids("tp_XX")
        if tp_id and tp_id != self._tokenizer.unk_token_id:
            self._tp_xx_id = tp_id
        logger.info("mREBEL loaded. tp_XX id = %d", self._tp_xx_id)

    def extract_relations(
        self, text: str, entities: list[DetectedEntity]
    ) -> list[ExtractedRelation]:
        if not text.strip() or len(entities) < 2:
            return []
        self._load()
        try:
            inputs = self._tokenizer(  # type: ignore[operator]
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            with torch.no_grad():  # type: ignore[union-attr]
                generated_ids = self._model.generate(  # type: ignore[union-attr]
                    inputs["input_ids"],
                    forced_bos_token_id=self._tp_xx_id,
                    max_length=256,
                    num_beams=4,
                    length_penalty=0,
                )
            generated = self._tokenizer.batch_decode(  # type: ignore[operator]
                generated_ids, skip_special_tokens=False
            )[0]
        except Exception:
            logger.exception("mREBEL inference failed")
            return []

        triplets = parse_rebel_triplets(generated)
        entity_by_text: dict[str, DetectedEntity] = {e.text.lower(): e for e in entities}

        def _match(query: str) -> DetectedEntity | None:
            q = query.lower()
            if q in entity_by_text:
                return entity_by_text[q]
            for key, ent in entity_by_text.items():
                if key in q or q in key:
                    return ent
            return None

        relations: list[ExtractedRelation] = []
        for subj_text, obj_text, relation_label in triplets:
            subj = _match(subj_text)
            obj = _match(obj_text)
            if subj is None or obj is None:
                continue
            if subj.text.lower() == obj.text.lower():
                continue
            relations.append(
                ExtractedRelation(
                    subject=subj,
                    object=obj,
                    relation_type=relation_label,
                    confidence=1.0,
                    learned_by="mrebel",
                )
            )
        return relations


def parse_rebel_triplets(decoded: str) -> list[tuple[str, str, str]]:
    """Parse mREBEL output into (subject, object, relation) tuples.

    Single triplet format:
        <s>tp_XX<triplet> SUBJ <SUBJ_TYPE> OBJ <OBJ_TYPE> RELATION</s>

    Continuation format (multiple triplets sharing the same subject):
        <triplet> SUBJ <SUBJ_TYPE> OBJ1 <OBJ1_TYPE> REL1 <SUBJ_TYPE> OBJ2 <OBJ2_TYPE> REL2 …

    The subject's type token reappears in the relation field to mark the
    start of the next (OBJ, REL) pair for the same subject.
    """
    if not decoded:
        return []
    cleaned = (
        decoded
        .replace("<s>", "")
        .replace("</s>", "")
        .replace("<pad>", "")
        .replace("tp_XX", "")
        .strip()
    )
    out: list[tuple[str, str, str]] = []
    for chunk in cleaned.split("<triplet>"):
        chunk = chunk.strip()
        if not chunk:
            continue
        subj_tokens: list[str] = []
        obj_tokens: list[str] = []
        rel_tokens: list[str] = []
        state = "subj"
        subj_type: str | None = None

        def _flush() -> None:
            s = " ".join(subj_tokens).strip()
            o = " ".join(obj_tokens).strip()
            r = " ".join(rel_tokens).strip()
            if s and o and r:
                out.append((s, o, r))

        for tok in chunk.split():
            if tok in _MREBEL_TYPE_TOKENS:
                if state == "subj":
                    subj_type = tok
                    state = "obj"
                elif state == "obj":
                    state = "rel"
                elif state == "rel" and tok == subj_type:
                    # Continuation: flush current triplet, start new (obj, rel) pair
                    _flush()
                    obj_tokens = []
                    rel_tokens = []
                    state = "obj"
            else:
                if state == "subj":
                    subj_tokens.append(tok)
                elif state == "obj":
                    obj_tokens.append(tok)
                elif state == "rel":
                    rel_tokens.append(tok)
        _flush()
    return out
