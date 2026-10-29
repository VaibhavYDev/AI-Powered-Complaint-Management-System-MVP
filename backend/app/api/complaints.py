from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud, evidence
from ..ai.graph import run_copilot
from ..auth import current_user, limit_ai
from ..db import get_db
from ..documents import extract_pdf, read_upload
from ..models import ComplaintRecord, User
from ..schemas import (
    ChatRequest,
    Complaint,
    ComplaintEventOut,
    CopilotResponse,
    Intent,
    ReviewRequest,
    ReviewStatus,
)

router = APIRouter(prefix="/api", tags=["complaints"])


@router.post("/chat", response_model=CopilotResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), user: User = Depends(limit_ai)):
    record = _load(db, req.complaint_id, user) if req.complaint_id is not None else None
    result = run_copilot(req.message, source="chat", existing=crud.sections(record) if record else None)
    return _persist(db, result, record, source="chat", user=user, source_text=req.message)


@router.post("/upload", response_model=CopilotResponse)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(limit_ai)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF files are supported.")
    document = extract_pdf(read_upload(file.file))
    result = run_copilot(document.text, source="document")
    return _persist(db, result, None, source="document", user=user, source_text=document.text)


@router.get("/complaints", response_model=list[Complaint])
def list_complaints(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return crud.list_recent(db, owner_id=user.id)


@router.get("/complaints/{complaint_id}", response_model=Complaint)
def get_complaint(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _load(db, complaint_id, user)


@router.post("/complaints/{complaint_id}/approve", response_model=Complaint)
def approve(
    complaint_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    record = _load(db, complaint_id, user)
    _require_revision(record, body.revision)
    if record.status == ReviewStatus.approved:
        raise HTTPException(409, "This complaint is already approved.")
    return crud.review(db, record, ReviewStatus.approved.value, actor_id=user.id, note=body.note)


@router.post("/complaints/{complaint_id}/reject", response_model=Complaint)
def reject(
    complaint_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    record = _load(db, complaint_id, user)
    _require_revision(record, body.revision)
    return crud.review(db, record, ReviewStatus.rejected.value, actor_id=user.id, note=body.note)


@router.get("/complaints/{complaint_id}/history", response_model=list[ComplaintEventOut])
def history(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _load(db, complaint_id, user)
    return crud.events(db, complaint_id)


@router.get("/complaints/{complaint_id}/export", response_model=Complaint)
def export(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """A mock export. Only an approved record leaves the system."""
    record = _load(db, complaint_id, user)
    if record.status != ReviewStatus.approved:
        raise HTTPException(409, "Only an approved complaint can be exported.")
    return record


def _load(db: Session, complaint_id: int, user: User) -> ComplaintRecord:
    # Someone else's record is reported as missing rather than forbidden, so ids cannot be probed.
    record = crud.get(db, complaint_id, owner_id=user.id)
    if record is None:
        raise HTTPException(404, f"Complaint {complaint_id} does not exist.")
    return record


def _require_revision(record: ComplaintRecord, revision: int) -> None:
    if record.revision != revision:
        raise HTTPException(
            409, f"This complaint has changed since you looked at it (revision {record.revision})."
        )


def _persist(
    db: Session,
    result: dict,
    record: ComplaintRecord | None,
    source: str,
    user: User,
    source_text: str | None = None,
) -> CopilotResponse:
    """Graph output -> database. This is the only place AI results are written."""
    intent: Intent = result["intent"]
    risk = result.get("risk")

    if intent == Intent.EDIT:
        record = crud.update(db, record, result["patch"], risk, actor_id=user.id)
    else:
        draft = result["draft"]
        record = crud.create(
            db,
            draft,
            risk,
            source,
            owner_id=user.id,
            source_text=source_text,
            evidence=evidence.verify(draft, source_text or ""),
        )

    complaint = Complaint.model_validate(record)
    return CopilotResponse(
        intent=intent,
        message=result["reply"],
        complaint_id=record.id,
        complaint=complaint,
        patch=result.get("patch"),
        risk_assessment=risk,
        review=evidence.summarize(complaint, record.evidence or {}),
    )
