import argparse
import re
from pathlib import Path

from jedi_mind_agent.rag.chroma import ChromaRagStore
from jedi_mind_agent.rag.chunking import chunk_pages, content_hash
from jedi_mind_agent.rag.config import CHROMA_COLLECTION, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from jedi_mind_agent.rag.embeddings import LocalEmbeddingService
from jedi_mind_agent.rag.pdf import extract_pdf_pages
from jedi_mind_agent.rag.schemas import IngestionSummary


def ingest_pdf(
    path: Path,
    *,
    source_slug: str | None = None,
    source_title: str | None = None,
    replace: bool = False,
) -> IngestionSummary:
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {path}")

    slug = slugify(source_slug or path.stem)
    title = source_title or path.stem
    file_hash = content_hash(path.read_bytes())

    pages = extract_pdf_pages(path)
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError(f"No text chunks extracted from PDF: {path}")

    embeddings = LocalEmbeddingService().embed([chunk.text for chunk in chunks])
    store = ChromaRagStore()
    if replace:
        store.delete_source(slug)
    store.upsert_chunks(
        chunks=chunks,
        embeddings=embeddings,
        source_slug=slug,
        source_title=title,
        source_filename=path.name,
        file_hash=file_hash,
        embedding_model=EMBEDDING_MODEL,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
    )

    return IngestionSummary(
        source_slug=slug,
        source_title=title,
        source_filename=path.name,
        file_hash=file_hash,
        page_count=len(pages),
        chunk_count=len(chunks),
        collection=CHROMA_COLLECTION,
        embedding_model=EMBEDDING_MODEL,
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.lower()).strip("-")
    return slug or "source"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a PDF source into the local RAG ChromaDB collection.")
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--source-slug", default=None)
    parser.add_argument("--source-title", default=None)
    parser.add_argument("--replace", action="store_true", help="Delete existing chunks for this source slug before upsert.")
    args = parser.parse_args()

    summary = ingest_pdf(
        args.pdf_path,
        source_slug=args.source_slug,
        source_title=args.source_title,
        replace=args.replace,
    )
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
