from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_admin
from app.db.models import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/", response_model=list[UserOut])
def list_users(
    db=None,
    current_user: User = Depends(require_admin),
):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        return db.query(User).all()
    finally:
        db.close()
