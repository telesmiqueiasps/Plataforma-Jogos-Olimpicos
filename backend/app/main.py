import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import athletes, auth, boardgame, cantina, championships, churches, credentials, draws, games, race, sports, suspensions, teams, tenis_mesa, users, webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

logger.info(f"CORS allowed origins: {settings.allowed_origins_list}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(athletes.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(sports.router, prefix="/api")
app.include_router(teams.router, prefix="/api")
app.include_router(championships.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(suspensions.router, prefix="/api")
app.include_router(draws.router, prefix="/api")
app.include_router(race.router, prefix="/api")
app.include_router(boardgame.router, prefix="/api")
app.include_router(tenis_mesa.router, prefix="/api")
app.include_router(cantina.router, prefix="/api")
app.include_router(credentials.router, prefix="/api")
app.include_router(churches.router, prefix="/api")
app.include_router(webhook.router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health")
def health():
    return {"status": "healthy"}
