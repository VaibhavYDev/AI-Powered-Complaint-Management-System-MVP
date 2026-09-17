"""EDIT safety: what the model proposes vs. what is actually applied."""

import pytest
from pydantic import ValidationError

from app.merge import apply_patch, describe_changes, patch_from
from app.schemas import ComplaintData, EditProposal

EXISTING = ComplaintData.model_validate(
    {
        "complainant": {"name": "Rahul", "email": "old@example.com", "phone": "+91 98200 11223"},
        "product": {"product_name": "Paracetamol 500mg", "batch_number": "B123", "strength": "500 mg"},
        "complaint": {"defect_category": "physical_defect", "sample_available": True},
        "patient": {"hospitalization_required": False},
    }
).model_dump(mode="json")
OTHER = ("complainant", "complaint", "patient")


def proposal(changes=(), clear=()) -> dict:
    return patch_from(EditProposal.model_validate({"changes": [{"field": f, "value": v} for f, v in changes], "clear": list(clear)}))


def test_single_top_level_field():
    patch = proposal([("batch_number", "B999")])
    assert patch == {"product": {"batch_number": "B999"}}
    merged = apply_patch(EXISTING, patch)
    assert merged["product"] == {**EXISTING["product"], "batch_number": "B999"}
    assert {k: merged[k] for k in OTHER} == {k: EXISTING[k] for k in OTHER}


def test_single_nested_field():
    patch = proposal([("email", "rahul@example.com")])
    assert patch == {"complainant": {"email": "rahul@example.com"}}
    merged = apply_patch(EXISTING, patch)
    assert merged["complainant"] == {**EXISTING["complainant"], "email": "rahul@example.com"}
    assert merged["product"] == EXISTING["product"]


def test_multiple_fields_across_sections():
    patch = proposal([("batch_number", "B999"), ("strength", "650 mg"), ("sample_available", False)])
    assert patch == {"product": {"batch_number": "B999", "strength": "650 mg"}, "complaint": {"sample_available": False}}
    merged = apply_patch(EXISTING, patch)
    assert merged["product"]["product_name"] == "Paracetamol 500mg"
    assert merged["complaint"]["defect_category"] == "physical_defect"
    assert merged["complainant"] == EXISTING["complainant"]


def test_nulls_in_changes_never_erase_data():
    # A model emitting null values must not wipe anything.
    patch = proposal([("name", None), ("email", None), ("phone", "+91 1"), ("batch_number", None)])
    assert patch == {"complainant": {"phone": "+91 1"}}
    merged = apply_patch(EXISTING, patch)
    assert merged["complainant"]["name"] == "Rahul" and merged["complainant"]["email"] == "old@example.com"
    assert merged["product"] == EXISTING["product"]


def test_clear_only_when_explicitly_requested():
    patch = proposal(clear=["phone"])
    assert patch == {"complainant": {"phone": None}}
    merged = apply_patch(EXISTING, patch)
    assert merged["complainant"]["phone"] is None
    assert merged["complainant"]["email"] == "old@example.com"
    assert describe_changes(EXISTING, patch) == "Updated cleared phone."


def test_clear_accepts_dotted_path_and_ignores_unknown():
    assert proposal(clear=["complainant.phone", "not_a_field", "product.bogus"]) == {"complainant": {"phone": None}}


def test_values_are_normalised_by_the_canonical_schema():
    patch = proposal([("sample_available", "yes"), ("defect_category", "Packaging"), ("product.expiry_date", "2028-02-28")])
    assert patch == {"complaint": {"sample_available": True, "defect_category": "packaging"}, "product": {"expiry_date": "2028-02-28"}}


def test_invalid_values_are_rejected_at_validation():
    with pytest.raises(ValidationError):
        EditProposal.model_validate({"changes": [{"field": "expiry_date", "value": "next week"}], "clear": []})


def test_unknown_fields_are_dropped_not_trusted():
    assert proposal([("bogus", "x"), ("batch_number", "B999")]) == {"product": {"batch_number": "B999"}}


def test_empty_proposal_is_empty_patch():
    assert proposal() == {}
    assert patch_from(EditProposal.model_validate({})) == {}


def test_change_description():
    assert describe_changes(EXISTING, {"product": {"batch_number": "B999"}}) == "Updated batch number: B123 → B999."
    assert describe_changes(EXISTING, {"product": {"lot_number": "L1"}}) == "Updated lot number set to L1."
