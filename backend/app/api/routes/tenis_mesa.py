"""
routes/tenis_mesa.py
=====================
Endpoints para a modalidade Tênis de Mesa (individual, sets-based).
Participantes: BoardgameParticipant
Jogos: BoardgameGame (home_score = sets vencidos, extra_data["sets"] = detalhe de cada set)
Classificação: sistema de pontos estilo vôlei, configurável via rules_config
"""

import random
from itertools import combinations
from functools import cmp_to_key

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from app.db.models import Athlete, BoardgameGame, BoardgameParticipant, Championship, User
from app.db.session import get_db

router = APIRouter(prefix="/championships", tags=["Tênis de Mesa"])

_GROUP_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_champ_or_404(championship_id: int, db: Session) -> Championship:
    c = db.query(Championship).filter(Championship.id == championship_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campeonato não encontrado")
    return c


def _get_participants(championship_id: int, db: Session) -> list:
    return db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.game_type == "tenis_mesa",
    ).all()


def _participant_out(p: BoardgameParticipant) -> dict:
    return {
        "id": p.id,
        "athlete_id": p.athlete_id,
        "athlete_name": p.athlete_name,
        "athlete_photo_url": p.athlete_photo_url,
        "game_type": p.game_type,
    }


def _names_map(championship_id: int, db: Session) -> dict:
    parts = _get_participants(championship_id, db)
    return {p.athlete_id: p.athlete_name for p in parts}


def _game_out(g: BoardgameGame, names: dict) -> dict:
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
        "home_score": g.home_score,
        "away_score": g.away_score,
        "result": g.result,
        "sets": ed.get("sets", []),
        "extra_data": ed,
    }


