from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Round-robin
# ---------------------------------------------------------------------------

class RoundRobinDrawRequest(BaseModel):
    randomize: bool = True
    teams_order: Optional[list[int]] = Field(
        default=None,
        description="Ordem explícita de team_ids. Ignorado quando randomize=True.",
    )
    legs: int = Field(default=2, ge=1, le=2, description="1=turno único | 2=turno+returno")

    @model_validator(mode="after")
    def _check_order_only_when_fixed(self) -> "RoundRobinDrawRequest":
        if self.randomize and self.teams_order is not None:
            raise ValueError("teams_order é ignorado quando randomize=True — omita ou defina randomize=False")
        return self


class GameSlot(BaseModel):
    game_id: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    scheduled_at: datetime
    status: str


class RoundDetail(BaseModel):
    round_number: int
    phase: str
    games: list[GameSlot]


class RoundRobinDrawResponse(BaseModel):
    championship_id: int
    championship_name: str
    legs: int
    total_rounds: int
    total_games: int
    rounds: list[RoundDetail]


# ---------------------------------------------------------------------------
# Eliminatória
# ---------------------------------------------------------------------------

class EliminationDrawRequest(BaseModel):
    randomize: bool = True
    seeded_team_ids: Optional[list[int]] = Field(
        default=None,
        description=(
            "IDs dos times cabeças de chave, em ordem de prioridade (seed 1, 2, ...). "
            "Eles ficam em partes opostas do bracket."
        ),
    )
    teams_order: Optional[list[int]] = Field(
        default=None,
        description="Ordem completa e manual de todos os times (ignora randomize e seeded_team_ids).",
    )

    @model_validator(mode="after")
    def _check_conflict(self) -> "EliminationDrawRequest":
        if self.teams_order is not None and self.seeded_team_ids is not None:
            raise ValueError(
                "Informe teams_order OU seeded_team_ids, não os dois ao mesmo tempo."
            )
        return self


# ---------------------------------------------------------------------------
# Jogo manual
# ---------------------------------------------------------------------------

class ManualGameCreate(BaseModel):
    home_team_id: int
    away_team_id: int
    scheduled_at: datetime
    venue: Optional[str] = None
    phase: Optional[str] = None
    round_number: Optional[int] = None
    extra_data: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def _home_away_differ(self) -> "ManualGameCreate":
        if self.home_team_id == self.away_team_id:
            raise ValueError("home_team_id e away_team_id devem ser times diferentes")
        return self


class ManualGameResponse(BaseModel):
    game_id: int
    championship_id: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    scheduled_at: datetime
    venue: Optional[str]
    phase: Optional[str]
    round_number: Optional[int]
    status: str
