"""
routes/boardgame.py
===================
Endpoints para modalidades de Jogos de Tabuleiro:
  - Dominó  (duplas)
  - Dama    (individual)
  - Xadrez  (individual)
"""

import random
from itertools import combinations

from fastapi import APIRouter, Depends, HTTPException
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

_GROUP_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


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
    ed = g.extra_data or {}
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
        "group": ed.get("group"),
        "round_number": g.round_number,
        "scheduled_at": g.scheduled_at.isoformat() if g.scheduled_at else None,
        "extra_data": ed,
        "home_score": g.home_score,
        "away_score": g.away_score,
        "result": g.result,
    }


def _domino_names(championship_id: int, db: Session) -> dict:
    teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    return {t.id: t.name for t in teams}


def _get_participants(championship_id: int, game_type: str, db: Session) -> list:
    return db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.game_type == game_type,
    ).all()


def _athlete_names_for_game_type(championship_id: int, game_type: str, db: Session) -> dict:
    parts = _get_participants(championship_id, game_type, db)
    return {p.athlete_id: p.athlete_name for p in parts}


# ── Dominó: cálculo de pontos por tipo de partida ──────────────────────────

def _calc_domino_match_points(match_type: str, quantidade_passes: int, rules: dict) -> int:
    if match_type == "batida_simples":
        return int(rules.get("pts_batida_simples", 1))
    elif match_type == "batida_caroca":
        return int(rules.get("pts_batida_caroca", 2))
    elif match_type == "passe_simples":
        return int(rules.get("pts_passe_simples", 1)) * max(1, int(quantidade_passes or 1))
    elif match_type == "passe_geral":
        return int(rules.get("pts_passe_geral", 2))
    return 0


def _compute_domino_standings_for_games(teams: list, games: list) -> list:
    """Classifica por pontos acumulados de tabela (batidas + passes), depois por vitórias."""
    stats: dict[int, dict] = {
        t.id: {"id": t.id, "name": t.name, "j": 0, "v": 0, "d": 0,
               "table_pts": 0, "matches_won": 0, "matches_lost": 0}
        for t in teams
    }
    for g in games:
        if g.status != "finished":
            continue
        ed = g.extra_data or {}
        home_tp = int(ed.get("home_table_points", 0) or 0)
        away_tp = int(ed.get("away_table_points", 0) or 0)
        for side_id, side_tp, side_wins, opp_wins in [
            (g.home_id, home_tp, g.home_score or 0, g.away_score or 0),
            (g.away_id, away_tp, g.away_score or 0, g.home_score or 0),
        ]:
            if side_id not in stats:
                continue
            s = stats[side_id]
            s["j"] += 1
            won = (g.result == "home_win" and side_id == g.home_id) or \
                  (g.result == "away_win" and side_id == g.away_id)
            if won:
                s["v"] += 1
            else:
                s["d"] += 1
            s["table_pts"] += side_tp
            s["matches_won"] += side_wins
            s["matches_lost"] += opp_wins
    ranked = sorted(
        stats.values(),
        key=lambda x: (-x["table_pts"], -x["v"], -(x["matches_won"] - x["matches_lost"]))
    )
    for i, r in enumerate(ranked):
        r["position"] = i + 1
    return ranked


def _compute_dama_standings_for_games(parts: list, games: list, rules: dict) -> list:
    """Classifica por pontos acumulados (peças capturadas + pts_empate em caso de empate)."""
    pts_empate = float(rules.get("pts_empate", 0.5))
    stats: dict[int, dict] = {
        p.athlete_id: {
            "id": p.athlete_id, "name": p.athlete_name,
            "photo_url": p.athlete_photo_url,
            "j": 0, "v": 0, "e": 0, "d": 0, "piece_pts": 0.0, "total_pts": 0.0,
        }
        for p in parts
    }
    for g in games:
        if g.status != "finished":
            continue
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
            if won:    s["v"] += 1
            elif lost: s["d"] += 1
            elif draw: s["e"] += 1; s["total_pts"] += pts_empate
            piece_key = "home_piece_points" if is_home else "away_piece_points"
            pp = float(ed.get(piece_key, 0) or 0)
            s["piece_pts"] += pp
            s["total_pts"]  += pp
    ranked = sorted(stats.values(), key=lambda x: (-x["total_pts"], -x["v"], -x["piece_pts"]))
    for i, r in enumerate(ranked):
        r["position"] = i + 1
    return ranked


