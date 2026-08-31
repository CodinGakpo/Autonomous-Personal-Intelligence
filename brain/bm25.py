"""brain/bm25.py — shared BM25 ranking: score named "documents" against a query.

Extracted from mail_ingest.guess_category_bm25's scoring math so mail_ingest (categories as
documents) and mail_ask (mail threads as documents) rank against the same formula instead of
duplicating it. Pure stdlib, no I/O.
"""

from __future__ import annotations

import math
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def rank(
    query: str,
    documents: dict[str, str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[str, float]]:
    """BM25-rank `documents` (name -> raw text) against `query`.

    Returns [(name, score), ...] sorted highest first. If `documents` is empty, returns [].
    If `query` tokenizes to nothing, every document scores 0.0 (still returned, in input
    order) — callers treat an all-zero result as "no signal".
    """
    if not documents:
        return []
    docs = {name: tokenize(text) for name, text in documents.items()}
    query_terms = set(tokenize(query))
    if not query_terms:
        return [(name, 0.0) for name in documents]

    n_docs = len(docs)
    avg_len = (sum(len(d) for d in docs.values()) / n_docs) or 1.0
    doc_freq: Counter[str] = Counter()
    for doc in docs.values():
        doc_freq.update(set(doc))

    scores: dict[str, float] = {}
    for name, doc in docs.items():
        term_freq = Counter(doc)
        doc_len = len(doc)
        score = 0.0
        for term in query_terms:
            f = term_freq.get(term, 0)
            if f == 0:
                continue
            n_t = doc_freq.get(term, 0)
            idf = math.log((n_docs - n_t + 0.5) / (n_t + 0.5) + 1)
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_len))
        scores[name] = score

    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
