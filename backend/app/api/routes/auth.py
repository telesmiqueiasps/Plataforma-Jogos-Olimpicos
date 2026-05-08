from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.user import Token, UserCreate, UserOut
from app.services.user_service import authenticate_user, create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["Autenticação"])

# Tempo de expiração por role (em minutos)
_EXPIRE_MINUTES: dict[str, int] = {
    "secretaria": 720,  # 12h
    "cantina":    720,  # 12h
    "admin":      480,  # 8h
    "organizer":  240,  # 4h
}


def _expire_for(role: str) -> timedelta:
    return timedelta(minutes=_EXPIRE_MINUTES.get(role, 240))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    return create_user(db, data)


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=_expire_for(user.role),
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
def refresh_token(current_user: User = Depends(get_current_user)):
    """Renova o token com o mesmo tempo de expiração do role do usuário."""
    token = create_access_token(
        data={"sub": str(current_user.id)},
        expires_delta=_expire_for(current_user.role),
    )
    return {"access_token": token, "token_type": "bearer"}
