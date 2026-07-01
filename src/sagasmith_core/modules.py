"""Adventure-module parsing, ingestion, search, and scene progress."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sagasmith_core.campaigns import CampaignNotFoundError
from sagasmith_core.database import Database
from sagasmith_core.embeddings import Embedder
from sagasmith_core.models import (
    Campaign,
    ModuleChapter,
    ModuleChunk,
    ModuleScene,
    ModuleSource,
    SceneProgress,
)
from sagasmith_core.parsing import MarkdownHierarchyParser, ParsedSection
from sagasmith_core.retrieval import (
    SearchHit,
    cosine_similarity,
    lexical_score,
    reciprocal_rank_fusion,
)
from sagasmith_core.vector import VectorStore


@dataclass(frozen=True)
class ParsedScene:
    ordinal: int
    title: str
    content: str
    heading_path: tuple[str, ...]
    chunks: tuple
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedChapter:
    ordinal: int
    title: str
    content: str
    scenes: tuple[ParsedScene, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


class MarkdownModuleParser:
    """Interpret H1 as chapters and H2+ as scenes."""

    def __init__(self, hierarchy_parser: MarkdownHierarchyParser | None = None) -> None:
        self.hierarchy_parser = hierarchy_parser or MarkdownHierarchyParser()

    def parse(self, content: str) -> list[ParsedChapter]:
        sections = self.hierarchy_parser.parse(content)
        chapters: list[tuple[ParsedSection, list[ParsedSection]]] = []
        for section in sections:
            if section.level == 1 or not chapters:
                chapters.append((section, []))
            else:
                chapters[-1][1].append(section)

        parsed: list[ParsedChapter] = []
        for chapter_ordinal, (chapter, children) in enumerate(chapters):
            scene_sections = children or [chapter]
            scenes = tuple(
                ParsedScene(
                    ordinal=scene_ordinal,
                    title=scene.title,
                    content=scene.content,
                    heading_path=scene.path,
                    chunks=scene.chunks,
                )
                for scene_ordinal, scene in enumerate(scene_sections)
            )
            parsed.append(
                ParsedChapter(
                    ordinal=chapter_ordinal,
                    title=chapter.title,
                    content=chapter.content,
                    scenes=scenes,
                )
            )
        return parsed


@dataclass(frozen=True)
class ModuleIngestResult:
    module_id: str
    skipped: bool
    chapters: int
    scenes: int
    chunks: int
    embeddings: int


class ModuleService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ingest(
        self,
        *,
        campaign_id: str,
        source_key: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        parser: MarkdownModuleParser | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ) -> ModuleIngestResult:
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        parsed = (parser or MarkdownModuleParser()).parse(content)
        with self.database.transaction() as session:
            campaign = session.get(Campaign, campaign_id)
            if campaign is None:
                raise CampaignNotFoundError(campaign_id)
            existing = session.scalar(
                select(ModuleSource).where(
                    ModuleSource.campaign_id == campaign_id,
                    ModuleSource.source_key == source_key,
                )
            )
            if existing and existing.checksum == checksum:
                counts = self._counts(session, existing.id)
                return ModuleIngestResult(existing.id, True, *counts, 0)
            if existing:
                session.execute(delete(ModuleSource).where(ModuleSource.id == existing.id))
                session.flush()

            module_id = str(uuid.uuid4())
            session.add(
                ModuleSource(
                    id=module_id,
                    system_id=campaign.system_id,
                    campaign_id=campaign_id,
                    source_key=source_key,
                    title=title,
                    checksum=checksum,
                    metadata_json=metadata or {},
                )
            )
            session.flush()
            scene_count = 0
            chunk_count = 0
            embedding_count = 0
            vector_ids: list[str] = []
            vector_values: list[list[float]] = []
            vector_metadata: list[dict[str, Any]] = []
            vector_documents: list[str] = []
            for chapter in parsed:
                chapter_id = str(uuid.uuid4())
                session.add(
                    ModuleChapter(
                        id=chapter_id,
                        module_id=module_id,
                        ordinal=chapter.ordinal,
                        title=chapter.title,
                        content=chapter.content,
                        metadata_json=chapter.metadata,
                    )
                )
                session.flush()
                for scene in chapter.scenes:
                    scene_id = str(uuid.uuid4())
                    session.add(
                        ModuleScene(
                            id=scene_id,
                            module_id=module_id,
                            chapter_id=chapter_id,
                            ordinal=scene.ordinal,
                            title=scene.title,
                            content=scene.content,
                            metadata_json=scene.metadata,
                        )
                    )
                    session.flush()
                    texts = [chunk.content for chunk in scene.chunks]
                    vectors = embedder.encode(texts) if embedder else [None] * len(texts)
                    for chunk, vector in zip(scene.chunks, vectors, strict=True):
                        chunk_id = str(uuid.uuid4())
                        session.add(
                            ModuleChunk(
                                id=chunk_id,
                                module_id=module_id,
                                scene_id=scene_id,
                                ordinal=chunk_count,
                                heading_path=list(chunk.heading_path),
                                content=chunk.content,
                                token_count=max(1, len(chunk.content) // 4),
                                embedding_model=embedder.model_name if embedder else None,
                                embedding_json=vector,
                                metadata_json=chunk.metadata,
                            )
                        )
                        chunk_count += 1
                        embedding_count += int(vector is not None)
                        if vector is not None:
                            vector_ids.append(chunk_id)
                            vector_values.append(vector)
                            vector_metadata.append(
                                {
                                    "system_id": campaign.system_id,
                                    "campaign_id": campaign_id,
                                    "module_id": module_id,
                                    "scene_id": scene_id,
                                }
                            )
                            vector_documents.append(chunk.content)
                    scene_count += 1
            if vector_store and vector_values:
                vector_store.upsert(
                    "modules",
                    ids=vector_ids,
                    embeddings=vector_values,
                    metadatas=vector_metadata,
                    documents=vector_documents,
                    profile=getattr(embedder, "profile", None),
                )
            return ModuleIngestResult(
                module_id,
                False,
                len(parsed),
                scene_count,
                chunk_count,
                embedding_count,
            )

    def ingest_path(
        self,
        *,
        campaign_id: str,
        path: str | Path,
        source_key: str | None = None,
        title: str | None = None,
        parser: MarkdownModuleParser | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ) -> ModuleIngestResult:
        source_path = Path(path).expanduser().resolve()
        if source_path.suffix.casefold() == ".pdf":
            content = self._pdf_to_text(source_path)
        else:
            content = source_path.read_text(encoding="utf-8")
        return self.ingest(
            campaign_id=campaign_id,
            source_key=source_key or source_path.name,
            title=title or source_path.stem,
            content=content,
            metadata={"source_path": str(source_path)},
            parser=parser,
            embedder=embedder,
            vector_store=vector_store,
        )

    @staticmethod
    def _pdf_to_text(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF modules require `pip install sagasmith-core[documents]`"
            ) from exc
        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append(f"\n\n<!-- page:{index} -->\n\n{page.extract_text() or ''}")
        return "".join(pages)

    def search(
        self,
        *,
        campaign_id: str,
        query: str,
        top_k: int = 8,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ) -> list[SearchHit]:
        with self.database.transaction() as session:
            rows = session.execute(
                select(ModuleChunk, ModuleScene, ModuleSource)
                .join(ModuleScene, ModuleScene.id == ModuleChunk.scene_id)
                .join(ModuleSource, ModuleSource.id == ModuleChunk.module_id)
                .where(
                    ModuleSource.campaign_id == campaign_id,
                    ModuleSource.active.is_(True),
                )
            ).all()
        if not rows:
            return []

        exact = [
            row
            for row in rows
            if row.ModuleScene.title.casefold() == query.casefold()
            or row.ModuleSource.title.casefold() == query.casefold()
        ]
        lexical = sorted(
            rows,
            key=lambda row: -lexical_score(
                query,
                title=row.ModuleScene.title,
                content=row.ModuleChunk.content,
            ),
        )
        rankings = {
            "exact": [row.ModuleChunk.id for row in exact],
            "lexical": [row.ModuleChunk.id for row in lexical],
        }
        if embedder:
            query_vector = embedder.encode([query])[0]
            if vector_store and vector_store.enabled:
                rankings["dense"] = [
                    item_id
                    for item_id, _score in vector_store.query(
                        "modules",
                        query_embedding=query_vector,
                        limit=max(top_k * 4, 20),
                        where={"campaign_id": campaign_id},
                        profile=getattr(embedder, "profile", None),
                    )
                    if item_id in {row.ModuleChunk.id for row in rows}
                ]
            else:
                dense = sorted(
                    (
                        (
                            cosine_similarity(query_vector, row.ModuleChunk.embedding_json or []),
                            row,
                        )
                        for row in rows
                        if row.ModuleChunk.embedding_model == embedder.model_name
                    ),
                    key=lambda item: -item[0],
                )
                rankings["dense"] = [row.ModuleChunk.id for _, row in dense]

        by_id = {row.ModuleChunk.id: row for row in rows}
        hits = []
        for chunk_id, score, retrieval in reciprocal_rank_fusion(rankings)[:top_k]:
            row = by_id[chunk_id]
            hits.append(
                SearchHit(
                    id=chunk_id,
                    score=score,
                    title=row.ModuleScene.title,
                    content=row.ModuleChunk.content,
                    source_id=row.ModuleSource.id,
                    heading_path=tuple(row.ModuleChunk.heading_path),
                    retrieval=retrieval,
                    metadata={
                        "campaign_id": row.ModuleSource.campaign_id,
                        "module_title": row.ModuleSource.title,
                        "scene_id": row.ModuleScene.id,
                    },
                )
            )
        return hits

    def set_scene_progress(
        self,
        *,
        campaign_id: str,
        scene_id: str,
        status: str = "current",
        progress: int = 0,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress = max(0, min(100, progress))
        with self.database.transaction() as session:
            scene = session.get(ModuleScene, scene_id)
            if scene is None:
                raise LookupError(scene_id)
            source = session.get(ModuleSource, scene.module_id)
            if source is None or source.campaign_id != campaign_id:
                raise ValueError("scene does not belong to campaign")
            row = session.scalar(
                select(SceneProgress).where(
                    SceneProgress.campaign_id == campaign_id,
                    SceneProgress.scene_id == scene_id,
                )
            )
            if row is None:
                row = SceneProgress(
                    id=str(uuid.uuid4()),
                    campaign_id=campaign_id,
                    scene_id=scene_id,
                )
                session.add(row)
            row.status = status
            row.progress = progress
            row.state = state or {}
            session.flush()
            return {
                "id": row.id,
                "campaign_id": row.campaign_id,
                "scene_id": row.scene_id,
                "status": row.status,
                "progress": row.progress,
                "state": dict(row.state),
            }

    @staticmethod
    def _counts(session, module_id: str) -> tuple[int, int, int]:
        chapters = session.query(ModuleChapter).filter_by(module_id=module_id).count()
        scenes = session.query(ModuleScene).filter_by(module_id=module_id).count()
        chunks = session.query(ModuleChunk).filter_by(module_id=module_id).count()
        return chapters, scenes, chunks
