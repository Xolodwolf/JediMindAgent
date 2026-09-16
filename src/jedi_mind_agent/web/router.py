"""Serves the JavaScript web interface. All data goes through the JSON API in `api/v1/product.py`."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(include_in_schema=False)


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