def _resolve_position_label(label: str, groups_data: list) -> int | None:
    """Resolve '1A', '2B' etc. para entity ID (team_id ou athlete_id)."""
    try:
        pos = int(label[:-1])
        group_letter = label[-1].upper()
    except (ValueError, IndexError):
        return None
    for gd in groups_data:
        if gd["group"] == group_letter:
            standings = gd.get("standings", [])
            if pos <= len(standings):
                return standings[pos - 1]["id"]
    return None


# ===========================================================================
# DOMINÓ — Duplas
# ===========================================================================

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
    team = DominoTeam(
        championship_id=championship_id,
        name=name,
        player1_id=body.get("player1_id") or None,
        player2_id=body.get("player2_id") or None,
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


# ===========================================================================
# DOMINÓ — Jogos
# ===========================================================================

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
    group = body.get("group")
    game = BoardgameGame(
        championship_id=championship_id,
        game_type="domino",
        home_id=home_id,
        away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "domino", "matches": [], "group": group,
                    "home_table_points": 0, "away_table_points": 0},
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
    Body: { match_number, winner: 'home'|'away',
            match_type: 'batida_simples'|'batida_caroca'|'passe_simples'|'passe_geral',
            quantidade_passes: int (para passe_simples) }
    Pontos calculados automaticamente pelas regras do campeonato.
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
    best_of = int(rules.get("best_of", 3))

    winner = body.get("winner")
    if winner not in ("home", "away"):
        raise HTTPException(status_code=400, detail="winner deve ser 'home' ou 'away'")

    match_type = body.get("match_type", "batida_simples")
    quantidade_passes = int(body.get("quantidade_passes", 1) or 1)
    match_num = int(body.get("match_number", 1))

    pts = _calc_domino_match_points(match_type, quantidade_passes, rules)

    ed = dict(game.extra_data or {"game_type": "domino", "matches": [],
                                   "home_table_points": 0, "away_table_points": 0})
    matches = list(ed.get("matches", []))

    idx = next((i for i, m in enumerate(matches) if m.get("match_number") == match_num), None)
    match_entry = {
        "match_number": match_num,
        "winner": winner,
        "match_type": match_type,
        "quantidade_passes": quantidade_passes,
        "points": pts,
    }
    if idx is not None:
        matches[idx] = match_entry
    else:
        matches.append(match_entry)

    ed["matches"] = matches

    home_wins   = sum(1 for m in matches if m.get("winner") == "home")
    away_wins   = sum(1 for m in matches if m.get("winner") == "away")
    home_tp     = sum(m.get("points", 0) for m in matches if m.get("winner") == "home")
    away_tp     = sum(m.get("points", 0) for m in matches if m.get("winner") == "away")

    ed["home_table_points"] = home_tp
    ed["away_table_points"] = away_tp

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


# ===========================================================================
# DOMINÓ — Grupos
# ===========================================================================

@router.post("/{championship_id}/domino/groups/draw", status_code=201)
def domino_draw_groups(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Body: { group_count: int } — sorteia duplas aleatoriamente nos grupos."""
    champ = _get_champ_or_404(championship_id, db)
    group_count = int(body.get("group_count", 2))
    if group_count < 1:
        raise HTTPException(status_code=400, detail="group_count deve ser >= 1")
    teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    if not teams:
        raise HTTPException(status_code=400, detail="Cadastre as duplas antes de sortear grupos")
    shuffled = list(teams)
    random.shuffle(shuffled)
    groups: dict[str, list[int]] = {}
    for i, team in enumerate(shuffled):
        letter = _GROUP_LETTERS[i % group_count]
        groups.setdefault(letter, []).append(team.id)
    ed = dict(champ.extra_data or {})
    ed["domino_groups"] = groups
    champ.extra_data = ed
    db.commit()
    return _domino_groups_response(championship_id, champ, db)


@router.get("/{championship_id}/domino/groups")
def domino_list_groups(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    return _domino_groups_response(championship_id, champ, db)


def _domino_groups_response(championship_id: int, champ: Championship, db: Session) -> list:
    raw_groups = (champ.extra_data or {}).get("domino_groups", {})
    if not raw_groups:
        return []
    all_teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    teams_by_id = {t.id: t for t in all_teams}
    names = {t.id: t.name for t in all_teams}
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.phase == "groups",
    ).all()
    result = []
    for letter in sorted(raw_groups.keys()):
        team_ids = raw_groups[letter]
        group_teams = [teams_by_id[tid] for tid in team_ids if tid in teams_by_id]
        group_games = [g for g in all_games if (g.extra_data or {}).get("group") == letter]
        standings = _compute_domino_standings_for_games(group_teams, group_games)
        result.append({
            "group": letter,
            "teams": [_domino_team_out(t) for t in group_teams],
            "standings": standings,
            "games": [_boardgame_game_out(g, names) for g in group_games],
        })
    return result


@router.post("/{championship_id}/domino/groups/{group}/games/generate", status_code=201)
def domino_generate_group_games(
    championship_id: int,
    group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Gera jogos round-robin entre todas as duplas do grupo."""
    champ = _get_champ_or_404(championship_id, db)
    group = group.upper()
    raw_groups = (champ.extra_data or {}).get("domino_groups", {})
    if group not in raw_groups:
        raise HTTPException(status_code=404, detail=f"Grupo {group} não encontrado")
    team_ids = raw_groups[group]
    names = _domino_names(championship_id, db)
    for rn, (home_id, away_id) in enumerate(combinations(team_ids, 2), start=1):
        game = BoardgameGame(
            championship_id=championship_id,
            game_type="domino",
            home_id=home_id,
            away_id=away_id,
            phase="groups",
            round_number=rn,
            extra_data={"game_type": "domino", "matches": [], "group": group,
                        "home_table_points": 0, "away_table_points": 0},
        )
        db.add(game)
    db.commit()
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.phase == "groups",
    ).all()
    return [_boardgame_game_out(g, names) for g in all_games
            if (g.extra_data or {}).get("group") == group]


# ===========================================================================
# DOMINÓ — Mata-mata
# ===========================================================================

@router.post("/{championship_id}/domino/knockout/setup", status_code=201)
def domino_knockout_setup(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Body: { matches: [{ home: '1A', away: '2B' }, ...] }"""
    champ = _get_champ_or_404(championship_id, db)
    matches = body.get("matches", [])
    ed = dict(champ.extra_data or {})
    ed["domino_knockout_setup"] = matches
    champ.extra_data = ed
    db.commit()
    return {"matches": matches}


@router.post("/{championship_id}/domino/knockout/generate", status_code=201)
def domino_knockout_generate(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    setup = (champ.extra_data or {}).get("domino_knockout_setup", [])
    if not setup:
        raise HTTPException(status_code=400, detail="Configure os cruzamentos antes de gerar")
    groups_data = _domino_groups_response(championship_id, champ, db)
    names = _domino_names(championship_id, db)
    for match in setup:
        home_id = _resolve_position_label(match.get("home", ""), groups_data)
        away_id = _resolve_position_label(match.get("away", ""), groups_data)
        if not home_id or not away_id:
            continue
        game = BoardgameGame(
            championship_id=championship_id,
            game_type="domino",
            home_id=home_id,
            away_id=away_id,
            phase="knockout",
            round_number=1,
            extra_data={"game_type": "domino", "matches": [],
                        "home_table_points": 0, "away_table_points": 0, "ko_round": 1},
        )
        db.add(game)
    db.commit()
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.phase == "knockout",
    ).all()
    return [_boardgame_game_out(g, names) for g in ko_games]


@router.post("/{championship_id}/domino/knockout/advance", status_code=201)
def domino_knockout_advance(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Pega vencedores da rodada atual e gera a próxima."""
    _get_champ_or_404(championship_id, db)
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.phase == "knockout",
    ).order_by(BoardgameGame.round_number.desc()).all()
    if not ko_games:
        raise HTTPException(status_code=400, detail="Nenhum jogo de mata-mata encontrado")
    current_round = ko_games[0].round_number or 1
    current_games = [g for g in ko_games if g.round_number == current_round]
    if any(g.status != "finished" for g in current_games):
        raise HTTPException(status_code=400, detail="Nem todos os jogos da rodada foram concluídos")
    winners = [
        g.home_id if g.result == "home_win" else g.away_id
        for g in current_games if g.result in ("home_win", "away_win")
    ]
    if len(winners) < 2:
        raise HTTPException(status_code=400, detail="Não há duplas suficientes para a próxima fase")
    names = _domino_names(championship_id, db)
    next_round = current_round + 1
    for i in range(0, len(winners) - 1, 2):
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="domino",
            home_id=winners[i], away_id=winners[i + 1],
            phase="knockout", round_number=next_round,
            extra_data={"game_type": "domino", "matches": [],
                        "home_table_points": 0, "away_table_points": 0, "ko_round": next_round},
        ))
    db.commit()
    new_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.phase == "knockout",
        BoardgameGame.round_number == next_round,
    ).all()
    return [_boardgame_game_out(g, names) for g in new_games]


