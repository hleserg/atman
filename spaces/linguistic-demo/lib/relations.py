"""mREBEL relation extraction (Babelscape/mrebel-large).

Standalone port of `src/atman/adapters/linguistic/mrebel_adapter.py` for
the HuggingFace Space demo.
"""

from __future__ import annotations

import logging
from typing import Any

from lib.dto import DetectedEntity, ExtractedRelation

logger = logging.getLogger(__name__)

try:
    from transformers import pipeline as _hf_pipeline  # type: ignore[import-untyped]

    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _hf_pipeline = None  # type: ignore[assignment]
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
        self._pipeline: Any = None

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        logger.info("Loading mREBEL model %s …", self._model_name)
        self._pipeline = _hf_pipeline(  # type: ignore[operator]
            "text2text-generation",
            model=self._model_name,
            tokenizer=self._model_name,
            device=self._device,
        )
        return self._pipeline

    def extract_relations(
        self, text: str, entities: list[DetectedEntity]
    ) -> list[ExtractedRelation]:
        if not text.strip() or len(entities) < 2:
            return []
        pipe = self._get_pipeline()
        try:
            outputs = pipe(
                text,
                max_length=192,
                num_beams=1,
                return_tensors=False,
                clean_up_tokenization_spaces=True,
            )
        except Exception:
            logger.exception("mREBEL inference failed")
            return []

        if not outputs or not isinstance(outputs, list):
            return []
        generated = str(outputs[0].get("generated_text", "")) if outputs else ""
        triplets = parse_rebel_triplets(generated)

        entity_by_text: dict[str, DetectedEntity] = {e.text.lower(): e for e in entities}
        relations: list[ExtractedRelation] = []
        for subj_text, obj_text, relation_label in triplets:
            subj = entity_by_text.get(subj_text.lower())
            obj = entity_by_text.get(obj_text.lower())
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
    """Parse mREBEL's four-marker output into (subject, object, relation) tuples."""
    if not decoded:
        return []
    out: list[tuple[str, str, str]] = []
    for chunk in decoded.split("<triplet>")[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue
        if "<subj>" not in chunk:
            continue
        subj_part, _, rest = chunk.partition("<subj>")
        if "<subj_type>" in rest:
            _, _, rest = rest.partition("<subj_type>")
        if "<obj>" in rest:
            obj_part, _, relation_part = rest.partition("<obj>")
            if "<obj_type>" in relation_part:
                _, _, relation_part = relation_part.partition("<obj_type>")
        elif "<obj_type>" in rest:
            obj_part, _, relation_part = rest.partition("<obj_type>")
        else:
            continue
        subj_text = subj_part.strip()
        obj_text = obj_part.strip()
        relation = relation_part.strip()
        if not subj_text or not obj_text or not relation:
            continue
        out.append((subj_text, obj_text, relation))
    return out
