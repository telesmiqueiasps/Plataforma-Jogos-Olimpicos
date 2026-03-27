"""
routes/churches.py
==================
Endpoints para gerenciamento de presbitérios e igrejas.
Endpoints de leitura são públicos (formulário de credenciamento).
Endpoints de escrita requerem autenticação admin.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.db.models import Church, Presbytery
from app.db.session import get_db
from app.api.deps import require_admin

router = APIRouter(tags=["Churches"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PresbyterySchemCreate(BaseModel):
    name: str

class PresbyterySchemUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None

class ChurchSchemaCreate(BaseModel):
    name: str
    presbytery_id: Optional[int] = None
    city: Optional[str] = None

class ChurchSchemaUpdate(BaseModel):
    name: Optional[str] = None
    presbytery_id: Optional[int] = None
    city: Optional[str] = None
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Presbitérios — público
# ---------------------------------------------------------------------------

@router.get("/presbyteries/")
def list_presbyteries(db: Session = Depends(get_db)):
    """Lista todos os presbitérios ativos ordenados por nome."""
    rows = (
        db.query(Presbytery)
        .filter(Presbytery.active == True)
        .order_by(Presbytery.name)
        .all()
    )
    return [{"id": r.id, "name": r.name} for r in rows]


# ---------------------------------------------------------------------------
# Igrejas — público
# ---------------------------------------------------------------------------

@router.get("/churches/search")
def search_churches(
    q: str = "",
    presbytery_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Busca igrejas por nome (autocomplete). Retorna top 10 matches."""
    query = db.query(Church).filter(Church.active == True)
    if q:
        query = query.filter(func.lower(Church.name).contains(q.lower()))
    if presbytery_id:
        query = query.filter(Church.presbytery_id == presbytery_id)
    rows = query.order_by(Church.name).limit(10).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "city": r.city,
            "presbytery_id": r.presbytery_id,
            "presbytery_name": r.presbytery.name if r.presbytery else None,
        }
        for r in rows
    ]


@router.get("/churches/")
def list_churches(
    presbytery_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Lista todas as igrejas ativas. Filtro opcional por presbitério."""
    query = db.query(Church).filter(Church.active == True)
    if presbytery_id:
        query = query.filter(Church.presbytery_id == presbytery_id)
    rows = query.order_by(Church.name).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "city": r.city,
            "presbytery_id": r.presbytery_id,
            "presbytery_name": r.presbytery.name if r.presbytery else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Presbitérios — admin
# ---------------------------------------------------------------------------

@router.post("/presbyteries/", dependencies=[Depends(require_admin)])
def create_presbytery(body: PresbyterySchemCreate, db: Session = Depends(get_db)):
    existing = db.query(Presbytery).filter(func.lower(Presbytery.name) == body.name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Presbitério já cadastrado com este nome.")
    p = Presbytery(name=body.name.strip())
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "active": p.active}


@router.put("/presbyteries/{presbytery_id}", dependencies=[Depends(require_admin)])
def update_presbytery(presbytery_id: int, body: PresbyterySchemUpdate, db: Session = Depends(get_db)):
    p = db.query(Presbytery).filter(Presbytery.id == presbytery_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presbitério não encontrado.")
    if body.name is not None:
        p.name = body.name.strip()
    if body.active is not None:
        p.active = body.active
    db.commit()
    return {"id": p.id, "name": p.name, "active": p.active}


@router.delete("/presbyteries/{presbytery_id}", dependencies=[Depends(require_admin)])
def delete_presbytery(presbytery_id: int, db: Session = Depends(get_db)):
    p = db.query(Presbytery).filter(Presbytery.id == presbytery_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Presbitério não encontrado.")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Igrejas — admin
# ---------------------------------------------------------------------------

@router.post("/churches/", dependencies=[Depends(require_admin)])
def create_church(body: ChurchSchemaCreate, db: Session = Depends(get_db)):
    c = Church(
        name=body.name.strip(),
        presbytery_id=body.presbytery_id,
        city=body.city.strip() if body.city else None,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "name": c.name, "city": c.city, "presbytery_id": c.presbytery_id, "active": c.active}


@router.put("/churches/{church_id}", dependencies=[Depends(require_admin)])
def update_church(church_id: int, body: ChurchSchemaUpdate, db: Session = Depends(get_db)):
    c = db.query(Church).filter(Church.id == church_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Igreja não encontrada.")
    if body.name is not None:
        c.name = body.name.strip()
    if body.presbytery_id is not None:
        c.presbytery_id = body.presbytery_id
    if body.city is not None:
        c.city = body.city.strip()
    if body.active is not None:
        c.active = body.active
    db.commit()
    return {"id": c.id, "name": c.name, "city": c.city, "presbytery_id": c.presbytery_id, "active": c.active}


@router.delete("/churches/{church_id}", dependencies=[Depends(require_admin)])
def delete_church(church_id: int, db: Session = Depends(get_db)):
    c = db.query(Church).filter(Church.id == church_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Igreja não encontrada.")
    db.delete(c)
    db.commit()
    return {"ok": True}
