from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.documents import DocumentError, extract_pdf_text


def test_rejects_non_pdf_and_empty():
    with pytest.raises(DocumentError):
        extract_pdf_text(b"")
    with pytest.raises(DocumentError, match="Only PDF"):
        extract_pdf_text(b"hello world")


def test_rejects_pdf_without_text():
    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buf)
    with pytest.raises(DocumentError, match="No text"):
        extract_pdf_text(buf.getvalue())


def test_rejects_corrupt_pdf():
    with pytest.raises(DocumentError):
        extract_pdf_text(b"%PDF-1.4 garbage")
