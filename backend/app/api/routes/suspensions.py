"""
routes/suspensions.py
=====================
Criação e remoção manual de suspensões.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from pydantic import BaseModel

from app.api.deps import require_organizer
from app.db.models import Athlete, Championship, Suspension, User
from app.db.session import get_db

router = APIRouter(prefix="/suspensions", tags=["Suspensões"])


class SuspensionCreate(BaseModel):
    athlete_id: int
    championship_id: int
    games_remaining: int = 1
    reason: Optional[str] = None


class SuspensionOut(BaseModel):
    id: int
    athlete_id: int
    championship_id: int
    games_remaining: int
    reason: Optional[str] = None
    auto_generated: bool

    model_config = {"from_attributes": True}


@router.post("/", response_model=SuspensionOut, status_code=status.HTTP_201_CREATED)
def create_suspension(
    data: SuspensionCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    athlete = db.query(Athlete).filter(Athlete.id == data.athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Atleta não encontrado")

    champ = db.query(Championship).filter(Championship.id == data.championship_id).first()
    if not champ:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campeonato não encontrado")

    suspension = Suspension(
        athlete_id=data.athlete_id,
        championship_id=data.championship_id,
        games_remaining=data.games_remaining,
        reason=data.reason or "Suspensão manual",
        auto_generated=False,
    )
    db.add(suspension)
    db.commit()
    db.refresh(suspension)
    return suspension


@router.delete("/{suspension_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suspension(
    suspension_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    suspension = db.query(Suspension).filter(Suspension.id == suspension_id).first()
    if not suspension:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suspensão não encontrada")
    db.delete(suspension)
    db.commit()
