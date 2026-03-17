from typing import Optional
from pydantic import BaseModel


class SportCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    rules_config: Optional[dict] = None


class SportOut(BaseModel):
    id: int
    name: str
    slug: Optional[str]
    rules_config: Optional[dict]

    model_config = {"from_attributes": True}
