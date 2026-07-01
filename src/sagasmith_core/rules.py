"""Rule parsing, ingestion, expansion, and hybrid retrieval."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select

from sagasmith_core.database import Database
from sagasmith_core.embeddings import Embedder
from sagasmith_core.models import RuleChunk, RuleSection, RuleSource
from sagasmith_core.parsing import MarkdownHierarchyParser
from sagasmith_core.retrieval import (
    SearchHit,
    cosine_similarity,
    lexical_score,
    reciprocal_rank_fusion,
)
from sagasmith_core.vector import VectorStore


@dataclass(frozen=True)
class RuleIngestResult:
    source_id: str
    skipped: bool
    sections: int
    chunks: int
    embeddings: int


class RuleService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ingest(
        self,
        *,
        system_id: str,
        source_key: str,
        title: str,
        content: str,
        locale: str = "en",
        version: str = "",
        metadata: dict[str, Any] | None = None,
        parser: MarkdownHierarchyParser | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ) -> RuleIngestResult:
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        parsed = (parser or MarkdownHierarchyParser()).parse(content)
        with self.database.transaction() as session:
            existing = session.scalar(
                select(RuleSource).where(
                    RuleSource.system_id == system_id,
                    RuleSource.source_key == source_key,
                )
            )
            if existing and existing.checksum == checksum:
                chunk_count = session.query(RuleChunk).filter_by(source_id=existing.id).count()
                section_count = session.query(RuleSection).filter_by(source_id=existing.id).count()
                return RuleIngestResult(existing.id, True, section_count, chunk_count, 0)
            if existing:
                session.execute(delete(RuleSource).where(RuleSource.id == existing.id))
                session.flush()

            source_id = str(uuid.uuid4())
            session.add(
                RuleSource(
                    id=source_id,
                    system_id=system_id,
                    source_key=source_key,
                    title=title,
                    locale=locale,
                    version=version,
                    checksum=checksum,
                    metadata_json=metadata or {},
                )
            )
            session.flush()
            section_ids: dict[tuple[str, ...], str] = {}
            embedding_count = 0
            chunk_count = 0
            vector_ids: list[str] = []
            vector_values: list[list[float]] = []
            vector_metadata: list[dict[str, Any]] = []
            vector_documents: list[str] = []
            for section in parsed:
                section_id = str(uuid.uuid4())
                parent_id = section_ids.get(section.path[:-1])
                section_ids[section.path] = section_id
                session.add(
                    RuleSection(
                        id=section_id,
                        source_id=source_id,
                        parent_id=parent_id,
                        ordinal=section.ordinal,
                        level=section.level,
                        title=section.title,
                        path=list(section.path),
                        content=section.content,
                        start_offset=section.start_offset,
                        end_offset=section.end_offset,
                    )
                )
                session.flush()
                chunk_texts = [chunk.content for chunk in section.chunks]
                vectors = embedder.encode(chunk_texts) if embedder else [None] * len(chunk_texts)
                for chunk, vector in zip(section.chunks, vectors, strict=True):
                    chunk_id = str(uuid.uuid4())
                    session.add(
                        RuleChunk(
                            id=chunk_id,
                            source_id=source_id,
                            section_id=section_id,
                            ordinal=chunk_count,
                            heading_path=list(chunk.heading_path),
                            content=chunk.content,
                            token_count=max(1, len(chunk.content) // 4),
                            embedding_model=embedder.model_name if embedder else None,
                            embedding_json=vector,
                            metadata_json={
                                **chunk.metadata,
                                "start_offset": chunk.start_offset,
                                "end_offset": chunk.end_offset,
                            },
                        )
                    )
                    chunk_count += 1
                    embedding_count += int(vector is not None)
                    if vector is not None:
                        vector_ids.append(chunk_id)
                        vector_values.append(vector)
                        vector_metadata.append(
                            {
                                "system_id": system_id,
                                "source_id": source_id,
                                "section_id": section_id,
                            }
                        )
                        vector_documents.append(chunk.content)
            if vector_store and vector_values:
                vector_store.upsert(
                    "rules",
                    ids=vector_ids,
                    embeddings=vector_values,
                    metadatas=vector_metadata,
                    documents=vector_documents,
                    profile=getattr(embedder, "profile", None),
                )
            return RuleIngestResult(
                source_id,
                False,
                len(parsed),
                chunk_count,
                embedding_count,
            )

    def search(
        self,
        *,
        system_id: str,
        query: str,
        top_k: int = 8,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ) -> list[SearchHit]:
        with self.database.transaction() as session:
            rows = session.execute(
                select(RuleChunk, RuleSection, RuleSource)
                .join(RuleSection, RuleSection.id == RuleChunk.section_id)
                .join(RuleSource, RuleSource.id == RuleChunk.source_id)
                .where(RuleSource.system_id == system_id)
            ).all()
        if not rows:
            return []

        exact = [
            row
            for row in rows
            if row.RuleSection.title.casefold() == query.casefold()
            or row.RuleSource.title.casefold() == query.casefold()
        ]
        lexical = sorted(
            rows,
            key=lambda row: -lexical_score(
                query,
                title=row.RuleSection.title,
                content=row.RuleChunk.content,
            ),
        )
        rankings = {
            "exact": [row.RuleChunk.id for row in exact],
            "lexical": [row.RuleChunk.id for row in lexical],
        }
        if embedder:
            query_vector = embedder.encode([query])[0]
            if vector_store and vector_store.enabled:
                rankings["dense"] = [
                    item_id
                    for item_id, _score in vector_store.query(
                        "rules",
                        query_embedding=query_vector,
                        limit=max(top_k * 4, 20),
                        where={"system_id": system_id},
                        profile=getattr(embedder, "profile", None),
                    )
                    if item_id in {row.RuleChunk.id for row in rows}
                ]
            else:
                dense = sorted(
                    (
                        (
                            cosine_similarity(query_vector, row.RuleChunk.embedding_json or []),
                            row,
                        )
                        for row in rows
                        if row.RuleChunk.embedding_model == embedder.model_name
                    ),
                    key=lambda item: -item[0],
                )
                rankings["dense"] = [row.RuleChunk.id for _, row in dense]

        by_id = {row.RuleChunk.id: row for row in rows}
        fused = reciprocal_rank_fusion(
            rankings,
            weights={"exact": 1.5, "lexical": 1.0, "dense": 1.0},
        )
        hits: list[SearchHit] = []
        for chunk_id, score, retrieval in fused[:top_k]:
            row = by_id[chunk_id]
            hits.append(
                SearchHit(
                    id=chunk_id,
                    score=score,
                    title=row.RuleSection.title,
                    content=row.RuleChunk.content,
                    source_id=row.RuleSource.id,
                    heading_path=tuple(row.RuleChunk.heading_path),
                    retrieval=retrieval,
                    metadata={
                        "source_key": row.RuleSource.source_key,
                        "version": row.RuleSource.version,
                        "locale": row.RuleSource.locale,
                    },
                )
            )
        return hits

    def expand(self, chunk_id: str) -> dict[str, Any]:
        with self.database.transaction() as session:
            row = session.execute(
                select(RuleChunk, RuleSection, RuleSource)
                .join(RuleSection, RuleSection.id == RuleChunk.section_id)
                .join(RuleSource, RuleSource.id == RuleChunk.source_id)
                .where(RuleChunk.id == chunk_id)
            ).one()
            return {
                "chunk_id": row.RuleChunk.id,
                "section_id": row.RuleSection.id,
                "title": row.RuleSection.title,
                "path": list(row.RuleSection.path),
                "content": row.RuleSection.content,
                "source": {
                    "id": row.RuleSource.id,
                    "key": row.RuleSource.source_key,
                    "title": row.RuleSource.title,
                    "version": row.RuleSource.version,
                    "locale": row.RuleSource.locale,
                },
            }
