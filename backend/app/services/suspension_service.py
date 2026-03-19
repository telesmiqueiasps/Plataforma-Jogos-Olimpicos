"""
services/suspension_service.py
================================
Lógica de suspensões automáticas por cartões.
"""

from sqlalchemy.orm import Session

from app.db.models import Athlete, Game, GameEvent, Suspension


def process_card_event(
    db: Session,
    athlete_id: int,
    championship_id: int,
    game_id: int,
    event_type: str,
    rules_config: dict,
):
    """
    Chamado ao registrar cartão amarelo ou vermelho.
    Gera suspensão automática se necessário.
    Retorna dict com info da suspensão criada ou None.
    """
    if event_type == "red_card":
        return _process_red_card(db, athlete_id, championship_id, game_id, rules_config)
    elif event_type == "yellow_card":
        return _process_yellow_card(db, athlete_id, championship_id, game_id, rules_config)
    return None


def _process_red_card(db, athlete_id, championship_id, game_id, rules_config):
    suspension_games = rules_config.get("red_card_suspension_games", 1)
    expulsion = rules_config.get("red_card_expulsion", False)
    if expulsion:
        suspension_games = 999  # expulsão do campeonato

    tag = f"[red:{game_id}:{athlete_id}]"
    existing = (
        db.query(Suspension)
        .filter(
            Suspension.athlete_id == athlete_id,
            Suspension.championship_id == championship_id,
            Suspension.reason.contains(tag),
        )
        .first()
    )
    if existing:
        return None

    suspension = Suspension(
        athlete_id=athlete_id,
        championship_id=championship_id,
        games_remaining=suspension_games,
        reason=f"Cartão vermelho {tag}",
        auto_generated=True,
    )
    db.add(suspension)
    db.commit()
    db.refresh(suspension)
    return {
        "type": "red_card",
        "suspension_games": suspension_games,
        "expulsion": expulsion,
        "suspension_id": suspension.id,
    }


def _process_yellow_card(db, athlete_id, championship_id, game_id, rules_config):
    threshold = rules_config.get("yellow_card_threshold", 3)
    suspension_games = rules_config.get("yellow_suspension_games", 1)
    if threshold <= 0:
        return None

    yellow_count = (
        db.query(GameEvent)
        .join(Game)
        .filter(
            Game.championship_id == championship_id,
            GameEvent.athlete_id == athlete_id,
            GameEvent.event_type == "yellow_card",
        )
        .count()
    )

    if yellow_count > 0 and yellow_count % threshold == 0:
        tag = f"[yellow:{yellow_count}:champ:{championship_id}]"
        existing = (
            db.query(Suspension)
            .filter(
                Suspension.athlete_id == athlete_id,
                Suspension.championship_id == championship_id,
                Suspension.reason.contains(tag),
            )
            .first()
        )
        if existing:
            return None

        suspension = Suspension(
            athlete_id=athlete_id,
            championship_id=championship_id,
            games_remaining=suspension_games,
            reason=f"Acúmulo de cartões amarelos ({yellow_count}) {tag}",
            auto_generated=True,
        )
        db.add(suspension)
        db.commit()
        db.refresh(suspension)
        return {
            "type": "yellow_card",
            "yellow_count": yellow_count,
            "suspension_games": suspension_games,
            "suspension_id": suspension.id,
        }
    return None


def is_athlete_suspended(db: Session, athlete_id: int, championship_id: int) -> bool:
    """Verifica se atleta tem suspensão ativa (games_remaining > 0)."""
    return (
        db.query(Suspension)
        .filter(
            Suspension.athlete_id == athlete_id,
            Suspension.championship_id == championship_id,
            Suspension.games_remaining > 0,
        )
        .first()
        is not None
    )


def get_athlete_suspension(db: Session, athlete_id: int, championship_id: int):
    """Retorna suspensão ativa do atleta ou None."""
    return (
        db.query(Suspension)
        .filter(
            Suspension.athlete_id == athlete_id,
            Suspension.championship_id == championship_id,
            Suspension.games_remaining > 0,
        )
        .first()
    )


def decrease_suspension_after_game(db: Session, athlete_id: int, championship_id: int):
    """Diminui games_remaining após atleta cumprir um jogo de suspensão."""
    suspension = get_athlete_suspension(db, athlete_id, championship_id)
    if suspension and suspension.games_remaining > 0 and suspension.games_remaining < 999:
        suspension.games_remaining -= 1
        db.commit()
