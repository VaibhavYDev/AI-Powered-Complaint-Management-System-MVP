from app.evidence import DERIVED, NORMALIZED, UNSUPPORTED, VERBATIM, summarize, verify
from app.schemas import ComplaintData

SOURCE = """[page 1]
Customer Complaint - Email Correspondence
From: Rahul Sharma <rahul.sharma@greenleafpharmacy.example.com>
Date: 16 September 2026

Several Paracetamol 500 mg tablets from batch PCM24031 were chipped inside the blister pack.
The patient is 62 years old. Sample retained.

[page 2]
Phone: +91 98200
   11223
Signed, GreenLeaf Pharmacy"""


def extracted(**overrides) -> ComplaintData:
    data = {
        "complainant": {"name": "Rahul Sharma", "email": "rahul.sharma@greenleafpharmacy.example.com"},
        "product": {"product_name": "Paracetamol 500 mg", "batch_number": "PCM24031"},
        "complaint": {"complaint_received_date": "2026-09-16", "sample_available": True},
        "patient": {"patient_age": 62},
    }
    for section, fields in overrides.items():
        data.setdefault(section, {}).update(fields)
    return ComplaintData.model_validate(data)


def test_quoted_values_are_located_with_page_and_excerpt():
    evidence = verify(extracted(), SOURCE)

    batch = evidence["product.batch_number"]
    assert batch["status"] == VERBATIM and batch["page"] == 1
    assert "PCM24031" in batch["excerpt"]
    assert SOURCE[batch["offset"]:].startswith("PCM24031")


def test_a_date_written_differently_still_counts_as_quoted():
    evidence = verify(extracted(), SOURCE)
    received = evidence["complaint.complaint_received_date"]
    assert received["status"] == NORMALIZED  # "16 September 2026" vs 2026-09-16
    assert "September 2026" in received["excerpt"]


def test_a_value_split_across_lines_is_still_found():
    evidence = verify(extracted(complainant={"phone": "+91 98200 11223"}), SOURCE)
    phone = evidence["complainant.phone"]
    assert phone["status"] == NORMALIZED and phone["page"] == 2


def test_invented_identifiers_are_marked_unsupported():
    evidence = verify(extracted(product={"batch_number": "PCM99999"}, complainant={"name": "Someone Else"}), SOURCE)
    assert evidence["product.batch_number"]["status"] == UNSUPPORTED
    assert evidence["product.batch_number"]["excerpt"] is None
    assert evidence["complainant.name"]["status"] == UNSUPPORTED


def test_judgements_are_labelled_rather_than_called_unsupported():
    evidence = verify(
        extracted(complaint={"defect_category": "physical_defect", "defect_description": "tablets broken in the blister"}),
        SOURCE,
    )
    assert evidence["complaint.sample_available"]["status"] == DERIVED  # a yes/no, never quoted
    assert evidence["complaint.defect_category"]["status"] == DERIVED  # an enum the model chose
    assert evidence["complaint.defect_description"]["status"] == DERIVED  # paraphrase


def test_fields_left_null_produce_no_evidence():
    evidence = verify(extracted(), SOURCE)
    assert "product.lot_number" not in evidence
    assert "patient.death_reported" not in evidence


def test_summary_separates_quoted_judged_and_invented():
    data = extracted(product={"manufacturer": "Nonexistent Pharma Ltd"})
    summary = summarize(data, verify(data, SOURCE))

    assert summary["unsupported"] == ["product.manufacturer"]
    assert "complaint.sample_available" in summary["derived"]
    assert "product.lot_number" in summary["missing"]
    assert summary["quoted"] >= 4


def test_page_is_absent_when_the_source_has_no_markers():
    plain = "Batch PCM24031 was chipped."
    evidence = verify(ComplaintData.model_validate({"product": {"batch_number": "PCM24031"}}), plain)
    assert evidence["product.batch_number"]["status"] == VERBATIM
    assert evidence["product.batch_number"]["page"] is None
