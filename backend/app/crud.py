"""Persistence. Every read and write is scoped to an owner in the query itself, so a record
belonging to another workspace cannot be reached even if its id is guessed."""

from sqlalchemy import select, update as sql_update
from sqlalchemy.orm import Session

from .merge import apply_patch
from datetime import datetime, timezone

from .models import ComplaintEvent, ComplaintRecord, User
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
    db: Session,
    data: ComplaintData,
    risk: RiskAssessment | None,
    source: str,
    owner_id: int,
    source_text: str | None = None,
    evidence: dict | None = None,
) -> ComplaintRecord:
    record = ComplaintRecord(
        owner_id=owner_id,
        source=source,
        **data.model_dump(mode="json"),
        risk_assessment=risk.model_dump(mode="json") if risk else None,
        source_text=source_text,
        evidence=evidence,
    )
    db.add(record)
    db.flush()
    db.add(ComplaintEvent(complaint_id=record.id, actor_id=owner_id, action="extracted", revision=record.revision))
    db.commit()
    db.refresh(record)
    return record


def update(
    db: Session, record: ComplaintRecord, patch: dict, risk: RiskAssessment | None, actor_id: int
) -> ComplaintRecord:
    merged = apply_patch(sections(record), patch)
    for section, values in merged.items():
        setattr(record, section, values)  # reassign so SQLAlchemy sees the JSON change
    if risk:
        record.risk_assessment = risk.model_dump(mode="json")

    changed = [f"{section}.{field}" for section, fields in patch.items() for field in fields]
    # The edited values came from the user's instruction, not from the original document.
    record.evidence = {**(record.evidence or {}), **{path: {"status": "user_supplied"} for path in changed}}
    # Changing the content undoes any approval: the record has to be looked at again.
    record.revision += 1
    record.status = "needs_review"
    record.reviewed_at = record.reviewed_by = None
    db.add(
        ComplaintEvent(
            complaint_id=record.id, actor_id=actor_id, action="edited", revision=record.revision, changed_fields=changed
        )
    )
    db.commit()
    db.refresh(record)
    return record


def review(
    db: Session,
    complaint_id: int,
    owner_id: int,
    expected_revision: int,
    status: str,
    actor_id: int,
    note: str | None = None,
) -> ComplaintRecord | None:
    """Apply a review decision only if the record is still at the revision the reviewer saw and
    still awaiting one.

    The check and the write are one statement, so two reviewers acting at the same time cannot
    both succeed: the second matches no row and is told the record moved on. Requiring the
    pending status as well means a decision cannot be overwritten by a second decision - the
    record has to be edited back into review first.
    """
    result = db.execute(
        sql_update(ComplaintRecord)
        .where(
            ComplaintRecord.id == complaint_id,
            ComplaintRecord.owner_id == owner_id,
            ComplaintRecord.revision == expected_revision,
            ComplaintRecord.status == "needs_review",
        )
        .values(status=status, reviewed_at=datetime.now(timezone.utc), reviewed_by=actor_id)
    )
    if result.rowcount == 0:
        db.rollback()
        return None
    db.add(
        ComplaintEvent(
            complaint_id=complaint_id, actor_id=actor_id, action=status, revision=expected_revision, note=note
        )
    )
    db.commit()
    return get(db, complaint_id, owner_id)


def events(db: Session, complaint_id: int) -> list[ComplaintEvent]:
    return list(
        db.scalars(
            select(ComplaintEvent)
            .where(ComplaintEvent.complaint_id == complaint_id)
            .order_by(ComplaintEvent.id)
        )
    )


def sections(record: ComplaintRecord) -> dict:
    return {name: getattr(record, name) for name in ComplaintData.model_fields}


def create_user(db: Session, email: str | None = None, password_hash: str | None = None) -> User:
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def claim_workspace(db: Session, user: User, email: str, password_hash: str) -> User:
    """Attach an account to the anonymous workspace already in use, so its complaints survive."""
    user.email, user.password_hash = email, password_hash
    db.commit()
    db.refresh(user)
    return user


def user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).one_or_none()
