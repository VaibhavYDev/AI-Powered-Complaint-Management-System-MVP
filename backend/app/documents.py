"""PDF intake: bounded reads, bounded parsing, and text carrying page references."""

import time
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .config import settings

CHUNK_BYTES = 64 * 1024


class DocumentError(ValueError):
    pass


@dataclass
class Document:
    """Extracted text per page, index 0 being page 1."""

    pages: list[str] = field(default_factory=list)
    page_count: int = 0
    truncated: bool = False

    @property
    def text(self) -> str:
        body = "\n\n".join(f"[page {n}]\n{t}" for n, t in enumerate(self.pages, 1) if t)
        return body + ("\n\n[document truncated]" if self.truncated else "")


def read_upload(stream) -> bytes:
    """Read the upload one chunk at a time and refuse it as soon as it exceeds the limit,
    so an oversized file is never held in memory in full."""
    limit = settings.max_upload_bytes
    chunks, total = [], 0
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise DocumentError(f"File exceeds the {limit // (1024 * 1024)} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def extract_pdf(data: bytes) -> Document:
    if not data:
        raise DocumentError("The uploaded file is empty.")
    if not data.startswith(b"%PDF"):
        raise DocumentError("Only PDF files are supported.")
    if len(data) > settings.max_upload_bytes:
        raise DocumentError(f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit.")

    buffer = BytesIO(data)
    try:
        reader = PdfReader(buffer)
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are not supported.")
        document = _read_pages(reader)
    except DocumentError:
        raise
    except (PyPdfError, ValueError, OSError, RecursionError) as exc:
        raise DocumentError("The PDF could not be read; it may be corrupted.") from exc
    finally:
        buffer.close()

    if not any(document.pages):
        raise DocumentError(
            "No text could be extracted. Scanned/image-only PDFs are not supported in this version."
        )
    return document


def _read_pages(reader: PdfReader) -> Document:
    """Page, character and wall-clock limits are applied while reading, so a crafted
    document cannot turn into unbounded work."""
    deadline = time.monotonic() + settings.max_pdf_seconds
    document = Document(page_count=len(reader.pages))
    budget = settings.max_document_chars

    for page in reader.pages[: settings.max_pdf_pages]:
        if time.monotonic() > deadline:
            document.truncated = True
            break
        text = (page.extract_text() or "").strip()
        if len(text) > budget:
            text, document.truncated = text[:budget], True
        budget -= len(text)
        document.pages.append(text)
        if budget <= 0:
            document.truncated = True
            break

    if document.page_count > len(document.pages):
        document.truncated = True
    return document
