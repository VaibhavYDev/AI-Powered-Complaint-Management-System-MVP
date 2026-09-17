"""EDIT safety: what the model proposes vs. what is actually applied."""

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


def proposal(raw: dict) -> dict:
    return patch_from(EditProposal.model_validate(raw))


def test_single_top_level_field():
    patch = proposal({"changes": {"product": {"batch_number": "B999"}}, "clear": []})
    assert patch == {"product": {"batch_number": "B999"}}
    merged = apply_patch(EXISTING, patch)
    assert merged["product"] == {**EXISTING["product"], "batch_number": "B999"}
    assert {k: merged[k] for k in ("complainant", "complaint", "patient")} == {k: EXISTING[k] for k in ("complainant", "complaint", "patient")}


def test_single_nested_field():
    patch = proposal({"changes": {"complainant": {"email": "rahul@example.com"}}})
    assert patch == {"complainant": {"email": "rahul@example.com"}}
    merged = apply_patch(EXISTING, patch)
    assert merged["complainant"] == {**EXISTING["complainant"], "email": "rahul@example.com"}
    assert merged["product"] == EXISTING["product"]


def test_multiple_fields_across_sections():
    patch = proposal({"changes": {"product": {"batch_number": "B999", "strength": "650 mg"}, "complaint": {"sample_available": False}}})
    assert patch == {"product": {"batch_number": "B999", "strength": "650 mg"}, "complaint": {"sample_available": False}}
    merged = apply_patch(EXISTING, patch)
    assert merged["product"]["product_name"] == "Paracetamol 500mg"
    assert merged["complaint"]["defect_category"] == "physical_defect"
    assert merged["complainant"] == EXISTING["complainant"]


def test_nulls_in_changes_never_erase_data():
    # A sloppy model echoing the template with nulls must not wipe anything.
    patch = proposal({"changes": {"complainant": {"name": None, "email": None, "phone": "+91 1"}, "product": {"batch_number": None}}})
    assert patch == {"complainant": {"phone": "+91 1"}}
    merged = apply_patch(EXISTING, patch)
    assert merged["complainant"]["name"] == "Rahul" and merged["complainant"]["email"] == "old@example.com"
    assert merged["product"] == EXISTING["product"]


def test_clear_only_when_explicitly_requested():
    patch = proposal({"changes": {}, "clear": ["complainant.phone"]})
    assert patch == {"complainant": {"phone": None}}
    merged = apply_patch(EXISTING, patch)
    assert merged["complainant"]["phone"] is None
    assert merged["complainant"]["email"] == "old@example.com"
    assert describe_changes(EXISTING, patch) == "Updated cleared phone."


def test_clear_accepts_bare_field_and_ignores_unknown():
    assert proposal({"clear": ["phone", "not_a_field", "product.bogus"]}) == {"complainant": {"phone": None}}


def test_flat_keys_and_unknown_keys():
    # Flat answers are lifted into their section; unknown keys are dropped rather than trusted.
    assert proposal({"batch_number": "B999", "email": "new@example.com", "bogus": "x"}) == {
        "product": {"batch_number": "B999"},
        "complainant": {"email": "new@example.com"},
    }


def test_empty_proposal_is_empty_patch():
    assert proposal({}) == {}
    assert proposal({"changes": {}, "clear": []}) == {}


def test_change_description():
    assert describe_changes(EXISTING, {"product": {"batch_number": "B999"}}) == "Updated batch number: B123 → B999."
    assert describe_changes(EXISTING, {"product": {"lot_number": "L1"}}) == "Updated lot number set to L1."
