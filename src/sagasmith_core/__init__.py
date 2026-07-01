"""Shared runtime contracts for SagaSmith system packages."""

from sagasmith_core.campaigns import CampaignService
from sagasmith_core.characters import CharacterService
from sagasmith_core.database import Database
from sagasmith_core.embeddings import (
    BgeM3Embedder,
    BgeSmallEnEmbedder,
    BgeSmallZhEmbedder,
    BgeEmbedder,
    EmbeddingProfile,
    configured_profiles,
    create_embedder,
)
from sagasmith_core.modules import ModuleService
from sagasmith_core.profile import SystemProfile
from sagasmith_core.rules import RuleService
from sagasmith_core.systems import SystemDefinition, SystemRegistry
from sagasmith_core.vector import VectorStore

__all__ = [
    "BgeEmbedder",
    "BgeM3Embedder",
    "BgeSmallEnEmbedder",
    "BgeSmallZhEmbedder",
    "CampaignService",
    "CharacterService",
    "Database",
    "EmbeddingProfile",
    "ModuleService",
    "RuleService",
    "SystemDefinition",
    "SystemRegistry",
    "SystemProfile",
    "VectorStore",
    "configured_profiles",
    "create_embedder",
]

__version__ = "0.1.0"
