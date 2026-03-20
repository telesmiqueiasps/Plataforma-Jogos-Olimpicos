from datetime import datetime
from typing import List, Optional, Any

from pydantic import BaseModel, model_validator


class TeamShort(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None

    model_config = {"from_attributes": True}


class GameCreate(BaseModel):
    home_team_id: int
    away_team_id: int
    scheduled_at: datetime
    venue: Optional[str] = None
    phase: Optional[str] = None
    round_number: Optional[int] = None
    extra_data: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def _teams_differ(self) -> "GameCreate":
        if self.home_team_id == self.away_team_id:
            raise ValueError("home_team_id e away_team_id devem ser times diferentes")
        return self


class GameUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    venue: Optional[str] = None
    phase: Optional[str] = None
    round_number: Optional[int] = None
    status: Optional[str] = None


class GameResultUpdate(BaseModel):
    home_score: int
    away_score: int
    notes: Optional[str] = None


class VolleyballSet(BaseModel):
    home_points: int
    away_points: int


class VolleyballResultUpdate(BaseModel):
    sets: List[VolleyballSet]
    notes: Optional[str] = None


class BasketballQuarter(BaseModel):
    home_points: int
    away_points: int


class GameResultBody(BaseModel):
    """Body flexível — aceita futsal (home_score/away_score), vôlei (sets) e basquete (quarters).
    Para vôlei/basquete, finalize=False salva sem encerrar (status fica 'live').
    finalize=True (padrão) encerra a partida e muda status para 'finished'.
    """
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    notes: Optional[str] = None
    sets: Optional[List[VolleyballSet]] = None
    quarters: Optional[List[BasketballQuarter]] = None
    overtime: Optional[BasketballQuarter] = None
    finalize: Optional[bool] = True


class GameResultOut(BaseModel):
    id: int
    game_id: int
    home_score: int
    away_score: int
    notes: Optional[str] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None

    model_config = {"from_attributes": True}


class GameEventCreate(BaseModel):
    athlete_id: Optional[int] = None
    team_id: Optional[int] = None
    event_type: str          # goal | yellow_card | red_card | point | foul
    minute: Optional[int] = None
    description: Optional[str] = None


class GameEventOut(BaseModel):
    id: int
    game_id: int
    athlete_id: Optional[int] = None
    athlete_name: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    event_type: str
    minute: Optional[int] = None
    description: Optional[str] = None
    created_by_name: Optional[str] = None

    model_config = {"from_attributes": True}


class GameOut(BaseModel):
    id: int
    championship_id: int
    home_team_id: int
    away_team_id: int
    home_team: Optional[TeamShort] = None
    away_team: Optional[TeamShort] = None
    scheduled_at: datetime
    venue: Optional[str] = None
    status: str
    phase: Optional[str] = None
    round_number: Optional[int] = None
    extra_data: Optional[dict] = None
    result: Optional[GameResultOut] = None
    phase_name: Optional[str] = None

    model_config = {"from_attributes": True}
