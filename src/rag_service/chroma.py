from collections.abc import Iterable
from functools import lru_cache

import chromadb

from rag_service.schemas import ChromaConfig, RetrievalResult, TextChunk

# Chroma rejects very large upserts; a book is written in parts.
UPSERT_BATCH_SIZE = 500


class ChromaRagStore:
    def __init__(self, config: ChromaConfig) -> None:
        self.collection_name = config.collection
        self._collection = _client(config.host, config.port).get_or_create_collection(name=config.collection)

    def count(self) -> int:
        return self._collection.count()

    def upsert_chunks(
        self,
        *,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
        source_slug: str,
        source_title: str,
        source_filename: str,
        file_hash: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        if not chunks:
            return

        ids = [build_document_id(source_slug, chunk) for chunk in chunks]
        metadata = [
            {
                "source_slug": source_slug,
                "source_title": source_title,
                "source_type": "pdf",
                "source_filename": source_filename,
                "file_hash": file_hash,
                "chunk_index": chunk.chunk_index,
                "chunk_hash": chunk.chunk_hash,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "embedding_model": embedding_model,
                "embedding_dimensions": embedding_dimensions,
                "is_exercise": False,
                "level": chunk.level,
            }
            for chunk in chunks
        ]

        for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
            end = start + UPSERT_BATCH_SIZE
            self._collection.upsert(
                ids=ids[start:end],
                documents=[chunk.text for chunk in chunks[start:end]],
                embeddings=embeddings[start:end],
                metadatas=metadata[start:end],
            )

    def delete_source(self, source_slug: str) -> None:
        self._collection.delete(where={"source_slug": source_slug})

    def query(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        source_slug: str | None = None,
        max_level: int | None = None,
    ) -> list[RetrievalResult]:
        clauses: list[dict] = []
        if source_slug:
            clauses.append({"source_slug": source_slug})
        if max_level is not None:
            clauses.append({"level": {"$lte": max_level}})
        where = None if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}

        response = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = _first(response.get("ids"))
        documents = _first(response.get("documents"))
        metadatas = _first(response.get("metadatas"))
        distances = _first(response.get("distances"))

        results: list[RetrievalResult] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] or {}
            distance = distances[index] if index < len(distances) else None
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    text=documents[index] or "",
                    score=float(distance) if distance is not None else None,
                    source_slug=str(metadata.get("source_slug", "")),
                    source_title=str(metadata.get("source_title", "")),
                    source_filename=str(metadata.get("source_filename", "")),
                    page_start=int(metadata.get("page_start", 0)),
                    page_end=int(metadata.get("page_end", 0)),
                    level=int(metadata.get("level") or 0),
                )
            )

        return results


@lru_cache(maxsize=8)
def _client(host: str, port: int) -> chromadb.HttpClient:
    return chromadb.HttpClient(host=host, port=port)


def build_document_id(source_slug: str, chunk: TextChunk) -> str:
    return f"{source_slug}:{chunk.chunk_index}:{chunk.chunk_hash[:12]}"


def _first(value: Iterable | None) -> list:
    if not value:
        return []
    return list(value)[0] or []
