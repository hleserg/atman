"""
Tests for BM25EmbeddingAdapter.

Covers Devin Review fixes for PR #414:
- ``model_name`` is implemented (Protocol contract).
- ``_tokenize`` accepts non-ASCII input (Cyrillic, CJK).
- ``embed`` returns vectors of a fixed ``dimension`` so independent
  ``embed()`` calls are directly comparable via ``similarity()`` (the
  previous implementation rebuilt the vocabulary on every call, which
  silently broke that contract).
"""

from __future__ import annotations

import pytest

from atman.adapters.memory.bm25_embedding import BM25EmbeddingAdapter


class TestBM25EmbeddingAdapter:
    """Unit tests for the BM25 sparse embedding adapter."""

    @pytest.fixture
    def adapter(self) -> BM25EmbeddingAdapter:
        return BM25EmbeddingAdapter()

    def test_implements_embedding_port_methods(self, adapter: BM25EmbeddingAdapter) -> None:
        """BM25 adapter satisfies the EmbeddingPort method contract."""
        for name in ("embed", "embed_batch", "dimension", "model_name", "similarity"):
            assert callable(getattr(adapter, name)), f"missing method: {name}"

    def test_model_name_is_set(self, adapter: BM25EmbeddingAdapter) -> None:
        """``model_name`` returns a stable identifier for telemetry/logs."""
        assert adapter.model_name() == "bm25-sparse"

    def test_embed_ascii_returns_nonempty_vector(self, adapter: BM25EmbeddingAdapter) -> None:
        """English text produces a non-empty BM25 vector (regression baseline)."""
        vec = adapter.embed("the quick brown fox jumps over the lazy dog")
        assert len(vec) == adapter.dimension()
        assert any(v != 0.0 for v in vec)

    @pytest.mark.parametrize(
        "text",
        [
            "Пользователь попросил реализовать факты",  # Cyrillic
            "我喜欢猫和狗",  # Chinese
            "café résumé naïve",  # Latin with diacritics
        ],
    )
    def test_embed_non_ascii_text_produces_tokens(
        self, adapter: BM25EmbeddingAdapter, text: str
    ) -> None:
        """Non-ASCII tokens must not be silently dropped by the tokenizer.

        With the previous ``[a-z0-9]+`` pattern, Cyrillic/CJK input produced
        zero tokens and an empty embedding vector. The Unicode-aware
        ``[^\\W_]+`` tokenizer fixes this.
        """
        tokens = adapter._tokenize(text)
        assert tokens, f"tokenizer dropped all tokens for {text!r}"

        vec = adapter.embed(text)
        assert len(vec) == adapter.dimension()
        assert any(v != 0.0 for v in vec)

    def test_tokenizer_drops_underscores_and_short_tokens(
        self, adapter: BM25EmbeddingAdapter
    ) -> None:
        """Underscores and ``<= 2`` char tokens are stripped as noise."""
        tokens = adapter._tokenize("a b cd hello_world __dunder__ longer")
        # ``a``, ``b``, ``cd`` are too short; underscores split ``hello_world``.
        assert "a" not in tokens
        assert "b" not in tokens
        assert "cd" not in tokens
        assert "hello" in tokens
        assert "world" in tokens
        assert "longer" in tokens

    def test_similarity_dimension_mismatch_raises(self, adapter: BM25EmbeddingAdapter) -> None:
        """``similarity`` rejects vectors with mismatched dimensions."""
        with pytest.raises(ValueError):
            adapter.similarity([1.0, 0.0, 0.0], [1.0, 0.0])

    def test_similarity_zero_vectors_returns_zero(self, adapter: BM25EmbeddingAdapter) -> None:
        """Zero-norm vectors get a defined similarity of 0.0."""
        assert adapter.similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_similarity_identical_vectors(self, adapter: BM25EmbeddingAdapter) -> None:
        """Cosine similarity of a non-zero vector with itself is ``1.0``."""
        vec = adapter.embed("the quick brown fox jumps over the lazy dog")
        assert adapter.similarity(vec, vec) == pytest.approx(1.0)

    def test_embed_calls_share_dimension_for_similarity(
        self, adapter: BM25EmbeddingAdapter
    ) -> None:
        """
        Independent ``embed()`` calls must yield vectors of identical length
        so that ``similarity()`` can compare them — prior to the E25 fix the
        adapter rebuilt the vocabulary on every call, which silently broke
        that contract.
        """
        v1 = adapter.embed("alpha beta gamma")
        v2 = adapter.embed("delta epsilon zeta")
        assert len(v1) == len(v2) == adapter.dimension()
        # similarity must run without raising and stay within [-1, 1].
        score = adapter.similarity(v1, v2)
        assert -1.0 <= score <= 1.0
