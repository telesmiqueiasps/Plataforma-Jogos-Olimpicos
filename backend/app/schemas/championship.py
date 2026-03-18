from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SportShort(BaseModel):
    id: int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class TeamShort(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ChampionshipCreate(BaseModel):
    name: str
    sport_id: int
    format: str
    status: Optional[str] = "draft"
    rules_config: dict = {}
    extra_data: Optional[dict] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    team_ids: List[int] = []
    group_count: Optional[int] = None
    group_phase_format: str = "round_robin"


class ChampionshipUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    rules_config: Optional[dict] = None
    extra_data: Optional[dict] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    current_phase: Optional[str] = None
    group_count: Optional[int] = None
    group_phase_format: Optional[str] = None
    teams_per_group: Optional[int] = None
    classifieds_per_group: Optional[int] = None


class ChampionshipConfigUpdate(BaseModel):
    points_win: Optional[int] = None
    points_draw: Optional[int] = None
    points_loss: Optional[int] = None
    tiebreaker_order: Optional[List[str]] = None
    yellow_card_threshold: Optional[int] = None
    yellow_suspension_games: Optional[int] = None
    red_card_suspension_games: Optional[int] = None
    red_card_expulsion: Optional[bool] = None
    classifieds_per_group: Optional[int] = None


class ChampionshipOut(BaseModel):
    id: int
    name: str
    sport_id: int
    sport: Optional[SportShort] = None
    format: str
    status: str
    rules_config: dict
    extra_data: Optional[dict] = None
    created_by: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    current_phase: Optional[str] = None
    group_count: Optional[int] = None
    group_phase_format: Optional[str] = None
    teams_per_group: Optional[int] = None
    classifieds_per_group: Optional[int] = None
    knockout_bracket: Optional[dict] = None

    model_config = {"from_attributes": True}


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
    goal_diff: int
    points: int


class GroupDrawRequest(BaseModel):
    group_count: int
    teams_per_group: Optional[int] = None


class GroupTeam(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None


class GroupEntry(BaseModel):
    group: str
    teams: List[GroupTeam]
