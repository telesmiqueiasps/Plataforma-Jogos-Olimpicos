"""
routes/draws.py
===============
Endpoints de sorteio e geração de calendário para campeonatos.

Todos os endpoints que modificam dados exigem role organizer ou admin.
O endpoint GET /bracket é público.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_organizer
from app.db.models import User
from app.db.session import get_async_db
from app.schemas.draw import (
    EliminationDrawRequest,
    ManualGameCreate,
    ManualGameResponse,
    RoundRobinDrawRequest,
    RoundRobinDrawResponse,
)
from app.schemas.standings import BracketResult
from app.services import draw_service

router = APIRouter(
    prefix="/championships",
    tags=["Sorteios & Calendário"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_from_service_error(exc: Exception) -> HTTPException:
    """Converte erros de domínio em respostas HTTP adequadas."""
    msg = str(exc)
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ---------------------------------------------------------------------------
# POST /championships/{id}/draw/round-robin
# ---------------------------------------------------------------------------

@router.post(
    "/{championship_id}/draw/round-robin",
    response_model=RoundRobinDrawResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sorteia o calendário de pontos corridos",
    description=(
        "Gera todos os jogos do campeonato usando o algoritmo circle-method. "
        "Com `randomize=true` a ordem dos times é embaralhada; com `randomize=false` "
        "use `teams_order` para definir a posição de cada time."
    ),
)
async def draw_round_robin(
    championship_id: int,
    body: RoundRobinDrawRequest,
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_organizer),
) -> RoundRobinDrawResponse:
    try:
        return await draw_service.execute_round_robin_draw(
            db=db,
            championship_id=championship_id,
            randomize=body.randomize,
            teams_order=body.teams_order,
            legs=body.legs,
        )
    except (ValueError, LookupError) as exc:
        raise _http_from_service_error(exc) from exc


# ---------------------------------------------------------------------------
# POST /championships/{id}/draw/elimination
# ---------------------------------------------------------------------------

@router.post(
    "/{championship_id}/draw/elimination",
    response_model=BracketResult,
    status_code=status.HTTP_201_CREATED,
    summary="Sorteia a chave eliminatória",
    description=(
        "Gera o bracket eliminatório. "
        "Use `seeded_team_ids` para definir cabeças de chave — eles ficarão "
        "automaticamente em lados opostos do bracket. "
        "BYEs são inseridos quando o número de times não é potência de 2."
    ),
)
async def draw_elimination(
    championship_id: int,
    body: EliminationDrawRequest,
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_organizer),
) -> BracketResult:
    try:
        return await draw_service.execute_elimination_draw(
            db=db,
            championship_id=championship_id,
            randomize=body.randomize,
            seeded_team_ids=body.seeded_team_ids,
            teams_order=body.teams_order,
        )
    except (ValueError, LookupError) as exc:
        raise _http_from_service_error(exc) from exc


# ---------------------------------------------------------------------------
# GET /championships/{id}/bracket
# ---------------------------------------------------------------------------

@router.get(
    "/{championship_id}/bracket",
    response_model=BracketResult,
    summary="Retorna o bracket atual",
    description=(
        "Reconstrói o bracket a partir dos jogos existentes no banco. "
        "Endpoint público — não exige autenticação."
    ),
)
async def get_bracket(
    championship_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> BracketResult:
    try:
        return await draw_service.get_championship_bracket(db, championship_id)
    except (ValueError, LookupError) as exc:
        raise _http_from_service_error(exc) from exc


# ---------------------------------------------------------------------------
# POST /championships/{id}/games  (criação manual)
# ---------------------------------------------------------------------------

@router.post(
    "/{championship_id}/games",
    response_model=ManualGameResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um jogo manualmente",
    description=(
        "Cria um único jogo sem usar o sorteio automático. "
        "Útil para jogos de abertura ou confrontos definidos pela organização. "
        "Ambos os times devem estar inscritos no campeonato."
    ),
)
async def create_manual_game(
    championship_id: int,
    body: ManualGameCreate,
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_organizer),
) -> ManualGameResponse:
    try:
        return await draw_service.create_manual_game(
            db=db,
            championship_id=championship_id,
            data=body,
        )
    except (ValueError, LookupError) as exc:
        raise _http_from_service_error(exc) from exc
