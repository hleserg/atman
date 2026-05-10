"""Tests for BM25EmbeddingAdapter (E24.6)."""

from __future__ import annotations

import pytest

from atman.adapters.memory.bm25_embedding import BM25EmbeddingAdapter


def test_tokenize_drops_short_tokens_and_lowercases():
    adapter = BM25EmbeddingAdapter()
    assert adapter._tokenize("Hello, World! a") == ["hello", "world"]


def test_embed_single_text_uses_self_corpus():
    adapter = BM25EmbeddingAdapter()
    vec = adapter.embed("alpha beta beta gamma")
    assert adapter.dimension() == 3
    assert len(vec) == 3
    # Each term has positive TF weight when corpus is itself
    assert all(value > 0 for value in vec)


def test_embed_batch_shares_vocabulary():
    adapter = BM25EmbeddingAdapter()
    docs = [
        "alpha beta gamma delta",
        "alpha epsilon zeta eta",
        "alpha beta theta iota",
    ]
    vectors = adapter.embed_batch(docs)
    assert len(vectors) == 3
    # Shared vocabulary across all docs
    dim = adapter.dimension()
    assert all(len(vec) == dim for vec in vectors)
    # "alpha" appears in every doc; its IDF is small (smoothed log(0.5/(n+0.5)+1)),
    # while a term that appears in only one doc has a higher IDF.
    alpha_idx = adapter._vocab["alpha"]
    epsilon_idx = adapter._vocab["epsilon"]
    # Alpha appears in every doc; rare terms should outrank it for the docs they appear in.
    assert vectors[1][epsilon_idx] > vectors[1][alpha_idx]


def test_embed_with_corpus_uses_idf():
    adapter = BM25EmbeddingAdapter()
    corpus = [
        "rare word here",
        "common term here",
        "common term again",
    ]
    vec = adapter.embed_with_corpus("rare word", corpus)
    rare_idx = adapter._vocab["rare"]
    common_idx = adapter._vocab["common"]
    # "rare" has higher IDF than "common"; both terms present in query "rare word"
    assert vec[rare_idx] > 0.0
    # "common" not in query, so its weight stays at 0
    assert vec[common_idx] == 0.0


def test_embed_with_corpus_skips_oov_terms():
    adapter = BM25EmbeddingAdapter()
    corpus = ["alpha beta gamma"]
    vec = adapter.embed_with_corpus("alpha unknown_term", corpus)
    # OOV term is skipped silently; dimension matches corpus vocab
    assert len(vec) == adapter.dimension()
    assert vec[adapter._vocab["alpha"]] >= 0.0


def test_similarity_self_is_one_for_nonzero_vector():
    adapter = BM25EmbeddingAdapter()
    vec = adapter.embed("hello world world world")
    assert adapter.similarity(vec, vec) == pytest.approx(1.0)


def test_similarity_zero_vector_returns_zero():
    adapter = BM25EmbeddingAdapter()
    other = adapter.embed("alpha beta")
    zero = [0.0] * adapter.dimension()
    assert adapter.similarity(zero, other) == 0.0


def test_similarity_dimension_mismatch_raises():
    adapter = BM25EmbeddingAdapter()
    with pytest.raises(ValueError):
        adapter.similarity([0.1], [0.1, 0.2])


def test_idf_returns_zero_for_unknown_term():
    adapter = BM25EmbeddingAdapter()
    adapter._build_corpus_stats([["alpha"], ["beta"]])
    assert adapter._idf("unknown") == 0.0


def test_tf_weight_handles_zero_avg_doc_len():
    adapter = BM25EmbeddingAdapter()
    # avg_doc_len == 0 short-circuits to plain term frequency
    assert adapter._tf_weight(term_freq=3, doc_len=0, avg_doc_len=0) == 3


def test_build_corpus_stats_with_empty_corpus():
    adapter = BM25EmbeddingAdapter()
    adapter._build_corpus_stats([])
    assert adapter._num_docs == 0
    assert adapter._avg_doc_len == 0.0
