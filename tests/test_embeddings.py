import pytest

from sagasmith_core.embeddings import (
    BgeM3Embedder,
    BgeSmallEnEmbedder,
    BgeSmallZhEmbedder,
    configured_profiles,
    profile_for_language,
)


def test_profiles_preserve_legacy_chinese_and_english_choices(monkeypatch) -> None:
    monkeypatch.setenv(
        "DND_EMBEDDING_PROFILES",
        "bge_small_zh_v1_5,bge_small_en_v1_5",
    )

    assert profile_for_language("zh-CN", env_prefix="DND").language == "zh"
    assert profile_for_language("en", env_prefix="DND").language == "en"


def test_bge_m3_is_the_default(monkeypatch) -> None:
    monkeypatch.delenv("GENERIC_EMBEDDING_PROFILES", raising=False)

    assert configured_profiles("GENERIC")[0].model_name == "BAAI/bge-m3"


def test_explicit_embedder_classes_select_expected_profiles(monkeypatch) -> None:
    monkeypatch.setenv("TTRPG_EMBEDDING_MODE", "cpu")

    assert BgeM3Embedder().dimensions == 1024
    assert BgeSmallZhEmbedder().dimensions == 512
    assert BgeSmallEnEmbedder().dimensions == 384


def test_unknown_profile_fails_early(monkeypatch) -> None:
    monkeypatch.setenv("DND_EMBEDDING_PROFILES", "missing")

    with pytest.raises(ValueError):
        configured_profiles("DND")
