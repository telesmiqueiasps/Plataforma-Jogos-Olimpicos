from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.user import Token, UserCreate, UserOut
from app.services.user_service import authenticate_user, create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["Autenticação"])


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
    expire_minutes = 720 if user.role in ("secretaria", "cantina") else None
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=expire_minutes) if expire_minutes else None,
    )
    return {"access_token": token, "token_type": "bearer"}
