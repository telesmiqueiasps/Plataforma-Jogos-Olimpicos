"""
routes/teams.py
===============
CRUD de equipes e atletas.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from sqlalchemy import update as sa_update

from app.db.models import Athlete, Sport, Team, User
from app.db.session import get_db
from app.schemas.athlete import AthleteCreate, AthleteOut, AthleteUpdate
from app.schemas.team import TeamCreate, TeamDetail, TeamOut, TeamUpdate

router = APIRouter(prefix="/teams", tags=["Equipes"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_team_or_404(team_id: int, db: Session) -> Team:
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipe não encontrada")
    return team


def _get_athlete_or_404(team_id: int, athlete_id: int, db: Session) -> Athlete:
    athlete = (
        db.query(Athlete)
        .filter(Athlete.id == athlete_id, Athlete.team_id == team_id)
        .first()
    )
    if not athlete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Atleta não encontrado")
    return athlete


# ---------------------------------------------------------------------------
# Equipes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[TeamOut])
def list_teams(
    sport_id: Optional[int] = Query(None, description="Filtra por modalidade"),
    db: Session = Depends(get_db),
):
    q = db.query(Team)
    if sport_id is not None:
        q = q.filter(Team.sport_id == sport_id)
    return q.order_by(Team.name).all()


@router.post("/", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(
    data: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    sport = db.query(Sport).filter(Sport.id == data.sport_id).first()
    if not sport:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modalidade não encontrada")

    athlete_ids = data.athlete_ids or []
    team = Team(**data.model_dump(exclude={"athlete_ids"}), created_by=current_user.id)
    db.add(team)
    db.commit()
    db.refresh(team)

    if athlete_ids:
        db.query(Athlete).filter(Athlete.id.in_(athlete_ids)).update(
            {"team_id": team.id}, synchronize_session=False
        )
        db.commit()
        db.refresh(team)

    return team


@router.get("/{team_id}", response_model=TeamDetail)
def get_team(team_id: int, db: Session = Depends(get_db)):
    return _get_team_or_404(team_id, db)


@router.put("/{team_id}", response_model=TeamOut)
def update_team(
    team_id: int,
    data: TeamUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    team = _get_team_or_404(team_id, db)
    if data.sport_id is not None:
        sport = db.query(Sport).filter(Sport.id == data.sport_id).first()
        if not sport:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modalidade não encontrada")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(team, field, value)
    db.commit()
    db.refresh(team)
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    team = _get_team_or_404(team_id, db)
    db.delete(team)
    db.commit()


# ---------------------------------------------------------------------------
# Atletas
# ---------------------------------------------------------------------------

@router.get("/{team_id}/athletes/", response_model=list[AthleteOut])
def list_athletes(team_id: int, db: Session = Depends(get_db)):
    _get_team_or_404(team_id, db)
    return (
        db.query(Athlete)
        .filter(Athlete.team_id == team_id)
        .order_by(Athlete.number, Athlete.name)
        .all()
    )


@router.post("/{team_id}/athletes/", response_model=AthleteOut, status_code=status.HTTP_201_CREATED)
def create_athlete(
    team_id: int,
    data: AthleteCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    _get_team_or_404(team_id, db)
    athlete = Athlete(**data.model_dump(exclude={"team_id"}), team_id=team_id)
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return athlete


@router.put("/{team_id}/athletes/{athlete_id}", response_model=AthleteOut)
def update_athlete(
    team_id: int,
    athlete_id: int,
    data: AthleteUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    athlete = _get_athlete_or_404(team_id, athlete_id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(athlete, field, value)
    db.commit()
    db.refresh(athlete)
    return athlete


@router.delete("/{team_id}/athletes/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_athlete(
    team_id: int,
    athlete_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    athlete = _get_athlete_or_404(team_id, athlete_id, db)
    db.delete(athlete)
    db.commit()
