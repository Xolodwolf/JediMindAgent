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


class RetrievalResult(BaseModel):
    chunk_id: str
    text: str
    score: float | None = None
    source_slug: str
    source_title: str
    source_filename: str
    page_start: int
    page_end: int
    level: int = 0


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    source_slug: str | None = Field(default=None, min_length=1, max_length=120)
    max_level: int | None = Field(default=None, ge=0, le=5, description="Only chunks with level <= max_level.")


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievalResult]
