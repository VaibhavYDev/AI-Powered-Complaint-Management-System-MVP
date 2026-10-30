"""Care Documentation Reliability Lab endpoints.

Same ownership, CSRF and review rules as the complaint side: a record belongs to one workspace,
is a suggestion until approved, and only an approved record can be exported.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update as sql_update
from sqlalchemy.orm import Session

from ..auth import current_user, limit_ai
from ..care.extract import extract, plan_from
from ..care.schemas import Alert, CareNote, CarePlanEntry, alert_key
from ..db import get_db
from ..models import CareEvent, CareRecord, User

router = APIRouter(prefix="/api/care", tags=["care"])

MAX_NOTE_CHARS = 20_000


class ExtractRequest(BaseModel):
    note: str = Field(min_length=1, max_length=MAX_NOTE_CHARS)
    care_plan: list[CarePlanEntry] = []


class ReviewRequest(BaseModel):
    revision: int
    note: str | None = Field(None, max_length=500)
    acknowledged: list[str] = []


class CareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    revision: int
    source_text: str | None
    care_plan: list[CarePlanEntry] | None
    note: CareNote
    evidence: dict[str, dict] = {}
    alerts: list[Alert] = []
    acknowledged: list[str] = []
    reviewed_at: datetime | None
    created_at: datetime


class CareEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    revision: int
    note: str | None = None
    created_at: datetime
    actor_id: int | None = None


@router.post("", response_model=CareOut)
def analyse_note(body: ExtractRequest, db: Session = Depends(get_db), user: User = Depends(limit_ai)):
    result = extract(body.note, body.care_plan)
    record = CareRecord(
        owner_id=user.id,
        source_text=body.note,
        care_plan=[entry.model_dump() for entry in body.care_plan],
        note=result.note.model_dump(mode="json"),
        evidence=result.evidence,
        alerts=[alert.model_dump() for alert in result.alerts],
        acknowledged=[],
    )
    db.add(record)
    db.flush()
    db.add(CareEvent(care_id=record.id, actor_id=user.id, action="extracted", revision=record.revision))
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[CareOut])
def list_records(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return list(
        db.scalars(
            select(CareRecord).where(CareRecord.owner_id == user.id).order_by(CareRecord.id.desc()).limit(20)
        )
    )


@router.get("/{record_id}", response_model=CareOut)
def get_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _load(db, record_id, user)


@router.post("/{record_id}/approve", response_model=CareOut)
def approve(
    record_id: int, body: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    record = _load(db, record_id, user)
    _require_revision(record, body.revision)

    outstanding = _high_priority(record)
    unacknowledged = sorted(outstanding - set(body.acknowledged))
    if unacknowledged:
        raise HTTPException(
            422,
            "These alerts must be acknowledged before approval: " + ", ".join(unacknowledged),
        )
    return _decide(db, record, "approved", user, body, acknowledged=sorted(outstanding))


@router.post("/{record_id}/reject", response_model=CareOut)
def reject(
    record_id: int, body: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    record = _load(db, record_id, user)
    _require_revision(record, body.revision)
    return _decide(db, record, "rejected", user, body, acknowledged=record.acknowledged or [])


@router.get("/{record_id}/history", response_model=list[CareEventOut])
def history(record_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _load(db, record_id, user)
    return list(db.scalars(select(CareEvent).where(CareEvent.care_id == record_id).order_by(CareEvent.id)))


@router.get("/{record_id}/export", response_model=CareOut)
def export(record_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """A mock export of synthetic documentation. Only an approved record leaves the lab."""
    record = _load(db, record_id, user)
    if record.status != "approved":
        raise HTTPException(409, "Only an approved record can be exported.")
    return record


def _high_priority(record: CareRecord) -> set[str]:
    """Alerts a reviewer has to answer for: a wrong resident or an invented finding."""
    return {
        alert_key(alert["kind"], alert.get("observation_index"))
        for alert in (record.alerts or [])
        if alert.get("severity") == "high"
    }


def _load(db: Session, record_id: int, user: User) -> CareRecord:
    record = db.scalars(
        select(CareRecord).where(CareRecord.id == record_id, CareRecord.owner_id == user.id)
    ).one_or_none()
    if record is None:
        raise HTTPException(404, f"Care record {record_id} does not exist.")
    return record


def _require_revision(record: CareRecord, revision: int) -> None:
    if record.revision != revision:
        raise HTTPException(409, f"This record has changed since you looked at it (revision {record.revision}).")


def _decide(
    db: Session, record: CareRecord, status: str, user: User, body: ReviewRequest, acknowledged: list[str]
) -> CareRecord:
    """One conditional update, so two reviewers cannot both record a decision."""
    result = db.execute(
        sql_update(CareRecord)
        .where(
            CareRecord.id == record.id,
            CareRecord.owner_id == user.id,
            CareRecord.revision == body.revision,
            CareRecord.status == "needs_review",
        )
        .values(
            status=status,
            acknowledged=acknowledged,
            reviewed_at=datetime.now(timezone.utc),
            reviewed_by=user.id,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(409, "This record changed while you were reviewing it.")
    db.add(
        CareEvent(care_id=record.id, actor_id=user.id, action=status, revision=body.revision, note=body.note)
    )
    db.commit()
    return _load(db, record.id, user)
