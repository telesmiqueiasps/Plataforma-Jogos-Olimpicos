"""
routes/championships.py
=======================
CRUD de campeonatos, gestão de equipes inscritas,
listagem de jogos e tabela de classificação.
"""

import random
from functools import cmp_to_key
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from app.db.models import Championship, ChampionshipTeam, Game, GameEvent, Sport, Suspension, Team, User
from app.db.session import get_db
from app.schemas.championship import (
    ChampionshipCreate,
    ChampionshipOut,
    ChampionshipUpdate,
    GroupDrawRequest,
    GroupEntry,
    StandingEntry,
)
from app.schemas.game import GameCreate, GameOut

router = APIRouter(prefix="/championships", tags=["Campeonatos"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_championship_or_404(championship_id: int, db: Session) -> Championship:
    champ = db.query(Championship).filter(Championship.id == championship_id).first()
    if not champ:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campeonato não encontrado")
    return champ


# ---------------------------------------------------------------------------
# CRUD de campeonatos
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ChampionshipOut])
def list_championships(
    status: Optional[str] = Query(None, description="Filtra por status: draft | active | finished"),
    sport_id: Optional[int] = Query(None, description="Filtra por modalidade"),
    db: Session = Depends(get_db),
):
    q = db.query(Championship)
    if status:
        q = q.filter(Championship.status == status)
    if sport_id is not None:
        q = q.filter(Championship.sport_id == sport_id)
    return q.order_by(Championship.id.desc()).all()


@router.post("/", response_model=ChampionshipOut, status_code=201)
def create_championship(
    data: ChampionshipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organizer),
):
    sport = db.query(Sport).filter(Sport.id == data.sport_id).first()
    if not sport:
        raise HTTPException(status_code=404, detail="Modalidade não encontrada")

    team_ids = data.team_ids or []
    champ = Championship(**data.model_dump(exclude={"team_ids"}), created_by=current_user.id)
    db.add(champ)
    db.commit()
    db.refresh(champ)

    for team_id in team_ids:
        team = db.query(Team).filter(Team.id == team_id).first()
        if team:
            already = db.query(ChampionshipTeam).filter(
                ChampionshipTeam.championship_id == champ.id,
                ChampionshipTeam.team_id == team_id,
            ).first()
            if not already:
                db.add(ChampionshipTeam(championship_id=champ.id, team_id=team_id))
    db.commit()
    db.refresh(champ)
    return champ


@router.get("/{championship_id}", response_model=ChampionshipOut)
def get_championship(championship_id: int, db: Session = Depends(get_db)):
    return _get_championship_or_404(championship_id, db)


