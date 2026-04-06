"""
routes/modality_mappings.py
===========================
CRUD de mapeamentos de palavras-chave → slug de modalidade.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.models import ModalityMapping, Sport, User
from app.db.session import get_db

router = APIRouter(prefix="/modality-mappings", tags=["Mapeamentos de Modalidade"])

# Nomes legíveis por slug (fallback caso não exista no cadastro de esportes)
_SLUG_LABELS = {
    "futsal":           "Futsal",
    "futsal_masculino": "Futsal Masculino",
    "futsal_feminino":  "Futsal Feminino",
    "volleyball":       "Vôlei",
    "basketball":       "Basquete",
    "running":          "Corrida",
    "tenis_mesa":       "Tênis de Mesa",
    "domino":           "Dominó",
    "xadrez":           "Xadrez",
    "dama":             "Dama",
}


def _sport_name(slug: str, sports_map: dict) -> str:
    return sports_map.get(slug) or _SLUG_LABELS.get(slug) or slug


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MappingCreate(BaseModel):
    keyword:    str
    sport_slug: str
    active:     bool = True


class MappingUpdate(BaseModel):
    keyword:    Optional[str] = None
    sport_slug: Optional[str] = None
    active:     Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_mappings(db: Session = Depends(get_db)):
    """Lista todos os mapeamentos — público."""
    mappings = (
        db.query(ModalityMapping)
        .order_by(ModalityMapping.sport_slug, ModalityMapping.keyword)
        .all()
    )
    sports = db.query(Sport).all()
    sports_map = {s.slug: s.name for s in sports}

    return [
        {
            "id":         m.id,
            "keyword":    m.keyword,
            "sport_slug": m.sport_slug,
            "sport_name": _sport_name(m.sport_slug, sports_map),
            "active":     m.active,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mappings
    ]


@router.post("/", status_code=201)
def create_mapping(
    body: MappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Cria novo mapeamento — requer admin."""
    keyword = body.keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="Palavra-chave não pode ser vazia.")

    existing = db.query(ModalityMapping).filter(
        ModalityMapping.keyword == keyword
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um mapeamento para a palavra-chave '{keyword}'.",
        )

    mapping = ModalityMapping(
        keyword=keyword,
        sport_slug=body.sport_slug.strip(),
        active=body.active,
        created_by=current_user.id,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    sports = db.query(Sport).all()
    sports_map = {s.slug: s.name for s in sports}
    return {
        "id":         mapping.id,
        "keyword":    mapping.keyword,
        "sport_slug": mapping.sport_slug,
        "sport_name": _sport_name(mapping.sport_slug, sports_map),
        "active":     mapping.active,
        "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
    }


@router.put("/{mapping_id}")
def update_mapping(
    mapping_id: int,
    body: MappingUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Atualiza mapeamento — requer admin."""
    mapping = db.query(ModalityMapping).filter(ModalityMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado.")

    if body.keyword is not None:
        mapping.keyword = body.keyword.strip().lower()
    if body.sport_slug is not None:
        mapping.sport_slug = body.sport_slug.strip()
    if body.active is not None:
        mapping.active = body.active

    db.commit()
    db.refresh(mapping)

    sports = db.query(Sport).all()
    sports_map = {s.slug: s.name for s in sports}
    return {
        "id":         mapping.id,
        "keyword":    mapping.keyword,
        "sport_slug": mapping.sport_slug,
        "sport_name": _sport_name(mapping.sport_slug, sports_map),
        "active":     mapping.active,
        "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
    }


@router.delete("/{mapping_id}", status_code=204)
def delete_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Remove mapeamento — requer admin."""
    mapping = db.query(ModalityMapping).filter(ModalityMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado.")
    db.delete(mapping)
    db.commit()
    return None
