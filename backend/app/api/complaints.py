from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud
from ..auth import current_user, limit_ai
from ..models import User
from ..ai.graph import run_copilot
from ..db import get_db
from ..documents import extract_pdf, read_upload
from ..models import ComplaintRecord
from ..schemas import ChatRequest, Complaint, CopilotResponse, Intent

router = APIRouter(prefix="/api", tags=["complaints"])


@router.post("/chat", response_model=CopilotResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), user: User = Depends(limit_ai)):
    record = _load(db, req.complaint_id, user) if req.complaint_id is not None else None
    result = run_copilot(req.message, source="chat", existing=crud.sections(record) if record else None)
    return _persist(db, result, record, source="chat", user=user)


@router.post("/upload", response_model=CopilotResponse)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(limit_ai)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF files are supported.")
    document = extract_pdf(read_upload(file.file))
    result = run_copilot(document.text, source="document")
    return _persist(db, result, None, source="document", user=user)


@router.get("/complaints", response_model=list[Complaint])
def list_complaints(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return crud.list_recent(db, owner_id=user.id)


@router.get("/complaints/{complaint_id}", response_model=Complaint)
def get_complaint(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _load(db, complaint_id, user)


def _load(db: Session, complaint_id: int, user: User) -> ComplaintRecord:
    # Someone else's record is reported as missing rather than forbidden, so ids cannot be probed.
    record = crud.get(db, complaint_id, owner_id=user.id)
    if record is None:
        raise HTTPException(404, f"Complaint {complaint_id} does not exist.")
    return record


def _persist(db: Session, result: dict, record: ComplaintRecord | None, source: str, user: User) -> CopilotResponse:
    """Graph output -> database. This is the only place AI results are written."""
    intent: Intent = result["intent"]
    risk = result.get("risk")

    if intent == Intent.EDIT:
        record = crud.update(db, record, result["patch"], risk)
    else:
        record = crud.create(db, result["draft"], risk, source, owner_id=user.id)

    return CopilotResponse(
        intent=intent,
        message=result["reply"],
        complaint_id=record.id,
        complaint=Complaint.model_validate(record),
        patch=result.get("patch"),
        risk_assessment=risk,
    )
