from typing import List, Optional

from pydantic import BaseModel


class RaceResultCreate(BaseModel):
    athlete_id: int
    position: Optional[int] = None
    finish_time: Optional[str] = None
    category: Optional[str] = None
    bib_number: Optional[int] = None
    notes: Optional[str] = None
    status: str = "registered"


class RaceResultUpdate(BaseModel):
    position: Optional[int] = None
    finish_time: Optional[str] = None
    category: Optional[str] = None
    bib_number: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class BulkEnrollIn(BaseModel):
    athlete_ids: List[int]
    category: Optional[str] = None


class RaceResultOut(BaseModel):
    id: int
    championship_id: int
    athlete_id: int
    athlete_name: Optional[str] = None
    athlete_photo_url: Optional[str] = None
    position: Optional[int] = None
    finish_time: Optional[str] = None
    category: Optional[str] = None
    bib_number: Optional[int] = None
    notes: Optional[str] = None
    status: str
    created_by_name: Optional[str] = None

    model_config = {"from_attributes": True}
