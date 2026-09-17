from app.merge import apply_patch, describe_changes, patch_from
from app.schemas import ComplaintData, ComplaintPatch

EXISTING = ComplaintData.model_validate(
    {
        "product": {"product_name": "Paracetamol 500mg", "batch_number": "B123"},
        "complainant": {"name": "Rahul", "email": "old@example.com"},
    }
).model_dump(mode="json")


def test_patch_contains_only_returned_fields():
    patch = patch_from(ComplaintPatch.model_validate({"product": {"batch_number": "B999"}}))
    assert patch == {"product": {"batch_number": "B999"}}


def test_flat_keys_are_lifted_into_sections():
    patch = patch_from(ComplaintPatch.model_validate({"batch_number": "B999", "email": "new@example.com"}))
    assert patch == {"product": {"batch_number": "B999"}, "complainant": {"email": "new@example.com"}}


def test_nulls_and_unknown_keys_are_ignored():
    patch = patch_from(ComplaintPatch.model_validate({"product": {"batch_number": None}, "bogus": "x"}))
    assert patch == {}


def test_merge_preserves_unrelated_data():
    merged = apply_patch(EXISTING, {"product": {"batch_number": "B999"}})
    assert merged["product"]["batch_number"] == "B999"
    assert merged["product"]["product_name"] == "Paracetamol 500mg"
    assert merged["complainant"] == EXISTING["complainant"]


def test_nested_update():
    merged = apply_patch(EXISTING, {"complainant": {"email": "rahul@example.com"}})
    assert merged["complainant"] == {**EXISTING["complainant"], "email": "rahul@example.com"}
    assert merged["product"] == EXISTING["product"]


def test_change_description():
    assert describe_changes(EXISTING, {"product": {"batch_number": "B999"}}) == "Updated batch number: B123 → B999."