# ===========================================================================
# DOMINÓ — Classificação
# ===========================================================================

@router.get("/{championship_id}/domino/standings")
def domino_standings(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    teams = db.query(DominoTeam).filter(DominoTeam.championship_id == championship_id).all()
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "domino",
        BoardgameGame.status == "finished",
    ).all()
    return _compute_domino_standings_for_games(teams, games)


# ===========================================================================
# DAMA — Participantes
# ===========================================================================

@router.get("/{championship_id}/dama/participants")
def list_dama_participants(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    return [_participant_out(p) for p in _get_participants(championship_id, "dama", db)]


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
    if not db.query(Athlete).filter(Athlete.id == athlete_id).first():
        raise HTTPException(status_code=404, detail="Atleta não encontrado")
    if db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.athlete_id == athlete_id,
    ).first():
        raise HTTPException(status_code=400, detail="Atleta já inscrito")
    p = BoardgameParticipant(championship_id=championship_id, athlete_id=athlete_id, game_type="dama")
    db.add(p)
    db.commit()
    db.refresh(p)
    return _participant_out(p)


@router.delete("/{championship_id}/dama/participants/{part_id}", status_code=204)
def remove_dama_participant(
    championship_id: int, part_id: int,
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


# ===========================================================================
# DAMA — Jogos
# ===========================================================================

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
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    home_id = body.get("home_id")
    away_id = body.get("away_id")
    if not home_id or not away_id:
        raise HTTPException(status_code=400, detail="home_id e away_id são obrigatórios")
    group = body.get("group")
    game = BoardgameGame(
        championship_id=championship_id, game_type="dama",
        home_id=home_id, away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "dama", "group": group},
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return _boardgame_game_out(game, _athlete_names_for_game_type(championship_id, "dama", db))


@router.put("/{championship_id}/dama/games/{game_id}/result")
def register_dama_result(
    championship_id: int, game_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Body: { result: 'home_win'|'away_win'|'draw',
            home_pieces_captured, home_damas_captured,
            away_pieces_captured, away_damas_captured }
    Em caso de draw, pts_empate é adicionado a ambos.
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
    # Suporta tanto o nome antigo (pts_piece/pts_dama) quanto o novo (pts_peca_simples/pts_dama_capturada)
    pts_peca    = float(rules.get("pts_peca_simples", rules.get("pts_piece", 1)))
    pts_dama_c  = float(rules.get("pts_dama_capturada", rules.get("pts_dama", 3)))
    pts_empate  = float(rules.get("pts_empate", 0.5))

    result = body.get("result")
    if result not in ("home_win", "away_win", "draw"):
        raise HTTPException(status_code=400, detail="result inválido")

    home_pieces = int(body.get("home_pieces_captured", 0))
    home_damas  = int(body.get("home_damas_captured",  0))
    away_pieces = int(body.get("away_pieces_captured", 0))
    away_damas  = int(body.get("away_damas_captured",  0))

    home_pp = home_pieces * pts_peca + home_damas * pts_dama_c
    away_pp = away_pieces * pts_peca + away_damas * pts_dama_c
    if result == "draw":
        home_pp += pts_empate
        away_pp += pts_empate

    prev_ed = game.extra_data or {}
    game.extra_data = {
        **prev_ed,
        "game_type": "dama", "result": result,
        "home_pieces_captured": home_pieces, "home_damas_captured": home_damas,
        "away_pieces_captured": away_pieces, "away_damas_captured": away_damas,
        "home_piece_points": home_pp, "away_piece_points": away_pp,
    }
    game.result     = result
    game.home_score = int(home_pp * 10)
    game.away_score = int(away_pp * 10)
    game.status     = "finished"
    db.commit()
    db.refresh(game)
    return _boardgame_game_out(game, _athlete_names_for_game_type(championship_id, "dama", db))


# ===========================================================================
# DAMA — Grupos
# ===========================================================================

@router.post("/{championship_id}/dama/groups/draw", status_code=201)
def dama_draw_groups(
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    group_count = int(body.get("group_count", 2))
    if group_count < 1:
        raise HTTPException(status_code=400, detail="group_count deve ser >= 1")
    parts = _get_participants(championship_id, "dama", db)
    if not parts:
        raise HTTPException(status_code=400, detail="Inscreva participantes antes de sortear grupos")
    shuffled = list(parts)
    random.shuffle(shuffled)
    groups: dict[str, list[int]] = {}
    for i, p in enumerate(shuffled):
        groups.setdefault(_GROUP_LETTERS[i % group_count], []).append(p.athlete_id)
    ed = dict(champ.extra_data or {})
    ed["dama_groups"] = groups
    champ.extra_data = ed
    db.commit()
    return _dama_groups_response(championship_id, champ, db)


@router.get("/{championship_id}/dama/groups")
def dama_list_groups(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    return _dama_groups_response(championship_id, champ, db)


def _dama_groups_response(championship_id: int, champ: Championship, db: Session) -> list:
    raw_groups = (champ.extra_data or {}).get("dama_groups", {})
    if not raw_groups:
        return []
    rules = champ.rules_config or {}
    all_parts = _get_participants(championship_id, "dama", db)
    parts_by_id = {p.athlete_id: p for p in all_parts}
    names = {p.athlete_id: p.athlete_name for p in all_parts}
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
        BoardgameGame.phase == "groups",
    ).all()
    result = []
    for letter in sorted(raw_groups.keys()):
        athlete_ids = raw_groups[letter]
        group_parts = [parts_by_id[aid] for aid in athlete_ids if aid in parts_by_id]
        group_games = [g for g in all_games if (g.extra_data or {}).get("group") == letter]
        standings = _compute_dama_standings_for_games(group_parts, group_games, rules)
        result.append({
            "group": letter,
            "participants": [_participant_out(p) for p in group_parts],
            "standings": standings,
            "games": [_boardgame_game_out(g, names) for g in group_games],
        })
    return result


@router.post("/{championship_id}/dama/groups/{group}/games/generate", status_code=201)
def dama_generate_group_games(
    championship_id: int, group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    group = group.upper()
    raw_groups = (champ.extra_data or {}).get("dama_groups", {})
    if group not in raw_groups:
        raise HTTPException(status_code=404, detail=f"Grupo {group} não encontrado")
    athlete_ids = raw_groups[group]
    names = _athlete_names_for_game_type(championship_id, "dama", db)
    for rn, (home_id, away_id) in enumerate(combinations(athlete_ids, 2), start=1):
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="dama",
            home_id=home_id, away_id=away_id,
            phase="groups", round_number=rn,
            extra_data={"game_type": "dama", "group": group},
        ))
    db.commit()
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama", BoardgameGame.phase == "groups",
    ).all()
    return [_boardgame_game_out(g, names) for g in all_games
            if (g.extra_data or {}).get("group") == group]


# ===========================================================================
# DAMA — Mata-mata
# ===========================================================================

@router.post("/{championship_id}/dama/knockout/setup", status_code=201)
def dama_knockout_setup(
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    matches = body.get("matches", [])
    ed = dict(champ.extra_data or {})
    ed["dama_knockout_setup"] = matches
    champ.extra_data = ed
    db.commit()
    return {"matches": matches}


@router.post("/{championship_id}/dama/knockout/generate", status_code=201)
def dama_knockout_generate(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    setup = (champ.extra_data or {}).get("dama_knockout_setup", [])
    if not setup:
        raise HTTPException(status_code=400, detail="Configure os cruzamentos antes de gerar")
    groups_data = _dama_groups_response(championship_id, champ, db)
    names = _athlete_names_for_game_type(championship_id, "dama", db)
    for match in setup:
        home_id = _resolve_position_label(match.get("home", ""), groups_data)
        away_id = _resolve_position_label(match.get("away", ""), groups_data)
        if not home_id or not away_id:
            continue
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="dama",
            home_id=home_id, away_id=away_id,
            phase="knockout", round_number=1,
            extra_data={"game_type": "dama", "ko_round": 1},
        ))
    db.commit()
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama", BoardgameGame.phase == "knockout",
    ).all()
    return [_boardgame_game_out(g, names) for g in ko_games]


