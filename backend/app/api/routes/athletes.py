"""
routes/athletes.py
==================
CRUD de atletas independente de equipe.
team_id e opcional — atleta pode existir sem equipe (status "livre").
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.api.deps import require_organizer
from app.db.models import Athlete, AthleteTeam, Sport, Team, User
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


# ---------------------------------------------------------------------------
# Vínculos de equipe (N:N)
# ---------------------------------------------------------------------------

class AthleteTeamIn(BaseModel):
    team_id: int


@router.get("/{athlete_id}/teams")
def list_athlete_teams(athlete_id: int, db: Session = Depends(get_db)):
    athlete = _get_or_404(athlete_id, db)
    return [
        {
            "id": at.id,
            "team_id": at.team_id,
            "team_name": at.team.name if at.team else None,
            "team_logo": at.team.logo_url if at.team else None,
            "sport_id": at.sport_id,
            "sport_name": at.sport.name if at.sport else None,
            "sport_slug": at.sport.slug if at.sport else None,
        }
        for at in (athlete.athlete_teams or [])
    ]


@router.put("/{athlete_id}/teams", status_code=status.HTTP_201_CREATED)
def link_athlete_team(
    athlete_id: int,
    data: AthleteTeamIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_organizer),
):
    athlete = _get_or_404(athlete_id, db)
    team = db.query(Team).filter(Team.id == data.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Equipe não encontrada")

    sport_id = team.sport_id
    sport = db.query(Sport).filter(Sport.id == sport_id).first()
    sport_name = sport.name if sport else f"Modalidade {sport_id}"

    # Verificar se atleta já tem vínculo nessa modalidade
    existing = db.query(AthleteTeam).filter(
        AthleteTeam.athlete_id == athlete_id,
        AthleteTeam.sport_id == sport_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Atleta já está em uma equipe de {sport_name}",
        )

    # Verificar se já está nessa equipe especificamente
    existing_link = db.query(AthleteTeam).filter(
        AthleteTeam.athlete_id == athlete_id,
        AthleteTeam.team_id == data.team_id,
    ).first()
    if existing_link:
        raise HTTPException(status_code=400, detail="Atleta já está vinculado a esta equipe")

    at = AthleteTeam(athlete_id=athlete_id, team_id=data.team_id, sport_id=sport_id)
    db.add(at)

    # Atualizar team_id principal se ainda não tiver equipe
    if athlete.team_id is None:
        athlete.team_id = data.team_id

    db.commit()
    db.refresh(at)
    return {
        "id": at.id,
        "team_id": at.team_id,
        "team_name": team.name,
        "sport_id": at.sport_id,
        "sport_name": sport_name,
    }


@router.delete("/{athlete_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_athlete_team(
    athlete_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_organizer),
):
    at = db.query(AthleteTeam).filter(
        AthleteTeam.athlete_id == athlete_id,
        AthleteTeam.team_id == team_id,
    ).first()
    if not at:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    db.delete(at)

    # Se o team_id principal era essa equipe, atualizar para a próxima disponível
    athlete = _get_or_404(athlete_id, db)
    if athlete.team_id == team_id:
        remaining = db.query(AthleteTeam).filter(
            AthleteTeam.athlete_id == athlete_id,
            AthleteTeam.team_id != team_id,
        ).first()
        athlete.team_id = remaining.team_id if remaining else None

    db.commit()