def _sets_to_win(best_of: int) -> int:
    """Retorna quantos sets são necessários para vencer."""
    return (best_of // 2) + 1  # B3→2, B5→3, B7→4


def _compute_standings(parts: list, games: list, rules: dict) -> list:
    """
    Classifica participantes de tênis de mesa pelo sistema de pontos configurável.
    Critérios de desempate: pontos, vitorias, saldo_sets, set_average, pontos_average, confronto_direto.
    """
    best_of = int(rules.get("best_of", 5))
    win_sets = _sets_to_win(best_of)

    pts_win_straight  = int(rules.get("pts_win_straight",  3))  # vitória sem set perdido (ex: 3-0, 4-0)
    pts_win_one_loss  = int(rules.get("pts_win_one_loss",  3))  # vitória com 1 set perdido
    pts_win_two_loss  = int(rules.get("pts_win_two_loss",  2))  # vitória com 2+ sets perdidos
    pts_loss_two_wins = int(rules.get("pts_loss_two_wins", 1))  # derrota com 2+ sets ganhos
    pts_loss          = int(rules.get("pts_loss",          0))  # derrota com 0 ou 1 set ganho

    tiebreakers = rules.get(
        "tiebreaker_order",
        ["pontos", "vitorias", "saldo_sets", "set_average", "pontos_average", "confronto_direto"],
    )

    stats: dict[int, dict] = {
        p.athlete_id: {
            "id": p.athlete_id,
            "name": p.athlete_name,
            "photo_url": p.athlete_photo_url,
            "j": 0, "v": 0, "d": 0,
            "pontos": 0,
            "sets_won": 0, "sets_lost": 0,
            "pontos_marcados": 0, "pontos_sofridos": 0,
        }
        for p in parts
    }

    # H2H: h2h[a][b] = {"pts": int, "saldo_sets": int}
    h2h: dict[int, dict[int, dict]] = {p.athlete_id: {} for p in parts}

    for g in games:
        if g.status != "finished":
            continue
        home_sets = g.home_score or 0
        away_sets = g.away_score or 0
        ed = g.extra_data or {}
        sets_detail = ed.get("sets", [])
        home_pts_scored = sum(s.get("home_points", 0) for s in sets_detail)
        away_pts_scored = sum(s.get("away_points", 0) for s in sets_detail)

        def _table_pts(winner_sets: int, loser_sets: int) -> tuple[int, int]:
            """Retorna (pts_vencedor, pts_perdedor) baseado nos sets do perdedor."""
            if loser_sets == 0:
                wp = pts_win_straight
            elif loser_sets == 1:
                wp = pts_win_one_loss
            else:  # 2 ou mais sets perdidos
                wp = pts_win_two_loss
            lp = pts_loss_two_wins if loser_sets >= 2 else pts_loss
            return wp, lp

        if home_sets == win_sets:
            h_tp, a_tp = _table_pts(home_sets, away_sets)
        elif away_sets == win_sets:
            a_tp, h_tp = _table_pts(away_sets, home_sets)
        else:
            h_tp, a_tp = 0, 0

        for (tid, opp, sets_w, sets_l, tp, pts_s, pts_a) in [
            (g.home_id, g.away_id, home_sets, away_sets, h_tp, home_pts_scored, away_pts_scored),
            (g.away_id, g.home_id, away_sets, home_sets, a_tp, away_pts_scored, home_pts_scored),
        ]:
            if tid not in stats:
                continue
            s = stats[tid]
            s["j"] += 1
            s["sets_won"] += sets_w
            s["sets_lost"] += sets_l
            s["pontos"] += tp
            s["pontos_marcados"] += pts_s
            s["pontos_sofridos"] += pts_a
            if sets_w == win_sets:
                s["v"] += 1
            else:
                s["d"] += 1

            # Registra H2H
            if tid not in h2h:
                h2h[tid] = {}
            if opp not in h2h[tid]:
                h2h[tid][opp] = {"pts": 0, "saldo_sets": 0}
            h2h[tid][opp]["pts"] += tp
            h2h[tid][opp]["saldo_sets"] += sets_w - sets_l

    # Calcula campos derivados
    for s in stats.values():
        saldo = s["sets_won"] - s["sets_lost"]
        s["saldo_sets"] = saldo
        s["set_average"] = (
            s["sets_won"] / s["sets_lost"] if s["sets_lost"] > 0 else float(s["sets_won"])
        )
        s["pontos_average"] = (
            s["pontos_marcados"] / s["pontos_sofridos"] if s["pontos_sofridos"] > 0
            else float(s["pontos_marcados"])
        )

    def compare(a: dict, b: dict) -> int:
        for tb in tiebreakers:
            if tb == "pontos":
                diff = b["pontos"] - a["pontos"]
            elif tb == "vitorias":
                diff = b["v"] - a["v"]
            elif tb == "saldo_sets":
                diff = b["saldo_sets"] - a["saldo_sets"]
            elif tb == "set_average":
                diff_f = b["set_average"] - a["set_average"]
                diff = 1 if diff_f > 0 else (-1 if diff_f < 0 else 0)
            elif tb == "pontos_average":
                diff_f = b["pontos_average"] - a["pontos_average"]
                diff = 1 if diff_f > 0 else (-1 if diff_f < 0 else 0)
            elif tb == "confronto_direto":
                ap = h2h.get(a["id"], {}).get(b["id"], {}).get("pts", 0)
                bp = h2h.get(b["id"], {}).get(a["id"], {}).get("pts", 0)
                diff = bp - ap
                if diff == 0:
                    ag = h2h.get(a["id"], {}).get(b["id"], {}).get("saldo_sets", 0)
                    bg = h2h.get(b["id"], {}).get(a["id"], {}).get("saldo_sets", 0)
                    diff = bg - ag
            else:
                diff = 0
            if diff != 0:
                return diff
        return 0

    ranked = sorted(stats.values(), key=cmp_to_key(compare))
    for i, r in enumerate(ranked):
        r["position"] = i + 1
    return ranked


def _resolve_label(label: str, groups_data: list) -> int | None:
    """Resolve '1A', '2B' etc. para athlete_id."""
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


def _groups_response(championship_id: int, champ: Championship, db: Session) -> list:
    raw_groups = (champ.extra_data or {}).get("tenis_groups", {})
    if not raw_groups:
        return []
    rules = champ.rules_config or {}
    all_parts = _get_participants(championship_id, db)
    parts_by_id = {p.athlete_id: p for p in all_parts}
    names = {p.athlete_id: p.athlete_name for p in all_parts}
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
        BoardgameGame.phase == "groups",
    ).all()
    result = []
    for letter in sorted(raw_groups.keys()):
        athlete_ids = raw_groups[letter]
        group_parts = [parts_by_id[aid] for aid in athlete_ids if aid in parts_by_id]
        group_games = [g for g in all_games if (g.extra_data or {}).get("group") == letter]
        standings = _compute_standings(group_parts, group_games, rules)
        result.append({
            "group": letter,
            "participants": [_participant_out(p) for p in group_parts],
            "standings": standings,
            "games": [_game_out(g, names) for g in group_games],
        })
    return result


# ===========================================================================
# PARTICIPANTES
# ===========================================================================

