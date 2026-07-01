"""Exact, lexical, dense, and reciprocal-rank-fusion retrieval helpers."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

_LATIN_WORD = re.compile(r"[A-Za-z0-9_'-]+")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(frozen=True)
class SearchHit:
    id: str
    score: float
    title: str
    content: str
    source_id: str
    heading_path: tuple[str, ...] = ()
    retrieval: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def terms(text: str) -> list[str]:
    normalized = text.casefold()
    values = _LATIN_WORD.findall(normalized)
    cjk = _CJK.findall(normalized)
    values.extend(cjk)
    values.extend("".join(cjk[index : index + 2]) for index in range(len(cjk) - 1))
    return [value for value in values if value]


def lexical_score(query: str, *, title: str, content: str) -> float:
    query_terms = terms(query)
    if not query_terms:
        return 0.0
    title_folded = title.casefold()
    content_folded = content.casefold()
    score = 0.0
    for term in query_terms:
        score += title_folded.count(term) * 4.0
        score += min(content_folded.count(term), 8)
    return score / math.sqrt(max(len(terms(content)), 1))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]],
    *,
    weights: dict[str, float] | None = None,
    rank_constant: int = 60,
) -> list[tuple[str, float, tuple[str, ...]]]:
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for name, ids in rankings.items():
        weight = (weights or {}).get(name, 1.0)
        for rank, item_id in enumerate(ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (rank_constant + rank)
            sources.setdefault(item_id, []).append(name)
    return sorted(
        (
            (item_id, score, tuple(sources[item_id]))
            for item_id, score in scores.items()
        ),
        key=lambda item: (-item[1], item[0]),
    )