@router.post("/{championship_id}/dama/knockout/advance", status_code=201)
def dama_knockout_advance(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
        BoardgameGame.phase == "knockout",
    ).order_by(BoardgameGame.round_number.desc()).all()
    if not ko_games:
        raise HTTPException(status_code=400, detail="Nenhum jogo de mata-mata encontrado")
    current_round = ko_games[0].round_number or 1
    current_games = [g for g in ko_games if g.round_number == current_round]
    if any(g.status != "finished" for g in current_games):
        raise HTTPException(status_code=400, detail="Nem todos os jogos da rodada foram concluídos")
    winners = [
        g.home_id if g.result == "home_win" else g.away_id
        for g in current_games if g.result in ("home_win", "away_win")
    ]
    if len(winners) < 2:
        raise HTTPException(status_code=400, detail="Não há jogadores suficientes para a próxima fase")
    names = _athlete_names_for_game_type(championship_id, "dama", db)
    next_round = current_round + 1
    for i in range(0, len(winners) - 1, 2):
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="dama",
            home_id=winners[i], away_id=winners[i + 1],
            phase="knockout", round_number=next_round,
            extra_data={"game_type": "dama", "ko_round": next_round},
        ))
    db.commit()
    new_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
        BoardgameGame.phase == "knockout",
        BoardgameGame.round_number == next_round,
    ).all()
    return [_boardgame_game_out(g, names) for g in new_games]


