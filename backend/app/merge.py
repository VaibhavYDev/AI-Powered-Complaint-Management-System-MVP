"""Partial-update logic for EDIT. The LLM only proposes changes; this module decides
how they are applied so unrelated data can never be erased."""

from .schemas import EditProposal


def patch_from(proposal: EditProposal) -> dict:
    """{section: {field: value}} containing only fields the model explicitly set.
    Nulls inside `changes` are dropped; a field becomes null only via `clear`."""
    raw = proposal.changes.model_dump(exclude_unset=True, mode="json")
    patch = {section: {k: v for k, v in fields.items() if v is not None} for section, fields in raw.items()}
    for path in proposal.clear:
        section, field = path.split(".")
        patch.setdefault(section, {})[field] = None
    return {section: fields for section, fields in patch.items() if fields}


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
            if new is None:
                parts.append(f"cleared {label}")
            elif old in (None, ""):
                parts.append(f"{label} set to {new}")
            else:
                parts.append(f"{label}: {old} → {new}")
    return "Updated " + "; ".join(parts) + "." if parts else "No fields were changed."
