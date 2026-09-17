"""Partial-update logic for EDIT. The LLM only proposes changes; this module decides
how they are applied so unrelated data can never be erased."""

from .schemas import ComplaintData, EditProposal


def patch_from(proposal: EditProposal) -> dict:
    """{section: {field: value}} with values normalised by the canonical section models
    (enum/boolean/date coercion). Only proposed fields are present; cleared ones are null."""
    normalised = ComplaintData.model_validate(proposal.patch()).model_dump(exclude_unset=True, mode="json")
    return {section: fields for section, fields in normalised.items() if fields}


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