@router.get("/{championship_id}/tenis/participants")
def list_participants(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_champ_or_404(championship_id, db)
    return [_participant_out(p) for p in _get_participants(championship_id, db)]


@router.post("/{championship_id}/tenis/participants", status_code=201)
def add_participant(
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
    if db.query(BoardgameParticipant).filter(
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.athlete_id == athlete_id,
        BoardgameParticipant.game_type == "tenis_mesa",
    ).first():
        raise HTTPException(status_code=400, detail="Atleta já inscrito neste campeonato")
    p = BoardgameParticipant(
        championship_id=championship_id,
        athlete_id=athlete_id,
        game_type="tenis_mesa",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _participant_out(p)


@router.delete("/{championship_id}/tenis/participants/{part_id}", status_code=204)
def remove_participant(
    championship_id: int,
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    p = db.query(BoardgameParticipant).filter(
        BoardgameParticipant.id == part_id,
        BoardgameParticipant.championship_id == championship_id,
        BoardgameParticipant.game_type == "tenis_mesa",
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Participante não encontrado")
    db.delete(p)
    db.commit()


# ===========================================================================
# JOGOS
# ===========================================================================

@router.get("/{championship_id}/tenis/games")
def list_games(championship_id: int, db: Session = Depends(get_db)):
    _get_champ_or_404(championship_id, db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
    ).order_by(BoardgameGame.round_number, BoardgameGame.id).all()
    names = _names_map(championship_id, db)
    return [_game_out(g, names) for g in games]


@router.post("/{championship_id}/tenis/games", status_code=201)
def create_game(
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
        game_type="tenis_mesa",
        home_id=home_id,
        away_id=away_id,
        phase=body.get("phase", "groups"),
        round_number=body.get("round_number"),
        extra_data={"game_type": "tenis_mesa", "sets": [], "group": body.get("group")},
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return _game_out(game, _names_map(championship_id, db))


@router.put("/{championship_id}/tenis/games/{game_id}/result")
def register_result(
    championship_id: int,
    game_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """
    Body: {
      sets: [{"home_points": int, "away_points": int}, ...],
      finalize: bool  (default true)
    }
    home_score e away_score são calculados automaticamente a partir dos sets.
    """
    game = db.query(BoardgameGame).filter(
        BoardgameGame.id == game_id,
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    best_of = int(rules.get("best_of", 5))
    win_sets = _sets_to_win(best_of)

    sets = body.get("sets", [])
    if not sets:
        raise HTTPException(status_code=400, detail="Envie os sets no body: [{home_points, away_points}, ...]")

    home_sets_won = sum(1 for s in sets if s.get("home_points", 0) > s.get("away_points", 0))
    away_sets_won = sum(1 for s in sets if s.get("away_points", 0) > s.get("home_points", 0))

    if home_sets_won == win_sets:
        result = "home_win"
    elif away_sets_won == win_sets:
        result = "away_win"
    else:
        result = None  # Jogo ainda em andamento

    prev_ed = game.extra_data or {}
    game.extra_data = {**prev_ed, "game_type": "tenis_mesa", "sets": sets}
    game.home_score = home_sets_won
    game.away_score = away_sets_won
    game.result = result

    finalize = body.get("finalize", True)
    if finalize and result:
        game.status = "finished"
    elif game.status == "scheduled":
        game.status = "live"

    db.commit()
    db.refresh(game)
    return _game_out(game, _names_map(championship_id, db))


# ===========================================================================
# GRUPOS
# ===========================================================================

@router.post("/{championship_id}/tenis/groups/draw", status_code=201)
def draw_groups(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Body: { group_count: int } — sorteia participantes nos grupos."""
    champ = _get_champ_or_404(championship_id, db)
    group_count = int(body.get("group_count", 2))
    if group_count < 1:
        raise HTTPException(status_code=400, detail="group_count deve ser >= 1")
    parts = _get_participants(championship_id, db)
    if not parts:
        raise HTTPException(status_code=400, detail="Inscreva participantes antes de sortear grupos")
    shuffled = list(parts)
    random.shuffle(shuffled)
    groups: dict[str, list[int]] = {}
    for i, p in enumerate(shuffled):
        groups.setdefault(_GROUP_LETTERS[i % group_count], []).append(p.athlete_id)
    ed = dict(champ.extra_data or {})
    ed["tenis_groups"] = groups
    champ.extra_data = ed
    db.commit()
    return _groups_response(championship_id, champ, db)


@router.get("/{championship_id}/tenis/groups")
def list_groups(championship_id: int, db: Session = Depends(get_db)):
    champ = _get_champ_or_404(championship_id, db)
    return _groups_response(championship_id, champ, db)


@router.post("/{championship_id}/tenis/groups/{group}/games/generate", status_code=201)
def generate_group_games(
    championship_id: int,
    group: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Gera confronto todos-contra-todos (round-robin) para o grupo especificado."""
    champ = _get_champ_or_404(championship_id, db)
    group = group.upper()
    raw_groups = (champ.extra_data or {}).get("tenis_groups", {})
    if group not in raw_groups:
        raise HTTPException(status_code=404, detail=f"Grupo {group} não encontrado")
    athlete_ids = raw_groups[group]
    names = _names_map(championship_id, db)
    for rn, (home_id, away_id) in enumerate(combinations(athlete_ids, 2), start=1):
        db.add(BoardgameGame(
            championship_id=championship_id,
            game_type="tenis_mesa",
            home_id=home_id,
            away_id=away_id,
            phase="groups",
            round_number=rn,
            extra_data={"game_type": "tenis_mesa", "sets": [], "group": group},
        ))
    db.commit()
    all_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
        BoardgameGame.phase == "groups",
    ).all()
    return [_game_out(g, names) for g in all_games if (g.extra_data or {}).get("group") == group]


# ===========================================================================
# MATA-MATA
# ===========================================================================

@router.post("/{championship_id}/tenis/knockout/setup", status_code=201)
def knockout_setup(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Salva cruzamentos do mata-mata. Body: { matches: [{"home": "1A", "away": "2B"}, ...] }"""
    champ = _get_champ_or_404(championship_id, db)
    matches = body.get("matches", [])
    ed = dict(champ.extra_data or {})
    ed["tenis_knockout_setup"] = matches
    champ.extra_data = ed
    db.commit()
    return {"matches": matches}


@router.post("/{championship_id}/tenis/knockout/generate", status_code=201)
def knockout_generate(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Gera os jogos do mata-mata com base nos cruzamentos configurados."""
    champ = _get_champ_or_404(championship_id, db)
    setup = (champ.extra_data or {}).get("tenis_knockout_setup", [])
    if not setup:
        raise HTTPException(status_code=400, detail="Configure os cruzamentos antes de gerar")
    groups_data = _groups_response(championship_id, champ, db)
    names = _names_map(championship_id, db)
    for match in setup:
        home_id = _resolve_label(match.get("home", ""), groups_data)
        away_id = _resolve_label(match.get("away", ""), groups_data)
        if not home_id or not away_id:
            continue
        db.add(BoardgameGame(
            championship_id=championship_id,
            game_type="tenis_mesa",
            home_id=home_id,
            away_id=away_id,
            phase="knockout",
            round_number=1,
            extra_data={"game_type": "tenis_mesa", "sets": [], "ko_round": 1},
        ))
    db.commit()
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
        BoardgameGame.phase == "knockout",
    ).all()
    return [_game_out(g, names) for g in ko_games]


@router.post("/{championship_id}/tenis/knockout/advance", status_code=201)
def knockout_advance(
    championship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    """Avança a fase do mata-mata: pega os vencedores da rodada atual e gera a próxima."""
    _get_champ_or_404(championship_id, db)
    ko_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
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
    names = _names_map(ko_games[0].championship_id, db)
    next_round = current_round + 1
    for i in range(0, len(winners) - 1, 2):
        db.add(BoardgameGame(
            championship_id=ko_games[0].championship_id,
            game_type="tenis_mesa",
            home_id=winners[i],
            away_id=winners[i + 1],
            phase="knockout",
            round_number=next_round,
            extra_data={"game_type": "tenis_mesa", "sets": [], "ko_round": next_round},
        ))
    db.commit()
    new_games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == ko_games[0].championship_id,
        BoardgameGame.game_type == "tenis_mesa",
        BoardgameGame.phase == "knockout",
        BoardgameGame.round_number == next_round,
    ).all()
    return [_game_out(g, names) for g in new_games]


# ===========================================================================
# CLASSIFICAÇÃO GERAL
# ===========================================================================

@router.get("/{championship_id}/tenis/standings")
def get_standings(championship_id: int, db: Session = Depends(get_db)):
    champ = _get_champ_or_404(championship_id, db)
    rules = champ.rules_config or {}
    parts = _get_participants(championship_id, db)
    games = db.query(BoardgameGame).filter(
        BoardgameGame.championship_id == championship_id,
        BoardgameGame.game_type == "tenis_mesa",
        BoardgameGame.status == "finished",
    ).all()
    return _compute_standings(parts, games, rules)
