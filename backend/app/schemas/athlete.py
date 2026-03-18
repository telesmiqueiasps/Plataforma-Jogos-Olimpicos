from typing import Optional

from pydantic import BaseModel


class AthleteCreate(BaseModel):
    name: str
    number: Optional[int] = None
    position: Optional[str] = None
    photo_url: Optional[str] = None
    active: bool = True
    team_id: Optional[int] = None


class AthleteUpdate(BaseModel):
    name: Optional[str] = None
    number: Optional[int] = None
    position: Optional[str] = None
    photo_url: Optional[str] = None
    active: Optional[bool] = None
    team_id: Optional[int] = None


class AthleteOut(BaseModel):
    id: int
    name: str
    number: Optional[int] = None
    position: Optional[str] = None
    photo_url: Optional[str] = None
    active: bool
    team_id: Optional[int] = None

    model_config = {"from_attributes": True}
