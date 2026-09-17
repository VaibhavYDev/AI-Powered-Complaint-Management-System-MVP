from sqlalchemy.orm import Session

from .merge import apply_patch
from .models import ComplaintRecord
from .schemas import ComplaintData, RiskAssessment


def get(db: Session, complaint_id: int) -> ComplaintRecord | None:
    return db.get(ComplaintRecord, complaint_id)


def list_recent(db: Session, limit: int = 20) -> list[ComplaintRecord]:
    return db.query(ComplaintRecord).order_by(ComplaintRecord.id.desc()).limit(limit).all()


def create(db: Session, data: ComplaintData, risk: RiskAssessment | None, source: str) -> ComplaintRecord:
    record = ComplaintRecord(
        source=source,
        **data.model_dump(mode="json"),
        risk_assessment=risk.model_dump(mode="json") if risk else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update(db: Session, record: ComplaintRecord, patch: dict, risk: RiskAssessment | None) -> ComplaintRecord:
    merged = apply_patch(sections(record), patch)
    for section, values in merged.items():
        setattr(record, section, values)  # reassign so SQLAlchemy sees the JSON change
    if risk:
        record.risk_assessment = risk.model_dump(mode="json")
    db.commit()
    db.refresh(record)
    return record


def sections(record: ComplaintRecord) -> dict:
    return {name: getattr(record, name) for name in ComplaintData.model_fields}
