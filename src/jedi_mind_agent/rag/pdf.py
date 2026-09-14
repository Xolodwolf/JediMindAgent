from pathlib import Path

from pypdf import PdfReader

from jedi_mind_agent.rag.schemas import PageText


def extract_pdf_pages(path: Path) -> list[PageText]:
    reader = PdfReader(str(path))
    pages: list[PageText] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if normalized:
            pages.append(PageText(page_number=index, text=normalized))

    return pages
