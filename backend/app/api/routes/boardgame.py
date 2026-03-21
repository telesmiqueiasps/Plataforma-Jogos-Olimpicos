"""
routes/boardgame.py
===================
Endpoints para modalidades de Jogos de Tabuleiro:
  - Dominó  (duplas)
  - Dama    (individual)
  - Xadrez  (individual)
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from app.db.models import (
    Athlete,
    BoardgameGame,
    BoardgameParticipant,
    Championship,
    DominoTeam,
    User,
)
from app.db.session import get_db
from app.services.chess_service import calculate_chess_standings

router = APIRouter(prefix="/championships", tags=["Tabuleiro"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_champ_or_404(championship_id: int, db: Session) -> Championship:
    c = db.query(Championship).filter(Championship.id == championship_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campeonato não encontrado")
    return c


def _domino_team_out(t: DominoTeam) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "player1_id": t.player1_id,
        "player1_name": t.player1.name if t.player1 else None,
        "player2_id": t.player2_id,
        "player2_name": t.player2.name if t.player2 else None,
    }


def _participant_out(p: BoardgameParticipant) -> dict:
    return {
        "id": p.id,
        "athlete_id": p.athlete_id,
        "athlete_name": p.athlete_name,
        "athlete_photo_url": p.athlete_photo_url,
        "game_type": p.game_type,
    }


def _boardgame_game_out(g: BoardgameGame, names: dict) -> dict:
    return {
        "id": g.id,
        "championship_id": g.championship_id,
        "game_type": g.game_type,
        "home_id": g.home_id,
        "away_id": g.away_id,
        "home_name": names.get(g.home_id, f"#{g.home_id}"),
        "away_name": names.get(g.away_id, f"#{g.away_id}"),
        "status": g.status,
        "phase": g.phase,
        "round_number": g.round_number,
        "scheduled_at": g.scheduled_at.isoformat() if g.scheduled_at else None,
        "extra_data": g.extra_data or {},
        "home_score": g.home_score,
        "away_score": g.away_score,
        "result": g.result,
    }


# ---------------------------------------------------------------------------
# DOMINÓ — Duplas
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/domino/teams")
def list_domino_teams(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    return [_domino_team_out(t) for t in teams]


@router.post("/{championship_id}/domino/teams", status_code=201)
def create_domino_team(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome da dupla é obrigatório")
    player1_id = body.get("player1_id")
    player2_id = body.get("player2_id")
    team = DominoTeam(
        championship_id=championship_id,
        name=name,
        player1_id=player1_id or None,
        player2_id=player2_id or None,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return _domino_team_out(team)


@router.delete("/{championship_id}/domino/teams/{team_id}", status_code=204)
def delete_domino_team(
    championship_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    team = db.query(DominoTeam).filter(
        DominoTeam.id == team_id,
        DominoTeam.championship_id == championship_id,
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Dupla não encontrada")
    db.delete(team)
    db.commit()


# ---------------------------------------------------------------------------
# DOMINÓ — Jogos
# ---------------------------------------------------------------------------

def _domino_names(championship_id: int, db: Session) -> dict:
    teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    return {t.id: t.name for t in teams}


@router.get("/{championship_id}/domino/games")
def list_domino_games(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
    ).order_by(BoardgameGame.round_number, BoardgameGame.id).all()
    names = _domino_names(championship_id, db)
    return [_boardgame_game_out(g, names) for g in games]


@router.post("/{championship_id}/domino/games", status_code=201)
def create_domino_game(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    home_id = body.get("home_id")
    away_id = body.get("away_id")
    if not home_id or not away_id:
        raise HTTPException(status_code=400, detail="home_id e away_id são obrigatórios")
    game = BoardgameGame(
        championship_id=championship_id,
        game_type="domino",
        home_id=home_id,
        away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "domino", "matches": []},
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    names = _domino_names(championship_id, db)
    return _boardgame_game_out(game, names)


@router.put("/{championship_id}/domino/games/{game_id}/match")
def register_domino_match(
    championship_id: int,
    game_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Registra uma partida individual dentro do jogo de dominó.
    Body: { match_number, winner: 'home'|'away'|'draw',
            match_type: 'batida_simples'|'batida_caroca'|'passe_simples'|'passe_geral',
            home_points, away_points }
    """
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    best_of = rules.get("best_of", 3)

    winner = body.get("winner")
    match_type = body.get("match_type", "batida_simples")
    home_pts = int(body.get("home_points", 0))
    away_pts = int(body.get("away_points", 0))
    match_num = int(body.get("match_number", 1))

    ed = dict(game.extra_data or {"game_type": "domino", "matches": []})
    matches = list(ed.get("matches", []))

    # Substitui ou adiciona partida
    idx = next((i for i, m in enumerate(matches) if m.get("match_number") == match_num), None)
    match_entry = {
        "match_number": match_num,
        "winner": winner,
        "match_type": match_type,
        "home_points": home_pts,
        "away_points": away_pts,
    }
    if idx is not None:
        matches[idx] = match_entry
    else:
        matches.append(match_entry)

    ed["matches"] = matches

    # Recalcula placar (partidas ganhas)
    home_wins = sum(1 for m in matches if m.get("winner") == "home")
    away_wins = sum(1 for m in matches if m.get("winner") == "away")
    needed = (best_of // 2) + 1

    result = None
    if home_wins >= needed:
        result = "home_win"
    elif away_wins >= needed:
        result = "away_win"

    game.extra_data = ed
    game.home_score = home_wins
    game.away_score = away_wins
    game.result = result
    if result:
        game.status = "finished"

    db.commit()
    db.refresh(game)
    names = _domino_names(championship_id, db)
    return _boardgame_game_out(game, names)


# ---------------------------------------------------------------------------
# DOMINÓ — Classificação
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/domino/standings")
def domino_standings(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    pts_win  = rules.get("pts_win",  3)
    pts_draw = rules.get("pts_draw", 1)
    pts_loss = rules.get("pts_loss", 0)

    teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.status == "finished",
    ).all()

    stats: dict[int, dict] = {
        t.id: {"id": t.id, "name": t.name, "j": 0, "v": 0, "e": 0, "d": 0, "pts": 0,
               "matches_won": 0, "matches_lost": 0}
        for t in teams
    }

    for g in games:
        for side_id, opp_id, result_key in [
            (g.home_id, g.away_id, g.result == "home_win"),
            (g.away_id, g.home_id, g.result == "away_win"),
        ]:
            if side_id not in stats:
                continue
            s = stats[side_id]
            s["j"] += 1
            won = (g.result == "home_win" and side_id == g.home_id) or \
                  (g.result == "away_win" and side_id == g.away_id)
            lost = (g.result == "home_win" and side_id == g.away_id) or \
                   (g.result == "away_win" and side_id == g.home_id)
            draw = g.result == "draw"
            if won:
                s["v"] += 1; s["pts"] += pts_win
                s["matches_won"] += (g.home_score if side_id == g.home_id else g.away_score) or 0
                s["matches_lost"] += (g.away_score if side_id == g.home_id else g.home_score) or 0
            elif lost:
                s["d"] += 1; s["pts"] += pts_loss
                s["matches_won"] += (g.home_score if side_id == g.home_id else g.away_score) or 0
                s["matches_lost"] += (g.away_score if side_id == g.home_id else g.home_score) or 0
            elif draw:
                s["e"] += 1; s["pts"] += pts_draw

    ranked = sorted(stats.values(), key=lambda x: (-x["pts"], -x["v"], -(x["matches_won"] - x["matches_lost"])))
    for i, r in enumerate(ranked):
        r["position"] = i + 1
    return ranked


# ---------------------------------------------------------------------------
# DAMA — Participantes
# ---------------------------------------------------------------------------

def _get_participants(championship_id: int, game_type: str, db: Session) -> list:
    return db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.game_type == game_type,
    ).all()


