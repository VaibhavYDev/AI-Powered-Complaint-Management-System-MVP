from io import BytesIO

import pytest
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.config import settings
from app.documents import CHUNK_BYTES, Document, DocumentError, extract_pdf, read_upload


def pdf_bytes(pages: list[str]) -> bytes:
    buf = BytesIO()
    canvas = Canvas(buf, pagesize=A4)
    for text in pages:
        canvas.drawString(72, 750, text)
        canvas.showPage()
    canvas.save()
    return buf.getvalue()


# --- bounded reads --------------------------------------------------------------------------

def test_read_upload_returns_the_whole_file_within_the_limit():
    data = b"%PDF-1.4" + b"x" * (CHUNK_BYTES * 2)
    assert read_upload(BytesIO(data)) == data


def test_read_upload_refuses_oversized_input_without_consuming_it_all(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", CHUNK_BYTES)

    class Counting(BytesIO):
        reads = 0

        def read(self, size=-1):
            Counting.reads += 1
            return super().read(size)

    oversized = Counting(b"x" * (CHUNK_BYTES * 50))
    with pytest.raises(DocumentError, match="exceeds"):
        read_upload(oversized)
    assert Counting.reads < 50  # stopped early instead of buffering the whole upload


# --- parsing --------------------------------------------------------------------------------

@pytest.mark.parametrize("data, match", [
    (b"", "empty"),
    (b"hello world", "Only PDF"),
    (b"%PDF-1.4 garbage", "could not be read"),
])
def test_invalid_input_is_rejected(data, match):
    with pytest.raises(DocumentError, match=match):
        extract_pdf(data)


def test_pdf_without_extractable_text_is_rejected():
    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buf)
    with pytest.raises(DocumentError, match="No text"):
        extract_pdf(buf.getvalue())


def test_encrypted_pdf_is_rejected():
    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    writer.write(buf)
    with pytest.raises(DocumentError, match="Encrypted"):
        extract_pdf(buf.getvalue())


def test_multi_page_text_carries_page_references():
    document = extract_pdf(pdf_bytes(["Batch PCM24031 chipped", "Sample retained", "Signed by QA"]))
    assert document.page_count == 3 and len(document.pages) == 3
    assert not document.truncated
    assert "[page 2]" in document.text and "Sample retained" in document.text


def test_page_limit_truncates_and_says_so(monkeypatch):
    monkeypatch.setattr(settings, "max_pdf_pages", 2)
    document = extract_pdf(pdf_bytes([f"page {i}" for i in range(6)]))
    assert len(document.pages) == 2 and document.page_count == 6
    assert document.truncated and "[document truncated]" in document.text


def test_character_limit_truncates_and_says_so(monkeypatch):
    monkeypatch.setattr(settings, "max_document_chars", 20)
    document = extract_pdf(pdf_bytes(["A" * 200, "B" * 200]))
    assert document.truncated
    assert sum(len(p) for p in document.pages) <= 20
    assert "[document truncated]" in document.text


def test_time_limit_stops_parsing(monkeypatch):
    monkeypatch.setattr(settings, "max_pdf_seconds", -1.0)
    with pytest.raises(DocumentError, match="too long"):
        extract_pdf(pdf_bytes(["one", "two"]))


def test_a_single_slow_page_cannot_hang_the_request(monkeypatch):
    """A page that spins inside pypdf must not hold the request open."""
    import time as clock

    monkeypatch.setattr(settings, "max_pdf_seconds", 0.3)
    data = pdf_bytes(["fast page", "slow page"])

    original = __import__("pypdf")._page.PageObject.extract_text
    calls = {"n": 0}

    def maybe_slow(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            clock.sleep(10)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(__import__("pypdf")._page.PageObject, "extract_text", maybe_slow)
    started = clock.monotonic()
    document = extract_pdf(data)
    assert clock.monotonic() - started < 5  # abandoned, not awaited
    assert document.truncated and document.pages == ["fast page"]


def test_document_text_is_empty_without_pages():
    assert Document().text == ""
