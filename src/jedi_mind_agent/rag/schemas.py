from pydantic import BaseModel, Field


class PageText(BaseModel):
    page_number: int
    text: str


class TextChunk(BaseModel):
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    chunk_hash: str
    level: int = 0  # 0 — general material, 1–5 — the level section of the book


class RagSource(BaseModel):
    chunk_id: str
    source_slug: str
    source_title: str
    source_filename: str
    page_start: int
    page_end: int
    score: float | None = None


class RetrievalResult(RagSource):
    text: str
    level: int = 0


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    source_slug: str | None = Field(default=None, min_length=1, max_length=120)
    max_level: int | None = Field(default=None, ge=0, le=5, description="Only chunks with level <= max_level.")


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievalResult]


class RagUsage(BaseModel):
    used: bool
    sources: list[RagSource] = Field(default_factory=list)


class IngestionSummary(BaseModel):
    source_slug: str
    source_title: str
    source_filename: str
    file_hash: str
    page_count: int
    chunk_count: int
    chunks_by_level: dict[int, int]
    collection: str
    embedding_model: str