@router.get("/{championship_id}/dama/participants")
def list_dama_participants(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    parts = _get_participants(championship_id, "dama", db)
    return [_participant_out(p) for p in parts]


@router.post("/{championship_id}/dama/participants", status_code=201)
def add_dama_participant(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    athlete_id = body.get("athlete_id")
    if not athlete_id:
        raise HTTPException(status_code=400, detail="athlete_id é obrigatório")
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Atleta não encontrado")
    existing = db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.athlete_id == athlete_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Atleta já inscrito")
    p = BoardgameParticipant(championship_id=championship_id, athlete_id=athlete_id, game_type="dama")
    db.add(p)
    db.commit()
    db.refresh(p)
    return _participant_out(p)


@router.delete("/{championship_id}/dama/participants/{part_id}", status_code=204)
def remove_dama_participant(
    championship_id: int,
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    p = db.query(BoardgameParticipant).filter(
        BoardgameParticipant.id == part_id,
        BoardgameParticipant.championship_id == championship_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Participante não encontrado")
    db.delete(p)
    db.commit()


# ---------------------------------------------------------------------------
# DAMA — Jogos
# ---------------------------------------------------------------------------

def _athlete_names_for_game_type(championship_id: int, game_type: str, db: Session) -> dict:
    parts = _get_participants(championship_id, game_type, db)
    return {p.athlete_id: p.athlete_name for p in parts}


@router.get("/{championship_id}/dama/games")
def list_dama_games(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
    ).order_by(BoardgameGame.round_number, BoardgameGame.id).all()
    names = _athlete_names_for_game_type(championship_id, "dama", db)
    return [_boardgame_game_out(g, names) for g in games]


@router.post("/{championship_id}/dama/games", status_code=201)
def create_dama_game(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    home_id = body.get("home_id")
    away_id = body.get("away_id")
    if not home_id or not away_id:
        raise HTTPException(status_code=400, detail="home_id e away_id são obrigatórios")
    game = BoardgameGame(
        championship_id=championship_id,
        game_type="dama",
        home_id=home_id,
        away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "dama"},
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    names = _athlete_names_for_game_type(championship_id, "dama", db)
    return _boardgame_game_out(game, names)


@router.put("/{championship_id}/dama/games/{game_id}/result")
def register_dama_result(
    championship_id: int,
    game_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Body: { result: 'home_win'|'away_win'|'draw',
            home_pieces_captured, home_damas_captured,
            away_pieces_captured, away_damas_captured }
    """
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    pts_piece = rules.get("pts_piece", 1)
    pts_dama  = rules.get("pts_dama",  3)
    pts_draw_each = rules.get("pts_draw_each", 0)

    result = body.get("result")
    if result not in ("home_win", "away_win", "draw"):
        raise HTTPException(status_code=400, detail="result inválido")

    home_pieces = int(body.get("home_pieces_captured", 0))
    home_damas  = int(body.get("home_damas_captured",  0))
    away_pieces = int(body.get("away_pieces_captured", 0))
    away_damas  = int(body.get("away_damas_captured",  0))

    home_piece_pts = home_pieces * pts_piece + home_damas * pts_dama
    away_piece_pts = away_pieces * pts_piece + away_damas * pts_dama

    ed = {
        "game_type": "dama",
        "result": result,
        "home_pieces_captured": home_pieces,
        "home_damas_captured": home_damas,
        "away_pieces_captured": away_pieces,
        "away_damas_captured": away_damas,
        "home_piece_points": home_piece_pts,
        "away_piece_points": away_piece_pts,
    }

    # home_score/away_score = pontos de peças × 10 (para armazenar como inteiro)
    game.extra_data = ed
    game.result     = result
    game.home_score = home_piece_pts * 10
    game.away_score = away_piece_pts * 10
    game.status     = "finished"

    db.commit()
    db.refresh(game)
    names = _athlete_names_for_game_type(championship_id, "dama", db)
    return _boardgame_game_out(game, names)


# ---------------------------------------------------------------------------
# DAMA — Classificação
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/dama/standings")
def dama_standings(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    pts_win  = rules.get("pts_win",  3)
    pts_draw = rules.get("pts_draw", 1)
    pts_loss = rules.get("pts_loss", 0)

    parts = _get_participants(championship_id, "dama", db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
        BoardgameGame.status == "finished",
    ).all()

    stats: dict[int, dict] = {
        p.athlete_id: {
            "id": p.athlete_id, "name": p.athlete_name,
            "photo_url": p.athlete_photo_url,
            "j": 0, "v": 0, "e": 0, "d": 0,
            "pts": 0, "piece_pts": 0.0,
        }
        for p in parts
    }

    for g in games:
        ed = g.extra_data or {}
        for side_id in [g.home_id, g.away_id]:
            if side_id not in stats:
                continue
            s = stats[side_id]
            s["j"] += 1
            is_home = (side_id == g.home_id)
            won  = (g.result == "home_win" and is_home) or (g.result == "away_win" and not is_home)
            lost = (g.result == "away_win" and is_home) or (g.result == "home_win" and not is_home)
            draw = g.result == "draw"
            if won:   s["v"] += 1; s["pts"] += pts_win
            elif lost: s["d"] += 1; s["pts"] += pts_loss
            elif draw: s["e"] += 1; s["pts"] += pts_draw
            piece_key = "home_piece_points" if is_home else "away_piece_points"
            s["piece_pts"] += ed.get(piece_key, 0)

    ranked = sorted(stats.values(), key=lambda x: (-x["pts"], -x["v"], -x["piece_pts"]))
    for i, r in enumerate(ranked):
        r["position"] = i + 1
    return ranked


# ---------------------------------------------------------------------------
# XADREZ — Participantes
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/xadrez/participants")
def list_xadrez_participants(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    parts = _get_participants(championship_id, "xadrez", db)
    return [_participant_out(p) for p in parts]


@router.post("/{championship_id}/xadrez/participants", status_code=201)
def add_xadrez_participant(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    athlete_id = body.get("athlete_id")
    if not athlete_id:
        raise HTTPException(status_code=400, detail="athlete_id é obrigatório")
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Atleta não encontrado")
    existing = db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.athlete_id == athlete_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Atleta já inscrito")
    p = BoardgameParticipant(championship_id=championship_id, athlete_id=athlete_id, game_type="xadrez")
    db.add(p)
    db.commit()
    db.refresh(p)
    return _participant_out(p)


@router.delete("/{championship_id}/xadrez/participants/{part_id}", status_code=204)
def remove_xadrez_participant(
    championship_id: int,
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    p = db.query(BoardgameParticipant).filter(
        BoardgameParticipant.id == part_id,
        BoardgameParticipant.championship_id == championship_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Participante não encontrado")
    db.delete(p)
    db.commit()


# ---------------------------------------------------------------------------
# XADREZ — Jogos
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/xadrez/games")
def list_xadrez_games(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
    ).order_by(BoardgameGame.round_number, BoardgameGame.id).all()
    names = _athlete_names_for_game_type(championship_id, "xadrez", db)
    return [_boardgame_game_out(g, names) for g in games]


@router.post("/{championship_id}/xadrez/games", status_code=201)
def create_xadrez_game(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    home_id = body.get("home_id")
    away_id = body.get("away_id")
    if not home_id or not away_id:
        raise HTTPException(status_code=400, detail="home_id e away_id são obrigatórios")
    game = BoardgameGame(
        championship_id=championship_id,
        game_type="xadrez",
        home_id=home_id,
        away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "xadrez"},
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    names = _athlete_names_for_game_type(championship_id, "xadrez", db)
    return _boardgame_game_out(game, names)


@router.put("/{championship_id}/xadrez/games/{game_id}/result")
def register_xadrez_result(
    championship_id: int,
    game_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Body: { result: 'home_win'|'away_win'|'draw' }
    Pontuação: vitória=pts_win (def 10), empate=pts_draw (def 5), derrota=0
    home_score/away_score são armazenados ×10 (10=1pt, 5=0.5pt)
    """
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    result = body.get("result")
    if result not in ("home_win", "away_win", "draw"):
        raise HTTPException(status_code=400, detail="result inválido")

    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    pts_win  = int(rules.get("pts_win",  10))   # ×10: 1.0 pt
    pts_draw = int(rules.get("pts_draw",  5))   # ×10: 0.5 pt
    pts_loss = int(rules.get("pts_loss",  0))   # ×10: 0.0 pt

    if result == "home_win":
        home_s, away_s = pts_win, pts_loss
    elif result == "away_win":
        home_s, away_s = pts_loss, pts_win
    else:
        home_s = away_s = pts_draw

    game.extra_data = {"game_type": "xadrez", "result": result}
    game.result     = result
    game.home_score = home_s
    game.away_score = away_s
    game.status     = "finished"

    db.commit()
    db.refresh(game)
    names = _athlete_names_for_game_type(championship_id, "xadrez", db)
    return _boardgame_game_out(game, names)


# ---------------------------------------------------------------------------
# XADREZ — Classificação (com Buchholz)
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/xadrez/standings")
def xadrez_standings(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}

    parts = _get_participants(championship_id, "xadrez", db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
    ).all()

    participants = [
        {"id": p.athlete_id, "name": p.athlete_name, "photo_url": p.athlete_photo_url}
        for p in parts
    ]

    return calculate_chess_standings(games, participants, rules)


# ---------------------------------------------------------------------------
# DELETE genérico para boardgame games (domino / dama / xadrez)
# ---------------------------------------------------------------------------

@router.delete("/{championship_id}/domino/games/{game_id}", status_code=204)
def delete_domino_game(
    championship_id: int,
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    db.delete(game)
    db.commit()


@router.delete("/{championship_id}/dama/games/{game_id}", status_code=204)
def delete_dama_game(
    championship_id: int,
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    db.delete(game)
    db.commit()


@router.delete("/{championship_id}/xadrez/games/{game_id}", status_code=204)
def delete_xadrez_game(
    championship_id: int,
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    db.delete(game)
    db.commit()
