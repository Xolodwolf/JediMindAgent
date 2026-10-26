import hashlib

from rag_service.config import CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS
from rag_service.schemas import PageText, TextChunk


def content_hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def chunk_pages(pages: list[PageText]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    buffer = ""
    page_start: int | None = None
    page_end: int | None = None

    for page in pages:
        page_text = page.text.strip()
        if not page_text:
            continue

        if page_start is None:
            page_start = page.page_number

        page_end = page.page_number
        buffer = f"{buffer}\n\n{page_text}".strip() if buffer else page_text

        while len(buffer) >= CHUNK_TARGET_CHARS:
            chunk_text = buffer[:CHUNK_TARGET_CHARS].strip()
            chunks.append(_build_chunk(len(chunks), chunk_text, page_start, page_end))

            overlap = buffer[CHUNK_TARGET_CHARS - CHUNK_OVERLAP_CHARS : CHUNK_TARGET_CHARS]
            buffer = f"{overlap}{buffer[CHUNK_TARGET_CHARS:]}".strip()
            page_start = page.page_number

    if buffer and page_start is not None and page_end is not None:
        chunks.append(_build_chunk(len(chunks), buffer.strip(), page_start, page_end))

    return chunks


def _build_chunk(index: int, text: str, page_start: int, page_end: int) -> TextChunk:
    return TextChunk(
        chunk_index=index,
        text=text,
        page_start=page_start,
        page_end=page_end,
        chunk_hash=content_hash(text),
    )
