from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.models import Feedback
from app.db.session import get_db

router = APIRouter(prefix="/feedbacks", tags=["Feedbacks"])


class FeedbackCreate(BaseModel):
    name: str
    message: str

    @field_validator("name")
    @classmethod
    def _name_len(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome não pode ser vazio")
        if len(v) > 100:
            raise ValueError("Nome deve ter no máximo 100 caracteres")
        return v

    @field_validator("message")
    @classmethod
    def _message_len(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Mensagem não pode ser vazia")
        if len(v) > 500:
            raise ValueError("Mensagem deve ter no máximo 500 caracteres")
        return v


@router.post("/", status_code=201)
def create_feedback(data: FeedbackCreate, db: Session = Depends(get_db)):
    fb = Feedback(name=data.name, message=data.message)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"id": fb.id, "name": fb.name, "created_at": fb.created_at}


@router.get("/")
def list_feedbacks(db: Session = Depends(get_db), _: object = Depends(require_admin)):
    feedbacks = (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc())
        .all()
    )
    return [
        {"id": f.id, "name": f.name, "message": f.message, "created_at": f.created_at}
        for f in feedbacks
    ]


@router.delete("/{feedback_id}", status_code=204)
def delete_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback não encontrado")
    db.delete(fb)
    db.commit()
