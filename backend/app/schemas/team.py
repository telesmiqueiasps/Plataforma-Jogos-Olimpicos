from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SportShort(BaseModel):
    id: int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class AthleteShort(BaseModel):
    id: int
    name: str
    number: Optional[int] = None
    position: Optional[str] = None
    active: bool

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    name: str
    sport_id: int
    logo_url: Optional[str] = None
    athlete_ids: List[int] = []
    sport_ids: List[int] = []  # modalidades adicionais (N:N)


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    sport_id: Optional[int] = None
    logo_url: Optional[str] = None
    sport_ids: Optional[List[int]] = None  # se fornecido, substitui todas as modalidades


class TeamOut(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None
    sport_id: int
    sport: Optional[SportShort] = None
    sports: List[SportShort] = []  # todas as modalidades via N:N
    created_by: Optional[int] = None
    created_at: datetime
    athlete_count: int = 0

    model_config = {"from_attributes": True}


class TeamDetail(TeamOut):
    athletes: list[AthleteShort] = []