# ===========================================================================
# DAMA — Classificação
# ===========================================================================

@router.get("/{championship_id}/dama/standings")
def dama_standings(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    parts = _get_participants(championship_id, "dama", db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "dama",
        BoardgameGame.status == "finished",
    ).all()
    return _compute_dama_standings_for_games(parts, games, rules)


# ===========================================================================
# XADREZ — Participantes
# ===========================================================================

@router.get("/{championship_id}/xadrez/participants")
def list_xadrez_participants(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    return [_participant_out(p) for p in _get_participants(championship_id, "xadrez", db)]


@router.post("/{championship_id}/xadrez/participants", status_code=201)
def add_xadrez_participant(
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    athlete_id = body.get("athlete_id")
    if not athlete_id:
        raise HTTPException(status_code=400, detail="athlete_id é obrigatório")
    if not db.query(Athlete).filter(Athlete.id == athlete_id).first():
        raise HTTPException(status_code=404, detail="Atleta não encontrado")
    if db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.athlete_id == athlete_id,
    ).first():
        raise HTTPException(status_code=400, detail="Atleta já inscrito")
    p = BoardgameParticipant(championship_id=championship_id, athlete_id=athlete_id, game_type="xadrez")
    db.add(p)
    db.commit()
    db.refresh(p)
    return _participant_out(p)


@router.delete("/{championship_id}/xadrez/participants/{part_id}", status_code=204)
def remove_xadrez_participant(
    championship_id: int, part_id: int,
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


# ===========================================================================
# XADREZ — Jogos
# ===========================================================================

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
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    home_id = body.get("home_id")
    away_id = body.get("away_id")
    if not home_id or not away_id:
        raise HTTPException(status_code=400, detail="home_id e away_id são obrigatórios")
    group = body.get("group")
    game = BoardgameGame(
        championship_id=championship_id, game_type="xadrez",
        home_id=home_id, away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "xadrez", "group": group},
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return _boardgame_game_out(game, _athlete_names_for_game_type(championship_id, "xadrez", db))


@router.put("/{championship_id}/xadrez/games/{game_id}/result")
def register_xadrez_result(
    championship_id: int, game_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Body: { result: 'home_win'|'away_win'|'draw' }
    Pontuação armazenada ×10 (10=1pt, 5=0.5pt, 0=0pt).
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
    pts_win  = int(rules.get("pts_win",  10))
    pts_draw = int(rules.get("pts_draw",  5))
    pts_loss = int(rules.get("pts_loss",  0))

    if result == "home_win":
        home_s, away_s = pts_win, pts_loss
    elif result == "away_win":
        home_s, away_s = pts_loss, pts_win
    else:
        home_s = away_s = pts_draw

    prev_ed = game.extra_data or {}
    game.extra_data = {**prev_ed, "game_type": "xadrez", "result": result}
    game.result     = result
    game.home_score = home_s
    game.away_score = away_s
    game.status     = "finished"
    db.commit()
    db.refresh(game)
    return _boardgame_game_out(game, _athlete_names_for_game_type(championship_id, "xadrez", db))


# ===========================================================================
# XADREZ — Grupos
# ===========================================================================

@router.post("/{championship_id}/xadrez/groups/draw", status_code=201)
def xadrez_draw_groups(
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    group_count = int(body.get("group_count", 2))
    if group_count < 1:
        raise HTTPException(status_code=400, detail="group_count deve ser >= 1")
    parts = _get_participants(championship_id, "xadrez", db)
    if not parts:
        raise HTTPException(status_code=400, detail="Inscreva participantes antes de sortear grupos")
    shuffled = list(parts)
    random.shuffle(shuffled)
    groups: dict[str, list[int]] = {}
    for i, p in enumerate(shuffled):
        groups.setdefault(_GROUP_LETTERS[i % group_count], []).append(p.athlete_id)
    ed = dict(champ.extra_data or {})
    ed["xadrez_groups"] = groups
    champ.extra_data = ed
    db.commit()
    return _xadrez_groups_response(championship_id, champ, db)


@router.get("/{championship_id}/xadrez/groups")
def xadrez_list_groups(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    champ = _get_champ_or_404(championship_id, db)
    return _xadrez_groups_response(championship_id, champ, db)


def _xadrez_groups_response(championship_id: int, champ: Championship, db: Session) -> list:
    raw_groups = (champ.extra_data or {}).get("xadrez_groups", {})
    if not raw_groups:
        return []
    rules = champ.rules_config or {}
    all_parts = _get_participants(championship_id, "xadrez", db)
    parts_by_id = {p.athlete_id: p for p in all_parts}
    names = {p.athlete_id: p.athlete_name for p in all_parts}
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
        BoardgameGame.phase == "groups",
    ).all()
    result = []
    for letter in sorted(raw_groups.keys()):
        athlete_ids = raw_groups[letter]
        group_parts = [parts_by_id[aid] for aid in athlete_ids if aid in parts_by_id]
        group_games = [g for g in all_games if (g.extra_data or {}).get("group") == letter]
        participants_list = [
            {"id": p.athlete_id, "name": p.athlete_name, "photo_url": p.athlete_photo_url}
            for p in group_parts
        ]
        standings = calculate_chess_standings(group_games, participants_list, rules)
        result.append({
            "group": letter,
            "participants": [_participant_out(p) for p in group_parts],
            "standings": standings,
            "games": [_boardgame_game_out(g, names) for g in group_games],
        })
    return result


@router.post("/{championship_id}/xadrez/groups/{group}/games/generate", status_code=201)
def xadrez_generate_group_games(
    championship_id: int, group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    group = group.upper()
    raw_groups = (champ.extra_data or {}).get("xadrez_groups", {})
    if group not in raw_groups:
        raise HTTPException(status_code=404, detail=f"Grupo {group} não encontrado")
    athlete_ids = raw_groups[group]
    names = _athlete_names_for_game_type(championship_id, "xadrez", db)
    for rn, (home_id, away_id) in enumerate(combinations(athlete_ids, 2), start=1):
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="xadrez",
            home_id=home_id, away_id=away_id,
            phase="groups", round_number=rn,
            extra_data={"game_type": "xadrez", "group": group},
        ))
    db.commit()
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez", BoardgameGame.phase == "groups",
    ).all()
    return [_boardgame_game_out(g, names) for g in all_games
            if (g.extra_data or {}).get("group") == group]


# ===========================================================================
# XADREZ — Mata-mata
# ===========================================================================

@router.post("/{championship_id}/xadrez/knockout/setup", status_code=201)
def xadrez_knockout_setup(
    championship_id: int, body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    matches = body.get("matches", [])
    ed = dict(champ.extra_data or {})
    ed["xadrez_knockout_setup"] = matches
    champ.extra_data = ed
    db.commit()
    return {"matches": matches}


@router.post("/{championship_id}/xadrez/knockout/generate", status_code=201)
def xadrez_knockout_generate(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    champ = _get_champ_or_404(championship_id, db)
    setup = (champ.extra_data or {}).get("xadrez_knockout_setup", [])
    if not setup:
        raise HTTPException(status_code=400, detail="Configure os cruzamentos antes de gerar")
    # Xadrez standings usa "player_id" — adapta para "id" na resolução
    raw_groups_data = _xadrez_groups_response(championship_id, champ, db)
    groups_data = [
        {"group": gd["group"],
         "standings": [{"id": s["player_id"], **s} for s in gd.get("standings", [])]}
        for gd in raw_groups_data
    ]
    names = _athlete_names_for_game_type(championship_id, "xadrez", db)
    for match in setup:
        home_id = _resolve_position_label(match.get("home", ""), groups_data)
        away_id = _resolve_position_label(match.get("away", ""), groups_data)
        if not home_id or not away_id:
            continue
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="xadrez",
            home_id=home_id, away_id=away_id,
            phase="knockout", round_number=1,
            extra_data={"game_type": "xadrez", "ko_round": 1},
        ))
    db.commit()
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez", BoardgameGame.phase == "knockout",
    ).all()
    return [_boardgame_game_out(g, names) for g in ko_games]


@router.post("/{championship_id}/xadrez/knockout/advance", status_code=201)
def xadrez_knockout_advance(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    _get_champ_or_404(championship_id, db)
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
        BoardgameGame.phase == "knockout",
    ).order_by(BoardgameGame.round_number.desc()).all()
    if not ko_games:
        raise HTTPException(status_code=400, detail="Nenhum jogo de mata-mata encontrado")
    current_round = ko_games[0].round_number or 1
    current_games = [g for g in ko_games if g.round_number == current_round]
    if any(g.status != "finished" for g in current_games):
        raise HTTPException(status_code=400, detail="Nem todos os jogos da rodada foram concluídos")
    winners = [
        g.home_id if g.result == "home_win" else g.away_id
        for g in current_games if g.result in ("home_win", "away_win")
    ]
    if len(winners) < 2:
        raise HTTPException(status_code=400, detail="Não há jogadores suficientes para a próxima fase")
    names = _athlete_names_for_game_type(championship_id, "xadrez", db)
    next_round = current_round + 1
    for i in range(0, len(winners) - 1, 2):
        db.add(BoardgameGame(
            championship_id=championship_id, game_type="xadrez",
            home_id=winners[i], away_id=winners[i + 1],
            phase="knockout", round_number=next_round,
            extra_data={"game_type": "xadrez", "ko_round": next_round},
        ))
    db.commit()
    new_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "xadrez",
        BoardgameGame.phase == "knockout",
        BoardgameGame.round_number == next_round,
    ).all()
    return [_boardgame_game_out(g, names) for g in new_games]


# ===========================================================================
# XADREZ — Classificação (com Buchholz)
# ===========================================================================

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


# ===========================================================================
# DELETE genérico para boardgame games
# ===========================================================================

@router.delete("/{championship_id}/domino/games/{game_id}", status_code=204)
def delete_domino_game(
    championship_id: int, game_id: int,
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
    championship_id: int, game_id: int,
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
    championship_id: int, game_id: int,
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
