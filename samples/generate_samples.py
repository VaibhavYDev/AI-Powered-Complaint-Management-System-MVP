"""Generate the fictional demo complaint PDFs in this folder.

    cd backend && .venv/Scripts/python ../samples/generate_samples.py

All names, companies, products and identifiers are invented for demonstration.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=styles["Normal"], fontSize=10.5, leading=15)
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=15, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=4)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=9, textColor=colors.grey)


def build(name: str, flow: list) -> None:
    doc = SimpleDocTemplate(str(HERE / name), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(flow)
    print("wrote", name)


def form_table(rows: list[tuple[str, str]]) -> Table:
    table = Table([[Paragraph(f"<b>{k}</b>", BODY), Paragraph(v, BODY)] for k, v in rows], colWidths=[55 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa4b2")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def complaint_01():
    # Email-style complaint from a pharmacy: minor physical defect, no patient harm.
    build("complaint_01_blister_defect.pdf", [
        Paragraph("Customer Complaint – Email Correspondence", H1),
        Paragraph("From: Rahul Sharma &lt;rahul.sharma@greenleafpharmacy.example.com&gt;<br/>"
                  "To: quality@zenithpharma.example.com<br/>"
                  "Date: 16 September 2026<br/>"
                  "Subject: Damaged tablets – Paracetamol 500 mg, Batch PCM24031", BODY),
        Spacer(1, 8),
        Paragraph("Dear Quality Team,", BODY), Spacer(1, 6),
        Paragraph("I am writing on behalf of GreenLeaf Pharmacy, Pune, India (phone +91 98200 11223) to report a quality issue with "
                  "Zenith Paracetamol Tablets 500 mg manufactured by Zenith Pharma Pvt. Ltd. The affected batch is PCM24031, "
                  "manufacturing date 02 March 2026, expiry date 28 February 2028.", BODY), Spacer(1, 6),
        Paragraph("On 15 September 2026 a customer returned a strip in which several tablets were chipped and broken inside the "
                  "sealed blister pockets. We inspected our remaining stock and found 3 more strips (approximately 12 tablets in "
                  "total) with the same problem. The blisters themselves were sealed and undamaged, so the breakage appears to have "
                  "occurred before packaging.", BODY), Spacer(1, 6),
        Paragraph("No patient consumed the broken tablets and no health effects have been reported. We have retained the affected "
                  "strips and can send them to you as a sample for investigation. We do not suspect the product to be counterfeit; "
                  "it was purchased through your authorised distributor.", BODY), Spacer(1, 6),
        Paragraph("Please confirm receipt of this complaint and let us know how you would like us to proceed with the returned stock.", BODY),
        Spacer(1, 10),
        Paragraph("Kind regards,<br/>Rahul Sharma<br/>Pharmacist-in-charge, GreenLeaf Pharmacy<br/>Pune, India", BODY),
    ])


def complaint_02():
    # Formal hospital complaint form with an adverse event: expected to triage as Class I/II.
    build("complaint_02_adverse_event.pdf", [
        Paragraph("PRODUCT QUALITY COMPLAINT REPORT FORM", H1),
        Paragraph("Submitted to: Zenith Pharma Pvt. Ltd. – Quality Assurance | Form ref: MCH-QC-2026-118", SMALL),
        Paragraph("1. Complainant details", H2),
        form_table([
            ("Name", "Dr. Priya Menon"),
            ("Organisation", "MedCare Hospital Pharmacy"),
            ("Country", "India"),
            ("Email", "priya.menon@medcarehospital.example.com"),
            ("Phone", "+91 44 2811 9080"),
            ("Received via", "Web form (manufacturer complaint portal)"),
            ("Date complaint submitted", "2026-09-14"),
        ]),
        Paragraph("2. Product details", H2),
        form_table([
            ("Product name", "Amoxiclav-DS Tablets"),
            ("Active ingredient(s)", "Amoxicillin / Clavulanic acid"),
            ("Strength", "875 mg / 125 mg"),
            ("Dosage form", "Film-coated tablet"),
            ("Manufacturer", "Zenith Pharma Pvt. Ltd."),
            ("Batch number", "AMC25017"),
            ("Lot number", "L-0932"),
            ("Manufacturing date", "2025-11-20"),
            ("Expiry date", "2027-10-31"),
        ]),
        Paragraph("3. Description of the complaint", H2),
        form_table([
            ("Date of occurrence", "2026-09-12"),
            ("Quantity affected", "1 carton (10 x 10 tablets)"),
            ("Description", "Tablets in this batch have a strong unusual odour and several show brownish discolouration on the "
                            "film coat. One inpatient (female, 62 years) developed a rash and vomiting approximately two hours after "
                            "the first dose from this carton. The patient required medical attention and was admitted for observation "
                            "for 24 hours; she has since recovered. No death occurred. Treatment was switched to an alternative supplier."),
            ("Sample available", "Yes – the remaining 92 tablets from the carton are quarantined and available on request."),
            ("Counterfeit suspected", "No – product received from the hospital's contracted distributor with intact seals."),
        ]),
        Paragraph("4. Declaration", H2),
        Paragraph("I confirm the above information is accurate to the best of my knowledge. Signed: Dr. Priya Menon, "
                  "Chief Pharmacist, 14 September 2026.", BODY),
    ])


def complaint_03():
    # API (active pharmaceutical ingredient) complaint from a B2B formulation customer.
    build("complaint_03_api_foreign_particles.pdf", [
        Paragraph("Supplier Quality Notification – API Complaint", H1),
        Paragraph("Issued by: Nova Formulations Ltd., Incoming Quality Control, Birmingham, United Kingdom", SMALL),
        Spacer(1, 6),
        form_table([
            ("Notification date", "2026-09-10"),
            ("Contact", "Mark Ellison, QC Manager – mark.ellison@novaformulations.example.com, +44 121 496 0342"),
            ("Supplier", "Zenith Pharma Pvt. Ltd. (API division)"),
            ("Material", "Metformin Hydrochloride API (USP)"),
            ("Batch number", "MET-API-2026-044"),
            ("Manufacturing date", "2026-06-05"),
            ("Retest / expiry date", "2028-06-04"),
            ("Quantity affected", "2 drums of 25 kg (50 kg)"),
        ]),
        Paragraph("Observation", H2),
        Paragraph("During incoming inspection on 9 September 2026, dark foreign particles were observed in two of the six drums received "
                  "against purchase order NF-77812. Particles were visible to the naked eye on the surface of the white crystalline powder "
                  "and were also retained on a 500 µm sieve. The remaining four drums appeared normal. Identity and assay of the affected "
                  "drums were within specification; the complaint relates to visible particulate contamination only.", BODY),
        Paragraph("Impact", H2),
        Paragraph("The affected drums have been placed on hold and have not been used in manufacturing. No finished product was produced "
                  "from this material, and no patient exposure has occurred. Retained samples of the particles and of the powder from both "
                  "drums are available and can be shipped to the supplier for investigation. We request a root-cause investigation, a "
                  "statement on the other batches manufactured on the same line, and replacement material.", BODY),
        Spacer(1, 10),
        Paragraph("Mark Ellison – QC Manager, Nova Formulations Ltd.", BODY),
    ])


if __name__ == "__main__":
    complaint_01()
    complaint_02()
    complaint_03()
