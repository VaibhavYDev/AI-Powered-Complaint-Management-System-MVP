"""Partial-update logic for EDIT. The LLM only proposes a patch; this module decides
how it is applied so unrelated data can never be erased."""

from .schemas import ComplaintPatch


def patch_from(draft: ComplaintPatch) -> dict:
    """Fields the model explicitly set, minus nulls. Clearing a field via chat is
    deliberately unsupported: a stray null from the model must not wipe real data."""
    raw = draft.model_dump(exclude_unset=True, mode="json")
    return {
        section: {k: v for k, v in fields.items() if v is not None}
        for section, fields in raw.items()
        if any(v is not None for v in fields.values())
    }


def apply_patch(existing: dict, patch: dict) -> dict:
    return {
        section: {**existing.get(section, {}), **patch.get(section, {})}
        for section in existing.keys() | patch.keys()
    }


def describe_changes(existing: dict, patch: dict) -> str:
    parts = []
    for section, fields in patch.items():
        for key, new in fields.items():
            old = existing.get(section, {}).get(key)
            label = key.replace("_", " ")
            parts.append(f"{label}: {old} → {new}" if old not in (None, "") else f"{label} set to {new}")
    return "Updated " + "; ".join(parts) + "." if parts else "No fields were changed."
