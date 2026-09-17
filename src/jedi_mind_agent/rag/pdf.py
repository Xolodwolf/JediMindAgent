import re
from pathlib import Path

from pypdf import PdfReader

from jedi_mind_agent.rag.schemas import PageText

# pypdf separates words in this book with tabs; runs of tabs and spaces become a single space.
_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t ]+")


def extract_pdf_pages(path: Path) -> list[PageText]:
    reader = PdfReader(str(path))
    pages: list[PageText] = []

    for index, page in enumerate(reader.pages, start=1):
        normalized = normalize_text(page.extract_text() or "")
        if normalized:
            pages.append(PageText(page_number=index, text=normalized))

    return pages


def normalize_text(text: str) -> str:
    lines = (_HORIZONTAL_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)
