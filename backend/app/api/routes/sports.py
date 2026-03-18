from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.models import Sport, User
from app.db.session import get_db
from app.schemas.sport import SportCreate, SportOut

router = APIRouter(prefix="/sports", tags=["Modalidades"])


@router.get("/", response_model=list[SportOut])
def list_sports(db: Session = Depends(get_db)):
    return db.query(Sport).all()


@router.get("/{sport_id}", response_model=SportOut)
def get_sport(sport_id: int, db: Session = Depends(get_db)):
    sport = db.query(Sport).filter(Sport.id == sport_id).first()
    if not sport:
        raise HTTPException(status_code=404, detail="Modalidade não encontrada")
    return sport


@router.post("/", response_model=SportOut, status_code=status.HTTP_201_CREATED)
def create_sport(
    data: SportCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sport = Sport(**data.model_dump())
    db.add(sport)
    db.commit()
    db.refresh(sport)
    return sport


@router.delete("/{sport_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sport(
    sport_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sport = db.query(Sport).filter(Sport.id == sport_id).first()
    if not sport:
        raise HTTPException(status_code=404, detail="Modalidade não encontrada")
    db.delete(sport)
    db.commit()
