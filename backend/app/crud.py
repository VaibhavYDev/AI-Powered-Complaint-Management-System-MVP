"""Persistence. Every read and write is scoped to an owner in the query itself, so a record
belonging to another workspace cannot be reached even if its id is guessed."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .merge import apply_patch
from .models import ComplaintRecord, User
from .schemas import ComplaintData, RiskAssessment


def get(db: Session, complaint_id: int, owner_id: int) -> ComplaintRecord | None:
    return db.scalars(
        select(ComplaintRecord).where(
            ComplaintRecord.id == complaint_id, ComplaintRecord.owner_id == owner_id
        )
    ).one_or_none()


def list_recent(db: Session, owner_id: int, limit: int = 20) -> list[ComplaintRecord]:
    return list(
        db.scalars(
            select(ComplaintRecord)
            .where(ComplaintRecord.owner_id == owner_id)
            .order_by(ComplaintRecord.id.desc())
            .limit(limit)
        )
    )


def create(
    db: Session, data: ComplaintData, risk: RiskAssessment | None, source: str, owner_id: int
) -> ComplaintRecord:
    record = ComplaintRecord(
        owner_id=owner_id,
        source=source,
        **data.model_dump(mode="json"),
        risk_assessment=risk.model_dump(mode="json") if risk else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update(
    db: Session, record: ComplaintRecord, patch: dict, risk: RiskAssessment | None
) -> ComplaintRecord:
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


def create_user(db: Session, email: str | None = None, password_hash: str | None = None) -> User:
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).one_or_none()
