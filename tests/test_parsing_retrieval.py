import math

from sagasmith_core.modules import MarkdownModuleParser
from sagasmith_core.parsing import MarkdownHierarchyParser
from sagasmith_core.retrieval import (
    enrich_query,
    lexical_score,
    reciprocal_rank_fusion,
    structured_score,
)


def test_markdown_parser_preserves_heading_paths() -> None:
    parsed = MarkdownHierarchyParser(chunk_size=200, chunk_overlap=20).parse(
        "# Combat\nGeneral rules.\n## Grapple\nA grapple uses a check."
    )

    assert [section.path for section in parsed] == [
        ("Combat",),
        ("Combat", "Grapple"),
    ]
    assert parsed[1].chunks[0].heading_path == ("Combat", "Grapple")


def test_module_parser_supports_profiles_without_scene_boundary_hook() -> None:
    class LegacyProfile:
        name = "legacy"
        version = "1"

        @staticmethod
        def classify_chunk(_heading: str, _text: str) -> str:
            return "narrative"

        @staticmethod
        def keywords(_title: str, _text: str) -> list[str]:
            return []

    chapters = MarkdownModuleParser(profile=LegacyProfile()).parse(
        "# Chapter\n## Gate\nDescription.\n"
    )

    assert chapters[0].scenes[0].title == "Gate"


def test_lexical_search_handles_chinese_and_english() -> None:
    assert lexical_score("擒抱 grapple", title="Grapple 擒抱", content="Rules") > 0


def test_rrf_combines_rankings_deterministically() -> None:
    fused = reciprocal_rank_fusion(
        {"lexical": ["a", "b"], "dense": ["b", "a"]},
    )

    assert {item[0] for item in fused[:2]} == {"a", "b"}


def test_enrich_query_appends_english_aliases() -> None:
    expanded = enrich_query("豁免")
    assert "save" in expanded or "saving" in expanded


def test_enrich_query_preserves_unchanged_query_when_no_match() -> None:
    assert enrich_query("xyz123noop") == "xyz123noop"


def test_enrich_query_merges_extra_terms() -> None:
    expanded = enrich_query("狂暴", extra_terms={"狂暴": ["rage", "frenzy"]})
    assert "rage" in expanded
    assert "frenzy" in expanded


def test_structured_score_prefers_multi_field_match() -> None:
    unstructured = structured_score(
        "宝箱",
        content="There is a room with a chest behind the curtain.",
    )
    structured = structured_score(
        "宝箱",
        keywords="宝箱 treasure chest locked",
        content="The door creaks open.",
    )
    assert structured > unstructured


def test_structured_score_uses_field_weights() -> None:
    title_hit = structured_score(
        "Gate",
        scene_title="Gate",
        content="Nothing here.",
    )
    content_hit = structured_score(
        "Gate",
        scene_title="Other",
        content="The Gate is open. Many gates.",
    )
    # Title match (weight 4.0) should beat partial content match (weight 1.0)
    assert title_hit > content_hit


def test_structured_score_skips_empty_fields() -> None:
    score = structured_score("combat", tags="combat", content="")
    assert score > 0
    assert not math.isnan(score)

