"""
routes/games.py
===============
Detalhe de jogo, registro de resultado e eventos.
Após registrar cartão, verifica suspensões automáticas via suspension_service.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from app.db.models import Athlete, Game, GameEvent, GameResult, Suspension, Team, User
from app.db.session import get_db
from app.schemas.game import (
    GameEventCreate,
    GameEventOut,
    GameOut,
    GameResultOut,
    GameResultUpdate,
    GameResultBody,
    GameUpdate,
)
from app.services import suspension_service

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
    data: GameResultBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Registra ou atualiza o resultado de um jogo e marca status como 'finished'.
    - Futsal: enviar home_score e away_score
    - Vôlei: enviar sets = [{home_points, away_points}, ...]
    """
    from app.services.volleyball_service import calculate_match_points

    game = _get_game_or_404(game_id, db)

    sport_slug = (
        game.championship.sport.slug
        if game.championship and game.championship.sport
        else None
    )

    if sport_slug == "volleyball":
        if not data.sets:
            raise HTTPException(status_code=400, detail="Para vôlei, envie 'sets' no body")

        finalize = data.finalize if data.finalize is not None else True
        home_score = sum(1 for s in data.sets if s.home_points > s.away_points)
        away_score = sum(1 for s in data.sets if s.away_points > s.home_points)

        best_of = int((game.championship.rules_config or {}).get("best_of", 5)) if game.championship else 5
        home_table_pts, away_table_pts = calculate_match_points(home_score, away_score, best_of)
        notes = data.notes

        # Salva sets detalhados e pontos de tabela no extra_data do jogo
        extra = dict(game.extra_data or {})
        extra["volleyball"] = {
            "sets": [
                {"home_points": s.home_points, "away_points": s.away_points}
                for s in data.sets
            ],
            "table_points": {"home": home_table_pts, "away": away_table_pts},
        }
        game.extra_data = extra

        if game.result:
            game.result.home_score = home_score
            game.result.away_score = away_score
            game.result.notes = notes
            game.result.updated_by = current_user.id
        else:
            result = GameResult(
                game_id=game_id,
                home_score=home_score,
                away_score=away_score,
                notes=notes,
                created_by=current_user.id,
            )
            db.add(result)
            game.result = result

        if finalize:
            game.status = "finished"
        elif game.status == "scheduled":
            game.status = "live"

        db.commit()
        db.refresh(game)

        if finalize:
            _check_suspensions(game, db)

        return game.result

    else:
        if data.home_score is None or data.away_score is None:
            raise HTTPException(status_code=400, detail="Informe home_score e away_score")
        home_score = data.home_score
        away_score = data.away_score
        notes = data.notes

        if game.result:
            game.result.home_score = home_score
            game.result.away_score = away_score
            game.result.notes = notes
            game.result.updated_by = current_user.id
        else:
            result = GameResult(
                game_id=game_id,
                home_score=home_score,
                away_score=away_score,
                notes=notes,
                created_by=current_user.id,
            )
            db.add(result)
            game.result = result

        game.status = "finished"
        db.commit()
        db.refresh(game)

        # Verificar suspensões automáticas por acúmulo de amarelos ao fechar jogo
        _check_suspensions(game, db)

        return game.result


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@router.post("/{game_id}/events", status_code=201)
def add_event(
    game_id: int,
    data: GameEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Registra evento. Para cartões, processa suspensão automática via suspension_service.
    Retorna: { event: GameEventOut, suspension: dict | null }
    """
    game = _get_game_or_404(game_id, db)
    event = GameEvent(**data.model_dump(), game_id=game_id, created_by=current_user.id)
    db.add(event)
    db.commit()
    db.refresh(event)

    susp_info = None
    if data.event_type in ("yellow_card", "red_card") and data.athlete_id:
        champ = game.championship
        rules = champ.rules_config or {}
        result = suspension_service.process_card_event(
            db=db,
            athlete_id=data.athlete_id,
            championship_id=champ.id,
            game_id=game_id,
            event_type=data.event_type,
            rules_config=rules,
        )
        if result:
            athlete = db.query(Athlete).filter(Athlete.id == data.athlete_id).first()
            athlete_name = athlete.name if athlete else f"Atleta #{data.athlete_id}"
            if result["type"] == "red_card" and result.get("expulsion"):
                msg = f"🚫 {athlete_name} está EXPULSO do campeonato!"
            elif result["type"] == "red_card":
                n = result["suspension_games"]
                msg = f"🟥 Cartão vermelho! {athlete_name} suspenso para o{'s próximos' if n > 1 else ' próximo'} {n} jogo{'s' if n > 1 else ''}."
            else:
                n = result["yellow_count"]
                sg = result["suspension_games"]
                msg = f"🟨 {athlete_name} atingiu {n} cartões amarelos e está suspenso para o próximo jogo!"
            susp_info = {**result, "message": msg}

    # Montar resposta do evento com nomes
    athlete_name = None
    team_name = None
    if event.athlete_id:
        a = db.query(Athlete).filter(Athlete.id == event.athlete_id).first()
        athlete_name = a.name if a else None
    if event.team_id:
        t = db.query(Team).filter(Team.id == event.team_id).first()
        team_name = t.name if t else None

    event_out = {
        "id": event.id,
        "game_id": event.game_id,
        "athlete_id": event.athlete_id,
        "athlete_name": athlete_name,
        "team_id": event.team_id,
        "team_name": team_name,
        "event_type": event.event_type,
        "minute": event.minute,
        "description": event.description,
        "created_by_name": current_user.name,
    }

    return {"event": event_out, "suspension": susp_info}


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

    team_ids = {e.team_id for e in events if e.team_id}
    teams: dict[int, str] = {}
    if team_ids:
        teams = {
            t.id: t.name
            for t in db.query(Team).filter(Team.id.in_(team_ids)).all()
        }

    creator_ids = {e.created_by for e in events if e.created_by}
    creators: dict[int, str] = {}
    if creator_ids:
        creators = {
            u.id: u.name
            for u in db.query(User).filter(User.id.in_(creator_ids)).all()
        }

    return [
        {
            "id": e.id,
            "game_id": e.game_id,
            "athlete_id": e.athlete_id,
            "athlete_name": athletes.get(e.athlete_id) if e.athlete_id else None,
            "team_id": e.team_id,
            "team_name": teams.get(e.team_id) if e.team_id else None,
            "event_type": e.event_type,
            "minute": e.minute,
            "description": e.description,
            "created_by_name": creators.get(e.created_by) if e.created_by else None,
        }
        for e in events
    ]


# ---------------------------------------------------------------------------
# Suspensões automáticas (acúmulo de amarelos ao finalizar jogo)
# ---------------------------------------------------------------------------

def _check_suspensions(game: Game, db: Session) -> None:
    """
    Verifica acúmulo de cartões amarelos ao encerrar um jogo.
    Cartões vermelhos geram suspensão imediata via process_card_event no add_event.
    """
    champ            = game.championship
    rules            = champ.rules_config or {}
    yellow_threshold = rules.get("yellow_card_threshold", 3)
    suspend_games    = rules.get("yellow_suspension_games", rules.get("suspension_games", 1))

    if yellow_threshold <= 0:
        return

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
        if cnt % yellow_threshold == 0:
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
