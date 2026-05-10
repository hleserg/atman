"""
Tests for BM25EmbeddingAdapter.

Covers the EmbeddingPort surface added in E25 (``model_name`` and Unicode
tokenization) so the adapter remains a drop-in for ``MockEmbeddingAdapter``
and ``OllamaEmbeddingAdapter``.
"""

import pytest

from atman.adapters.memory.bm25_embedding import BM25EmbeddingAdapter


class TestBM25EmbeddingAdapter:
    """Cover the EmbeddingPort surface implemented by BM25."""

    @pytest.fixture
    def adapter(self) -> BM25EmbeddingAdapter:
        return BM25EmbeddingAdapter()

    def test_implements_embedding_port_methods(self, adapter: BM25EmbeddingAdapter) -> None:
        """BM25 adapter exposes every method ``EmbeddingPort`` declares."""
        for name in ("embed", "embed_batch", "dimension", "model_name", "similarity"):
            assert hasattr(adapter, name), f"BM25EmbeddingAdapter is missing {name!r}"

    def test_model_name_encodes_parameters(self) -> None:
        """``model_name`` includes ``k1`` / ``b`` so artifacts are traceable."""
        adapter = BM25EmbeddingAdapter(k1=1.2, b=0.8)
        name = adapter.model_name()
        assert "bm25" in name
        assert "1.2" in name
        assert "0.8" in name

    def test_tokenizer_keeps_cyrillic(self, adapter: BM25EmbeddingAdapter) -> None:
        """Tokens like ``пользователь`` survive lowercasing + tokenization."""
        # Russian-only sentence — the resulting vector must be non-zero, which
        # only happens if Cyrillic word characters survive the tokenizer.
        vector = adapter.embed("Пользователь подтвердил результат задачи")
        assert len(vector) == adapter.dimension()
        assert any(component != 0.0 for component in vector)
        # Every produced token must be Cyrillic (no ASCII spillover).
        tokens = adapter._tokenize("Пользователь подтвердил результат задачи")
        assert tokens, "tokenizer must keep Cyrillic content"
        assert all(any(ord(ch) > 127 for ch in tok) for tok in tokens)

    def test_tokenizer_keeps_cjk(self, adapter: BM25EmbeddingAdapter) -> None:
        """CJK ideographs are preserved by ``[^\\W_]+`` with re.UNICODE."""
        vector = adapter.embed("机器学习 是 人工智能 的 子领域")
        assert len(vector) == adapter.dimension()
        assert any(component != 0.0 for component in vector)
        tokens = adapter._tokenize("机器学习 是 人工智能 的 子领域")
        # CJK tokens are kept (every kept token contains an ideograph).
        assert tokens
        assert any(any(0x4E00 <= ord(ch) <= 0x9FFF for ch in tok) for tok in tokens)

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

    def test_similarity_identical_vectors(self, adapter: BM25EmbeddingAdapter) -> None:
        """Cosine similarity of a non-zero vector with itself is ``1.0``."""
        vec = adapter.embed("the quick brown fox jumps over the lazy dog")
        assert adapter.similarity(vec, vec) == pytest.approx(1.0)

    def test_similarity_zero_vector(self, adapter: BM25EmbeddingAdapter) -> None:
        """Empty input produces a zero vector and similarity is ``0.0``."""
        empty = adapter.embed("")
        assert adapter.similarity(empty, empty) == 0.0

    def test_embed_calls_share_dimension_for_similarity(
        self, adapter: BM25EmbeddingAdapter
    ) -> None:
        """
        Independent ``embed()`` calls must yield vectors of identical length
        so that ``similarity()`` can compare them — prior to E25 the adapter
        rebuilt the vocabulary on every call, which silently broke this.
        """
        v1 = adapter.embed("alpha beta gamma")
        v2 = adapter.embed("delta epsilon zeta")
        assert len(v1) == len(v2) == adapter.dimension()
        # similarity must run without raising and stay within [-1, 1].
        score = adapter.similarity(v1, v2)
        assert -1.0 <= score <= 1.0
