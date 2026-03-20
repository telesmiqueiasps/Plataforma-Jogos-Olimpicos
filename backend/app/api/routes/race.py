"""
routes/race.py
==============
Endpoints de corrida de rua (modalidade individual).
"""

from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_organizer
from app.db.models import Athlete, Championship, RaceResult, User
from app.db.session import get_db
from app.schemas.race import BulkEnrollIn, RaceResultCreate, RaceResultOut, RaceResultUpdate

router = APIRouter(prefix="/championships", tags=["Corrida"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_champ_or_404(champ_id: int, db: Session) -> Championship:
    c = db.query(Championship).filter(Championship.id == champ_id).first()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campeonato não encontrado")
    return c


def _get_result_or_404(champ_id: int, result_id: int, db: Session) -> RaceResult:
    r = (
        db.query(RaceResult)
        .filter(RaceResult.id == result_id, RaceResult.championship_id == champ_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resultado não encontrado")
    return r


# ---------------------------------------------------------------------------
# Participantes
# ---------------------------------------------------------------------------

@router.get("/{champ_id}/race/participants", response_model=List[RaceResultOut])
def list_participants(
    champ_id: int,
    category: Optional[str] = Query(None, description="Filtrar por categoria"),
    db: Session = Depends(get_db),
):
    _get_champ_or_404(champ_id, db)
    q = db.query(RaceResult).filter(RaceResult.championship_id == champ_id)
    if category:
        q = q.filter(RaceResult.category == category)
    # Posicionados primeiro (ASC), depois sem posição; dentro de cada grupo por bib_number
    results = q.order_by(RaceResult.position.asc(), RaceResult.bib_number.asc()).all()
    return results


@router.post("/{champ_id}/race/participants", response_model=RaceResultOut, status_code=status.HTTP_201_CREATED)
def enroll_participant(
    champ_id: int,
    data: RaceResultCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(champ_id, db)
    athlete = db.query(Athlete).filter(Athlete.id == data.athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Atleta não encontrado")

    existing = (
        db.query(RaceResult)
        .filter(RaceResult.championship_id == champ_id, RaceResult.athlete_id == data.athlete_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Atleta já inscrito nesta corrida")

    r = RaceResult(championship_id=champ_id, created_by=_current_user.id, **data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.post("/{champ_id}/race/participants/bulk", response_model=List[RaceResultOut], status_code=status.HTTP_201_CREATED)
def bulk_enroll(
    champ_id: int,
    data: BulkEnrollIn,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(champ_id, db)

    existing_ids = {
        row[0]
        for row in db.query(RaceResult.athlete_id)
        .filter(RaceResult.championship_id == champ_id)
        .all()
    }

    new_results = []
    for aid in data.athlete_ids:
        if aid in existing_ids:
            continue
        athlete = db.query(Athlete).filter(Athlete.id == aid).first()
        if not athlete:
            continue
        r = RaceResult(
            championship_id=champ_id,
            athlete_id=aid,
            category=data.category,
            status="registered",
            created_by=_current_user.id,
        )
        db.add(r)
        new_results.append(r)

    db.commit()
    for r in new_results:
        db.refresh(r)
    return new_results


@router.put("/{champ_id}/race/participants/{result_id}", response_model=RaceResultOut)
def update_participant(
    champ_id: int,
    result_id: int,
    data: RaceResultUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    r = _get_result_or_404(champ_id, result_id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{champ_id}/race/participants/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_participant(
    champ_id: int,
    result_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    r = _get_result_or_404(champ_id, result_id, db)
    db.delete(r)
    db.commit()


# ---------------------------------------------------------------------------
# Finalizar corrida (calcular posições por tempo)
# ---------------------------------------------------------------------------

@router.post("/{champ_id}/race/finalize", response_model=List[RaceResultOut])
def finalize_race(
    champ_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Ordena atletas por finish_time e atribui posições (dentro de cada categoria se houver)."""
    _get_champ_or_404(champ_id, db)

    # Apenas atletas com tempo registrado e não DNF/DSQ
    finishers = (
        db.query(RaceResult)
        .filter(
            RaceResult.championship_id == champ_id,
            RaceResult.finish_time.isnot(None),
            RaceResult.status.notin_(["dnf", "dsq"]),
        )
        .all()
    )

    def _time_key(r: RaceResult) -> str:
        return r.finish_time or "99:99:99"

    categories = {r.category for r in finishers}
    # Se há categorias distintas (excluindo None), atribuir posição dentro de cada categoria
    named_cats = [c for c in categories if c]

    if named_cats:
        by_cat: dict = defaultdict(list)
        for r in finishers:
            by_cat[r.category].append(r)
        for cat_results in by_cat.values():
            cat_results.sort(key=_time_key)
            for i, r in enumerate(cat_results):
                r.position = i + 1
                r.status = "finished"
    else:
        finishers.sort(key=_time_key)
        for i, r in enumerate(finishers):
            r.position = i + 1
            r.status = "finished"

    db.commit()

    all_results = (
        db.query(RaceResult)
        .filter(RaceResult.championship_id == champ_id)
        .order_by(RaceResult.position.asc(), RaceResult.bib_number.asc())
        .all()
    )
    return all_results


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

@router.get("/{champ_id}/race/ranking")
def get_ranking(champ_id: int, db: Session = Depends(get_db)):
    """Ranking agrupado por categoria: { 'overall': [...], 'Masculino': [...], ... }"""
    _get_champ_or_404(champ_id, db)

    all_results = (
        db.query(RaceResult)
        .filter(
            RaceResult.championship_id == champ_id,
            RaceResult.status.notin_(["dnf", "dsq"]),
        )
        .order_by(RaceResult.position.asc(), RaceResult.bib_number.asc())
        .all()
    )

    def _to_dict(r: RaceResult) -> dict:
        return {
            "id": r.id,
            "athlete_id": r.athlete_id,
            "athlete_name": r.athlete_name,
            "athlete_photo_url": r.athlete_photo_url,
            "position": r.position,
            "finish_time": r.finish_time,
            "category": r.category,
            "bib_number": r.bib_number,
            "status": r.status,
            "notes": r.notes,
        }

    ranking: dict = {"overall": []}
    by_cat: dict = defaultdict(list)

    for r in all_results:
        d = _to_dict(r)
        ranking["overall"].append(d)
        if r.category:
            by_cat[r.category].append(d)

    ranking.update(by_cat)
    return ranking
