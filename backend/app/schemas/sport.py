from typing import Optional
from pydantic import BaseModel


class SportCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None


class SportOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    icon: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True
