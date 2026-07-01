from sagasmith_core.parsing import MarkdownHierarchyParser
from sagasmith_core.retrieval import lexical_score, reciprocal_rank_fusion


def test_markdown_parser_preserves_heading_paths() -> None:
    parsed = MarkdownHierarchyParser(chunk_size=200, chunk_overlap=20).parse(
        "# Combat\nGeneral rules.\n## Grapple\nA grapple uses a check."
    )

    assert [section.path for section in parsed] == [
        ("Combat",),
        ("Combat", "Grapple"),
    ]
    assert parsed[1].chunks[0].heading_path == ("Combat", "Grapple")


def test_lexical_search_handles_chinese_and_english() -> None:
    assert lexical_score("擒抱 grapple", title="Grapple 擒抱", content="Rules") > 0


def test_rrf_combines_rankings_deterministically() -> None:
    fused = reciprocal_rank_fusion(
        {"lexical": ["a", "b"], "dense": ["b", "a"]},
    )

    assert {item[0] for item in fused[:2]} == {"a", "b"}

