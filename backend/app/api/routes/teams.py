"""
routes/teams.py
===============
CRUD de equipes e atletas.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from sqlalchemy import func, update as sa_update

from app.db.models import Athlete, Sport, Suspension, Team, TeamSport, User
from app.db.session import get_db
from app.schemas.athlete import AthleteCreate, AthleteOut, AthleteUpdate
from app.schemas.team import TeamCreate, TeamDetail, TeamOut, TeamUpdate
from app.services import suspension_service

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
        # Retorna equipes com sport_id principal OU com vínculo N:N para o sport_id
        from sqlalchemy import exists
        q = q.filter(
            (Team.sport_id == sport_id) |
            exists().where(
                (TeamSport.team_id == Team.id) & (TeamSport.sport_id == sport_id)
            )
        )
    teams = q.order_by(Team.name).all()
    if teams:
        counts = {
            row[0]: row[1]
            for row in db.query(Athlete.team_id, func.count(Athlete.id))
            .filter(Athlete.team_id.in_([t.id for t in teams]), Athlete.active == True)
            .group_by(Athlete.team_id)
            .all()
        }
        for t in teams:
            t.athlete_count = counts.get(t.id, 0)
    return teams


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
    extra_sport_ids = list(data.sport_ids or [])

    team = Team(**data.model_dump(exclude={"athlete_ids", "sport_ids"}), created_by=current_user.id)
    db.add(team)
    db.flush()  # obter team.id antes de criar sport_links

    # Cria vínculos N:N: sempre inclui o sport_id principal
    all_sport_ids = list(dict.fromkeys([data.sport_id] + extra_sport_ids))  # deduplicado, principal primeiro
    for sid in all_sport_ids:
        db.add(TeamSport(team_id=team.id, sport_id=sid))

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

    for field, value in data.model_dump(exclude_none=True, exclude={"sport_ids"}).items():
        setattr(team, field, value)

    if data.sport_ids is not None:
        # Substitui todos os vínculos N:N, mantendo sempre o sport_id principal no conjunto
        principal_id = data.sport_id if data.sport_id is not None else team.sport_id
        new_ids = list(dict.fromkeys([principal_id] + list(data.sport_ids)))
        db.query(TeamSport).filter(TeamSport.team_id == team_id).delete()
        for sid in new_ids:
            db.add(TeamSport(team_id=team_id, sport_id=sid))

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
def list_athletes(
    team_id: int,
    championship_id: Optional[int] = Query(None, description="Se informado, inclui status de suspensão"),
    db: Session = Depends(get_db),
):
    _get_team_or_404(team_id, db)
    athletes = (
        db.query(Athlete)
        .filter(Athlete.team_id == team_id)
        .order_by(Athlete.number, Athlete.name)
        .all()
    )
    if championship_id:
        for a in athletes:
            susp = suspension_service.get_athlete_suspension(db, a.id, championship_id)
            a.suspended = susp is not None
            a.suspension_reason = susp.reason if susp else None
    return athletes


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
