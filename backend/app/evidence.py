"""Field-level provenance.

Every extracted value is looked up in the text it came from. Nothing here asks the model where
it found something - a model that invents a batch number will just as happily invent a citation -
so the check is a deterministic search over the source.

A match proves the characters are present, not that they mean what the field says they mean. That
is why a located value is still only a reviewer's starting point, and why the statuses below
distinguish "quoted" from "judged".
"""

import re
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from types import NoneType, UnionType
from typing import Any, get_args

from .schemas import SECTIONS, ComplaintData

VERBATIM = "verbatim"        # found exactly as written
NORMALIZED = "normalized"    # found allowing for case, spacing or date format
DERIVED = "derived"          # a judgement (yes/no, a category, a summary), not a quotation
UNSUPPORTED = "unsupported"  # an identifier-like value that is not in the source at all

# Fields the model is expected to paraphrase rather than quote.
PARAPHRASED = {"complaint_description", "defect_description"}
PAGE_MARKER = re.compile(r"\[page (\d+)\]")
EXCERPT_PADDING = 50


@dataclass
class FieldEvidence:
    status: str
    excerpt: str | None = None
    offset: int | None = None
    page: int | None = None


def verify_values(values: dict[str, Any], source: str, judgements: set[str] = frozenset()) -> dict:
    """Evidence for each populated value, keyed by its path.

    `judgements` names paths whose value is interpreted rather than quoted, so that not finding
    it in the source is expected instead of suspicious.
    """
    pages = _page_spans(source)
    haystack = source.casefold()
    evidence: dict[str, dict] = {}

    for path, value in values.items():
        if value is None:
            continue
        found = _locate(value, source, haystack)
        if found is None:
            status = DERIVED if path in judgements else UNSUPPORTED
            evidence[path] = asdict(FieldEvidence(status=status))
            continue
        status, offset, length = found
        evidence[path] = asdict(
            FieldEvidence(
                status=status,
                excerpt=_excerpt(source, offset, length),
                offset=offset,
                page=_page_of(offset, pages),
            )
        )
    return evidence


def verify(data: ComplaintData, source: str) -> dict:
    """Evidence for every populated complaint field, keyed by "section.field"."""
    values: dict[str, Any] = {}
    judgements: set[str] = set()
    for section, model in SECTIONS.items():
        populated = getattr(data, section)
        for name, field in model.model_fields.items():
            value = getattr(populated, name)
            path = f"{section}.{name}"
            values[path] = value
            if value is not None and _is_judgement(field.annotation, name, value):
                judgements.add(path)
    return verify_values(values, source, judgements)


def summarize(data: ComplaintData, evidence: dict) -> dict:
    """What a reviewer needs to look at first."""
    unsupported = sorted(p for p, e in evidence.items() if e["status"] == UNSUPPORTED)
    derived = sorted(p for p, e in evidence.items() if e["status"] == DERIVED)
    missing = sorted(
        f"{section}.{name}"
        for section, model in SECTIONS.items()
        for name in model.model_fields
        if getattr(getattr(data, section), name) is None
    )
    return {
        "unsupported": unsupported,
        "derived": derived,
        "missing": missing,
        "quoted": len(evidence) - len(unsupported) - len(derived),
    }


def _is_judgement(annotation: Any, name: str, value: Any) -> bool:
    if isinstance(value, bool) or name in PARAPHRASED:
        return True
    inner = [a for a in get_args(annotation) if a is not NoneType] if isinstance(annotation, UnionType) else [annotation]
    return bool(inner) and isinstance(inner[0], type) and issubclass(inner[0], Enum)


def _candidates(value: Any) -> list[str]:
    if isinstance(value, date):
        return [
            value.isoformat(),
            value.strftime("%d %B %Y").lstrip("0"),
            value.strftime("%d %b %Y").lstrip("0"),
            value.strftime("%B %d, %Y"),
            value.strftime("%d/%m/%Y"),
            value.strftime("%m/%d/%Y"),
            value.strftime("%d-%m-%Y"),
            value.strftime("%Y/%m/%d"),
        ]
    return [str(value)]


def _locate(value: Any, source: str, haystack: str) -> tuple[str, int, int] | None:
    """The first candidate is the value as stored; the rest are other ways the same fact may be
    written, so finding one of those is a normalized match rather than a quotation."""
    for index, candidate in enumerate(_candidates(value)):
        if not candidate:
            continue
        status = VERBATIM if index == 0 else NORMALIZED

        offset = source.find(candidate)
        if offset >= 0:
            return status, offset, len(candidate)
        offset = haystack.find(candidate.casefold())
        if offset >= 0:
            return NORMALIZED, offset, len(candidate)
        # last resort: tolerate runs of whitespace, e.g. a phone number split across a line break
        pattern = r"\s+".join(re.escape(part) for part in candidate.split())
        match = re.search(pattern, source, re.IGNORECASE)
        if match:
            return NORMALIZED, match.start(), match.end() - match.start()
    return None


def _excerpt(source: str, offset: int, length: int) -> str:
    start = max(0, offset - EXCERPT_PADDING)
    end = min(len(source), offset + length + EXCERPT_PADDING)
    return " ".join(source[start:end].split())


def _page_spans(source: str) -> list[tuple[int, int]]:
    """(offset, page number) for each page marker, in order."""
    return [(m.start(), int(m.group(1))) for m in PAGE_MARKER.finditer(source)]


def _page_of(offset: int, pages: list[tuple[int, int]]) -> int | None:
    page = None
    for start, number in pages:
        if start <= offset:
            page = number
        else:
            break
    return page
