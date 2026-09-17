from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .config import settings


class DocumentError(ValueError):
    pass


def extract_pdf_text(data: bytes) -> str:
    if not data:
        raise DocumentError("The uploaded file is empty.")
    if not data.startswith(b"%PDF"):
        raise DocumentError("Only PDF files are supported.")
    if len(data) > settings.max_upload_bytes:
        raise DocumentError(f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit.")

    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are not supported.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise DocumentError("The PDF could not be read; it may be corrupted.") from exc

    text = "\n\n".join(p.strip() for p in pages if p.strip()).strip()
    if not text:
        raise DocumentError(
            "No text could be extracted. Scanned/image-only PDFs are not supported in this version."
        )
    if len(text) > settings.max_document_chars:
        text = text[: settings.max_document_chars] + "\n[document truncated]"
    return text
