from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rag_service.chunking import chunk_pages, content_hash
from rag_service.embeddings import LocalEmbeddingService
from rag_service.levels import assign_levels
from rag_service.pdf import extract_pdf_pages
from rag_service.schemas import TextChunk


@dataclass
class PreparedBook:
    """A parsed and embedded book, ready to be written to `rag_chunks`."""

    file_hash: str
    page_count: int
    chunks: list[TextChunk]
    embeddings: list[list[float]] = field(repr=False)

    @property
    def chunks_by_level(self) -> dict[int, int]:
        return dict(sorted(Counter(chunk.level for chunk in self.chunks).items()))


def prepare_pdf(path: Path, *, embeddings: LocalEmbeddingService) -> PreparedBook:
    """Parse the PDF, tag chunks with book levels and embed them. Touches no storage."""
    if not path.exists():
        raise FileNotFoundError(f"PDF не найден: {path.name}. Загрузите файл заново.")

    pages = extract_pdf_pages(path)
    chunks = assign_levels(chunk_pages(pages))
    if not chunks:
        raise ValueError("В PDF не найден текст: возможно, это скан без текстового слоя.")

    return PreparedBook(
        file_hash=content_hash(path.read_bytes()),
        page_count=len(pages),
        chunks=chunks,
        embeddings=embeddings.embed([chunk.text for chunk in chunks]),
    )
