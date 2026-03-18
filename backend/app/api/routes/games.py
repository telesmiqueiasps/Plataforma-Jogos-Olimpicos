"""
routes/games.py
===============
Detalhe de jogo, registro de resultado e eventos.
Após registrar resultado, verifica suspensões automáticas.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_organizer
from app.db.models import Athlete, Game, GameEvent, GameResult, Suspension, User
from app.db.session import get_db
from app.schemas.game import (
    GameEventCreate,
    GameEventOut,
    GameOut,
    GameResultOut,
    GameResultUpdate,
    GameUpdate,
)

router = APIRouter(prefix="/games", tags=["Jogos"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_game_or_404(game_id: int, db: Session) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogo não encontrado")
    return game


# ---------------------------------------------------------------------------
# Detalhe do jogo
# ---------------------------------------------------------------------------

@router.get("/{game_id}", response_model=GameOut)
def get_game(game_id: int, db: Session = Depends(get_db)):
    return _get_game_or_404(game_id, db)


# ---------------------------------------------------------------------------
# Atualizar jogo
# ---------------------------------------------------------------------------

@router.put("/{game_id}", response_model=GameOut)
def update_game(
    game_id: int,
    data: GameUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    game = _get_game_or_404(game_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(game, field, value)
    db.commit()
    db.refresh(game)
    return game


@router.delete("/{game_id}", status_code=204)
def delete_game(
    game_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    game = _get_game_or_404(game_id, db)
    db.delete(game)
    db.commit()


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@router.put("/{game_id}/result", response_model=GameResultOut)
def set_result(
    game_id: int,
    data: GameResultUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Registra ou atualiza o resultado de um jogo e marca status como 'finished'."""
    game = _get_game_or_404(game_id, db)

    if game.result:
        game.result.home_score = data.home_score
        game.result.away_score = data.away_score
        game.result.notes = data.notes
    else:
        result = GameResult(
            game_id=game_id,
            home_score=data.home_score,
            away_score=data.away_score,
            notes=data.notes,
        )
        db.add(result)
        game.result = result

    game.status = "finished"
    db.commit()
    db.refresh(game)

    _check_suspensions(game, db)

    return game.result


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@router.post("/{game_id}/events", response_model=GameEventOut, status_code=201)
def add_event(
    game_id: int,
    data: GameEventCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    game = _get_game_or_404(game_id, db)
    event = GameEvent(**data.model_dump(), game_id=game_id)
    db.add(event)
    db.commit()
    db.refresh(event)

    # Cartão vermelho gera suspensão imediata
    if data.event_type == "red_card":
        _check_suspensions(game, db)

    return event


@router.get("/{game_id}/events", response_model=list[GameEventOut])
def list_events(game_id: int, db: Session = Depends(get_db)):
    _get_game_or_404(game_id, db)
    events = (
        db.query(GameEvent)
        .filter(GameEvent.game_id == game_id)
        .order_by(GameEvent.minute, GameEvent.id)
        .all()
    )

    athlete_ids = {e.athlete_id for e in events if e.athlete_id}
    athletes: dict[int, str] = {}
    if athlete_ids:
        athletes = {
            a.id: a.name
            for a in db.query(Athlete).filter(Athlete.id.in_(athlete_ids)).all()
        }

    return [
        {
            "id": e.id,
            "game_id": e.game_id,
            "athlete_id": e.athlete_id,
            "athlete_name": athletes.get(e.athlete_id) if e.athlete_id else None,
            "team_id": e.team_id,
            "event_type": e.event_type,
            "minute": e.minute,
            "description": e.description,
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
# Suspensões automáticas
# ---------------------------------------------------------------------------

def _check_suspensions(game: Game, db: Session) -> None:
    """
    Verifica e cria suspensões automáticas após um resultado ou evento de cartão.

    Regras (configuráveis em championship.rules_config):
    - red_card      → suspension_games jogos de suspensão (default 1)
    - yellow_card   → suspensão a cada yellow_card_threshold amarelos (default 3)

    Usa tags no campo `reason` para idempotência.
    """
    champ            = game.championship
    rules            = champ.rules_config or {}
    yellow_threshold = rules.get("yellow_card_threshold", 3)
    suspend_games    = rules.get("suspension_games", 1)

    events = db.query(GameEvent).filter(GameEvent.game_id == game.id).all()

    # --- Cartões vermelhos ------------------------------------------------
    for ev in events:
        if ev.event_type != "red_card" or ev.athlete_id is None:
            continue

        tag = f"[red_card:game={game.id}:event={ev.id}]"
        already = (
            db.query(Suspension)
            .filter(
                Suspension.athlete_id == ev.athlete_id,
                Suspension.championship_id == champ.id,
                Suspension.reason.contains(tag),
            )
            .first()
        )
        if not already:
            db.add(Suspension(
                athlete_id=ev.athlete_id,
                championship_id=champ.id,
                games_remaining=suspend_games,
                reason=f"Cartão vermelho {tag}",
                auto_generated=True,
            ))

    # --- Acúmulo de cartões amarelos -------------------------------------
    athlete_yellows = (
        db.query(GameEvent.athlete_id, func.count(GameEvent.id).label("cnt"))
        .join(Game, Game.id == GameEvent.game_id)
        .filter(
            Game.championship_id == champ.id,
            GameEvent.event_type == "yellow_card",
            GameEvent.athlete_id.isnot(None),
        )
        .group_by(GameEvent.athlete_id)
        .all()
    )

    for athlete_id, cnt in athlete_yellows:
        if yellow_threshold > 0 and cnt % yellow_threshold == 0:
            tag = f"[yellow:{cnt}:champ={champ.id}]"
            already = (
                db.query(Suspension)
                .filter(
                    Suspension.athlete_id == athlete_id,
                    Suspension.championship_id == champ.id,
                    Suspension.reason.contains(tag),
                )
                .first()
            )
            if not already:
                db.add(Suspension(
                    athlete_id=athlete_id,
                    championship_id=champ.id,
                    games_remaining=suspend_games,
                    reason=f"Acúmulo de {cnt} cartões amarelos {tag}",
                    auto_generated=True,
                ))

    db.commit()
