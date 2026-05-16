"""Tests for the mREBEL triplet parser — four-marker + two-marker formats."""

from __future__ import annotations

from atman.adapters.linguistic.mrebel_adapter import _parse_rebel_triplets


def test_four_marker_format_alice_bob_spouse() -> None:
    """Real mREBEL output: <triplet> subj <subj> type <subj_type> obj <obj> type <obj_type> rel"""
    out = _parse_rebel_triplets(
        "<triplet> Alice <subj> person <subj_type> Bob <obj> person <obj_type> spouse"
    )
    assert out == [("Alice", "Bob", "spouse")]


def test_four_marker_multi_word_relation_preserved() -> None:
    """Multi-word relations like 'located in' must not be truncated to first word."""
    out = _parse_rebel_triplets(
        "<triplet> Paris <subj> city <subj_type> France <obj> country <obj_type> located in"
    )
    assert out == [("Paris", "France", "located in")]


def test_two_marker_legacy_format_dropped() -> None:
    """Single-language REBEL output without <subj>/<obj> markers is intentionally dropped.

    Its layout ``subj <subj_type> subj_type_label <obj_type> obj relation``
    cannot be unambiguously split — the object text and the relation share
    the trailing fragment with no separator. The parser drops the triplet
    rather than emitting garbage that would never match a detected entity.
    """
    out = _parse_rebel_triplets("<triplet> Alice <subj_type> person <obj_type> Bob spouse")
    assert out == []


def test_multiple_triplets() -> None:
    decoded = (
        "<triplet> Alice <subj> person <subj_type> Bob <obj> person <obj_type> spouse"
        " <triplet> Paris <subj> city <subj_type> France <obj> country <obj_type> capital of"
    )
    out = _parse_rebel_triplets(decoded)
    assert ("Alice", "Bob", "spouse") in out
    assert ("Paris", "France", "capital of") in out


def test_empty_input_returns_empty() -> None:
    assert _parse_rebel_triplets("") == []
    assert _parse_rebel_triplets("garbage no markers") == []


def test_malformed_triplet_dropped() -> None:
    # No <obj> / <obj_type> marker
    out = _parse_rebel_triplets("<triplet> Alice <subj> person <subj_type> Bob")
    assert out == []


def test_empty_subject_or_object_dropped() -> None:
    out = _parse_rebel_triplets(
        "<triplet>  <subj> person <subj_type> Bob <obj> person <obj_type> spouse"
    )
    assert out == []
