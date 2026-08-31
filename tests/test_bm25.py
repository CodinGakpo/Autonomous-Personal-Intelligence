"""Tests for brain/bm25.py — the shared BM25 ranking helper."""

from brain import bm25


def test_rank_orders_by_relevance():
    docs = {"a": "placement internship accenture", "b": "lecture syllabus professor"}
    ranked = bm25.rank("accenture internship", docs)
    assert ranked[0][0] == "a"
    assert ranked[0][1] > ranked[1][1]


def test_rank_empty_documents_returns_empty_list():
    assert bm25.rank("anything", {}) == []


def test_rank_empty_query_scores_everything_zero():
    docs = {"a": "hello", "b": "world"}
    assert bm25.rank("", docs) == [("a", 0.0), ("b", 0.0)]


def test_rank_no_shared_terms_scores_zero():
    ranked = bm25.rank("unrelated words here", {"a": "placement internship"})
    assert ranked == [("a", 0.0)]
