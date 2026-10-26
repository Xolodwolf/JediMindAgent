from collections import Counter
from pathlib import Path

from rag_service.chroma import ChromaRagStore
from rag_service.chunking import chunk_pages, content_hash
from rag_service.config import EMBEDDING_MODEL
from rag_service.embeddings import LocalEmbeddingService
from rag_service.levels import assign_levels
from rag_service.pdf import extract_pdf_pages
from rag_service.schemas import IngestionSummary


def ingest_pdf(
    path: Path,
    *,
    source_slug: str,
    source_title: str,
    store: ChromaRagStore,
    embeddings: LocalEmbeddingService,
) -> IngestionSummary:
    """Parse the PDF, tag chunks with book levels, embed them and replace the source's chunks in ChromaDB."""
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")

    file_hash = content_hash(path.read_bytes())
    pages = extract_pdf_pages(path)
    chunks = assign_levels(chunk_pages(pages))
    if not chunks:
        raise ValueError("В PDF не найден текст: возможно, это скан без текстового слоя.")

    vectors = embeddings.embed([chunk.text for chunk in chunks])
    # Embeddings are computed before anything is deleted, so a failure leaves the previous version searchable.
    store.delete_source(source_slug)
    store.upsert_chunks(
        chunks=chunks,
        embeddings=vectors,
        source_slug=source_slug,
        source_title=source_title,
        source_filename=path.name,
        file_hash=file_hash,
        embedding_model=EMBEDDING_MODEL,
        embedding_dimensions=len(vectors[0]),
    )

    return IngestionSummary(
        source_slug=source_slug,
        source_title=source_title,
        source_filename=path.name,
        file_hash=file_hash,
        page_count=len(pages),
        chunk_count=len(chunks),
        chunks_by_level=dict(sorted(Counter(chunk.level for chunk in chunks).items())),
        collection=store.collection_name,
        embedding_model=EMBEDDING_MODEL,
    )