@router.put("/{championship_id}", response_model=ChampionshipOut)
def update_championship(
    championship_id: int,
    data: ChampionshipUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    champ = _get_championship_or_404(championship_id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(champ, field, value)
    db.commit()
    db.refresh(champ)
    return champ


@router.delete("/{championship_id}", status_code=204)
def delete_championship(
    championship_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    champ = _get_championship_or_404(championship_id, db)
    db.delete(champ)
    db.commit()


# ---------------------------------------------------------------------------
# Equipes inscritas
# ---------------------------------------------------------------------------

@router.post("/{championship_id}/teams", status_code=201)
def add_team(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Inscreve uma equipe no campeonato. Body: {"team_id": int}"""
    team_id: int = body.get("team_id")
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id é obrigatório")

    champ = _get_championship_or_404(championship_id, db)

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Equipe não encontrada")

    already = (
        db.query(ChampionshipTeam)
        .filter(
            ChampionshipTeam.championship_id == championship_id,
            ChampionshipTeam.team_id == team_id,
        )
        .first()
    )
    if already:
        raise HTTPException(status_code=400, detail="Equipe já inscrita neste campeonato")

    link = ChampionshipTeam(championship_id=championship_id, team_id=team_id)
    db.add(link)
    db.commit()
    return {"championship_id": championship_id, "team_id": team_id, "team_name": team.name}


@router.delete("/{championship_id}/teams/{team_id}", status_code=204)
def remove_team(
    championship_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    link = (
        db.query(ChampionshipTeam)
        .filter(
            ChampionshipTeam.championship_id == championship_id,
            ChampionshipTeam.team_id == team_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Equipe não está inscrita neste campeonato")
    db.delete(link)
    db.commit()


# ---------------------------------------------------------------------------
# Jogos do campeonato
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/games", response_model=list[GameOut])
def list_games(
    championship_id: int,
    db: Session = Depends(get_db),
):
    _get_championship_or_404(championship_id, db)
    return (
        db.query(Game)
        .filter(Game.championship_id == championship_id)
        .order_by(Game.round_number, Game.scheduled_at)
        .all()
    )


@router.post("/{championship_id}/games", response_model=GameOut, status_code=201)
def create_game(
    championship_id: int,
    data: GameCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Cria um jogo manualmente no campeonato."""
    champ = _get_championship_or_404(championship_id, db)

    for team_id, label in [(data.home_team_id, "mandante"), (data.away_team_id, "visitante")]:
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail=f"Equipe {label} não encontrada")

    game = Game(**data.model_dump(), championship_id=championship_id)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


# ---------------------------------------------------------------------------
# Tabela de classificação
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/standings", response_model=list[StandingEntry])
def get_standings(
    championship_id: int,
    group: Optional[str] = Query(None, description="Filtra por grupo (ex: A, B, C)"),
    db: Session = Depends(get_db),
):
    champ = _get_championship_or_404(championship_id, db)
    return _build_standings(champ, db, group=group)


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@router.post("/{championship_id}/groups/draw", response_model=list[GroupEntry])
def draw_groups(
    championship_id: int,
    body: GroupDrawRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Sorteia grupos aleatoriamente e salva em extra_data do campeonato."""
    champ = _get_championship_or_404(championship_id, db)
    teams = [link.team for link in champ.team_links]

    if body.group_count < 1:
        raise HTTPException(status_code=400, detail="group_count deve ser >= 1")
    if len(teams) < body.group_count:
        raise HTTPException(
            status_code=400,
            detail=f"Times insuficientes ({len(teams)}) para {body.group_count} grupos",
        )

    shuffled = teams.copy()
    random.shuffle(shuffled)

    group_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    groups = []
    for i in range(body.group_count):
        group_teams = shuffled[i::body.group_count]
        groups.append({
            "group": group_labels[i],
            "teams": [{"id": t.id, "name": t.name, "logo_url": t.logo_url} for t in group_teams],
        })

    extra_data = dict(champ.extra_data or {})
    extra_data["groups"] = groups
    champ.extra_data = extra_data
    champ.group_count = body.group_count
    db.commit()
    return groups


@router.get("/{championship_id}/groups", response_model=list[GroupEntry])
def get_groups(championship_id: int, db: Session = Depends(get_db)):
    """Retorna grupos salvos no extra_data do campeonato."""
    champ = _get_championship_or_404(championship_id, db)
    return (champ.extra_data or {}).get("groups", [])


def _build_standings(champ: Championship, db: Session, group: Optional[str] = None) -> list[StandingEntry]:
    rules        = champ.rules_config or {}
    pts_win      = rules.get("points_win",  3)
    pts_draw     = rules.get("points_draw", 1)
    pts_loss     = rules.get("points_loss", 0)
    tiebreakers  = rules.get(
        "tiebreaker_order",
        ["points", "wins", "goal_difference", "goals_scored"],
    )

    # Monta dicionário de estatísticas por time
    team_names: dict[int, str] = {
        link.team_id: link.team.name for link in champ.team_links
    }

    # Filtra por grupo se informado
    if group:
        groups_data = (champ.extra_data or {}).get("groups", [])
        group_data = next((g for g in groups_data if g["group"] == group.upper()), None)
        if group_data:
            group_ids = {t["id"] for t in group_data["teams"]}
            team_names = {tid: name for tid, name in team_names.items() if tid in group_ids}
    entry: dict[int, dict] = {
        tid: dict(
            team_id=tid, team_name=name,
            games_played=0, wins=0, draws=0, losses=0,
            goals_for=0, goals_against=0, goal_diff=0, points=0,
        )
        for tid, name in team_names.items()
    }

    # H2H: h2h[a][b] = {"pts": int, "gd": int}
    h2h: dict[int, dict[int, dict]] = {tid: {} for tid in team_names}

    finished_games = (
        db.query(Game)
        .filter(Game.championship_id == champ.id, Game.status == "finished")
        .all()
    )

    for g in finished_games:
        if not g.result:
            continue
        hi, ai     = g.home_team_id, g.away_team_id
        hs, as_    = g.result.home_score, g.result.away_score

        # Atualiza contadores básicos
        for tid, gf, ga in [(hi, hs, as_), (ai, as_, hs)]:
            if tid not in entry:
                continue
            e = entry[tid]
            e["games_played"]  += 1
            e["goals_for"]     += gf
            e["goals_against"] += ga

        if hs > as_:
            h_pts, a_pts = pts_win, pts_loss
            if hi in entry: entry[hi]["wins"]   += 1; entry[hi]["points"] += pts_win
            if ai in entry: entry[ai]["losses"] += 1; entry[ai]["points"] += pts_loss
        elif as_ > hs:
            h_pts, a_pts = pts_loss, pts_win
            if ai in entry: entry[ai]["wins"]   += 1; entry[ai]["points"] += pts_win
            if hi in entry: entry[hi]["losses"] += 1; entry[hi]["points"] += pts_loss
        else:
            h_pts = a_pts = pts_draw
            if hi in entry: entry[hi]["draws"] += 1; entry[hi]["points"] += pts_draw
            if ai in entry: entry[ai]["draws"] += 1; entry[ai]["points"] += pts_draw

        # Registra H2H
        for tid_a, tid_b, pts_a, gd_a in [
            (hi, ai, h_pts, hs - as_),
            (ai, hi, a_pts, as_ - hs),
        ]:
            if tid_a not in h2h:
                continue
            if tid_b not in h2h[tid_a]:
                h2h[tid_a][tid_b] = {"pts": 0, "gd": 0}
            h2h[tid_a][tid_b]["pts"] += pts_a
            h2h[tid_a][tid_b]["gd"]  += gd_a

    for e in entry.values():
        e["goal_diff"] = e["goals_for"] - e["goals_against"]

    # Comparador com critérios configuráveis
    def compare(a: dict, b: dict) -> int:
        for tb in tiebreakers:
            if tb == "points":
                diff = b["points"] - a["points"]
            elif tb == "wins":
                diff = b["wins"] - a["wins"]
            elif tb == "goal_difference":
                diff = b["goal_diff"] - a["goal_diff"]
            elif tb == "goals_scored":
                diff = b["goals_for"] - a["goals_for"]
            elif tb == "head_to_head":
                ap = h2h.get(a["team_id"], {}).get(b["team_id"], {}).get("pts", 0)
                bp = h2h.get(b["team_id"], {}).get(a["team_id"], {}).get("pts", 0)
                diff = bp - ap
                if diff == 0:
                    ag = h2h.get(a["team_id"], {}).get(b["team_id"], {}).get("gd", 0)
                    bg = h2h.get(b["team_id"], {}).get(a["team_id"], {}).get("gd", 0)
                    diff = bg - ag
            else:
                diff = 0
            if diff != 0:
                return diff
        return 0

    sorted_list = sorted(entry.values(), key=cmp_to_key(compare))
    return [StandingEntry(position=i + 1, **s) for i, s in enumerate(sorted_list)]
