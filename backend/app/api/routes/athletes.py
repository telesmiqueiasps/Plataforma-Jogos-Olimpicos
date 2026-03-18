"""
routes/athletes.py
==================
CRUD de atletas independente de equipe.
team_id e opcional — atleta pode existir sem equipe (status "livre").
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_organizer
from app.db.models import Athlete, Team, User
from app.db.session import get_db
from app.schemas.athlete import AthleteCreate, AthleteOut, AthleteUpdate

router = APIRouter(prefix="/athletes", tags=["Atletas"])


def _get_or_404(athlete_id: int, db: Session) -> Athlete:
    a = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Atleta nao encontrado")
    return a


@router.get("/", response_model=list[AthleteOut])
def list_athletes(
    team_id: Optional[int] = Query(None, description="Filtra por equipe"),
    active: Optional[bool] = Query(None, description="Filtra por status ativo"),
    free: Optional[bool] = Query(None, description="Se true, retorna apenas atletas sem equipe"),
    db: Session = Depends(get_db),
):
    q = db.query(Athlete)
    if team_id is not None:
        q = q.filter(Athlete.team_id == team_id)
    if active is not None:
        q = q.filter(Athlete.active == active)
    if free is True:
        q = q.filter(Athlete.team_id.is_(None))
    return q.order_by(Athlete.name).all()


@router.post("/", response_model=AthleteOut, status_code=status.HTTP_201_CREATED)
def create_athlete(
    data: AthleteCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_organizer),
):
    if data.team_id is not None:
        team = db.query(Team).filter(Team.id == data.team_id).first()
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipe nao encontrada")
    athlete = Athlete(**data.model_dump())
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return athlete


@router.get("/{athlete_id}", response_model=AthleteOut)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    return _get_or_404(athlete_id, db)


@router.put("/{athlete_id}", response_model=AthleteOut)
def update_athlete(
    athlete_id: int,
    data: AthleteUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_organizer),
):
    athlete = _get_or_404(athlete_id, db)
    update_data = data.model_dump(exclude_unset=True)
    if "team_id" in update_data and update_data["team_id"] is not None:
        team = db.query(Team).filter(Team.id == update_data["team_id"]).first()
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipe nao encontrada")
    for field, value in update_data.items():
        setattr(athlete, field, value)
    db.commit()
    db.refresh(athlete)
    return athlete


@router.delete("/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_athlete(
    athlete_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_organizer),
):
    athlete = _get_or_404(athlete_id, db)
    db.delete(athlete)
    db.commit()
