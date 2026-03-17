from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------

class StandingEntry(BaseModel):
    position: int
    team_id: int
    team_name: str
    games_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int

    class Config:
        from_attributes = True


class StandingsResult(BaseModel):
    championship_id: int
    championship_name: str
    entries: list[StandingEntry]


# ---------------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------------

class MatchupSlot(BaseModel):
    """Um confronto a ser criado — ainda sem data definitiva."""
    round_number: int
    phase: str
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    is_bye: bool = False


class ScheduleResult(BaseModel):
    championship_id: int
    total_rounds: int
    total_games: int
    games_created: list[int] = Field(default_factory=list, description="IDs dos jogos criados no banco")
    matchups: list[MatchupSlot]


# ---------------------------------------------------------------------------
# Elimination bracket
# ---------------------------------------------------------------------------

class BracketGame(BaseModel):
    slot: int                   # posição no bracket (1-indexed por round)
    round_number: int
    phase: str                  # "round_of_16", "quarterfinal", "semifinal", "final"
    home_team_id: Optional[int]
    home_team_name: Optional[str]
    away_team_id: Optional[int]
    away_team_name: Optional[str]
    is_bye: bool = False
    game_id: Optional[int] = None   # preenchido quando persistido


class BracketRound(BaseModel):
    round_number: int
    phase: str
    games: list[BracketGame]


class BracketResult(BaseModel):
    championship_id: int
    bracket_size: int           # potência de 2 usada
    total_byes: int
    rounds: list[BracketRound]


# ---------------------------------------------------------------------------
# Suspensions
# ---------------------------------------------------------------------------

class SuspensionCreated(BaseModel):
    athlete_id: int
    athlete_name: str
    championship_id: int
    games_remaining: int
    reason: str
    auto_generated: bool = True
