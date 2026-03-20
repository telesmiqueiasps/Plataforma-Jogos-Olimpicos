"""
routes/championships.py
=======================
CRUD de campeonatos, gestão de equipes inscritas,
listagem de jogos e tabela de classificação.
"""

import math
import random
from datetime import datetime, timezone
from functools import cmp_to_key
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organizer
from app.db.models import (
    Athlete,
    Championship,
    ChampionshipTeam,
    Game,
    GameEvent,
    Sport,
    Suspension,
    Team,
    User,
)
from app.db.session import get_db
from app.schemas.championship import (
    ChampionshipConfigUpdate,
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


def _generate_group_round_robin(team_ids: list) -> list:
    """Algoritmo circle-method. Retorna lista de (round_number, home_id, away_id)."""
    pool = list(team_ids)
    if len(pool) % 2 == 1:
        pool.append(None)  # BYE

    n = len(pool)
    result = []
    for round_idx in range(n - 1):
        for i in range(n // 2):
            home = pool[i]
            away = pool[n - 1 - i]
            if home is not None and away is not None:
                result.append((round_idx + 1, home, away))
        # Rotaciona tudo exceto pool[0]
        pool = [pool[0]] + [pool[-1]] + pool[1:-1]
    return result


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
# Configurações (rules_config)
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/config")
def get_config(championship_id: int, db: Session = Depends(get_db)):
    """Retorna o rules_config completo do campeonato."""
    champ = _get_championship_or_404(championship_id, db)
    return champ.rules_config or {}


@router.put("/{championship_id}/config")
def update_config(
    championship_id: int,
    data: ChampionshipConfigUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Atualiza rules_config. Campos não enviados são mantidos."""
    champ = _get_championship_or_404(championship_id, db)
    rules = dict(champ.rules_config or {})

    payload = data.model_dump(exclude_none=True)
    rules.update(payload)
    champ.rules_config = rules

    # Sincroniza classifieds_per_group no modelo também
    if "classifieds_per_group" in payload:
        champ.classifieds_per_group = payload["classifieds_per_group"]

    db.commit()
    return rules


# ---------------------------------------------------------------------------
# Equipes inscritas
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/teams")
def list_championship_teams(championship_id: int, db: Session = Depends(get_db)):
    """Lista equipes inscritas no campeonato."""
    champ = _get_championship_or_404(championship_id, db)
    return [
        {
            "id": link.team_id,
            "name": link.team.name,
            "logo_url": link.team.logo_url,
            "sport_id": link.team.sport_id,
        }
        for link in champ.team_links
    ]


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
    games = (
        db.query(Game)
        .filter(Game.championship_id == championship_id)
        .order_by(Game.phase, Game.round_number, Game.scheduled_at)
        .all()
    )

    # Fallback dinâmico para jogos de knockout sem phase_name salvo em extra_data
    ko_rounds = [g.round_number or 1 for g in games if g.phase == "knockout"]
    max_ko_round = max(ko_rounds) if ko_rounds else 0

    for g in games:
        if g.phase == "groups":
            rn = g.round_number
            g.phase_name = f"Fase de Grupos - Rodada {rn}" if rn else "Fase de Grupos"
        elif g.phase == "knockout":
            saved = (g.extra_data or {}).get("phase_name")
            if saved:
                g.phase_name = saved
            else:
                rn = g.round_number or 1
                diff = max_ko_round - rn
                if diff == 0:
                    g.phase_name = "Final"
                elif diff == 1:
                    g.phase_name = "Semifinal"
                elif diff == 2:
                    g.phase_name = "Quartas de Final"
                elif diff == 3:
                    g.phase_name = "Oitavas de Final"
                else:
                    g.phase_name = f"Mata-mata - Rodada {rn}"
        else:
            g.phase_name = None

    return games


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
    phase: Optional[str] = Query(None, description="Filtra por fase (ex: groups, knockout)"),
    db: Session = Depends(get_db),
):
    champ = _get_championship_or_404(championship_id, db)
    return _build_standings(champ, db, group=group, phase=phase)


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


@router.post("/{championship_id}/groups/{group}/games/generate", status_code=201)
def generate_group_games(
    championship_id: int,
    group: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """Gera todos os jogos de pontos corridos para um grupo específico (round-robin)."""
    champ = _get_championship_or_404(championship_id, db)
    groups_data = (champ.extra_data or {}).get("groups", [])
    group_upper = group.upper()
    group_data = next((g for g in groups_data if g["group"] == group_upper), None)

    if not group_data:
        raise HTTPException(status_code=404, detail=f"Grupo {group_upper} não encontrado")

    team_ids = [t["id"] for t in group_data["teams"]]
    if len(team_ids) < 2:
        raise HTTPException(status_code=400, detail="O grupo precisa ter pelo menos 2 equipes")

    # Verifica se jogos já foram gerados para este grupo
    existing = db.query(Game).filter(
        Game.championship_id == championship_id,
        Game.phase == "groups",
    ).all()
    already_generated = [g for g in existing if (g.extra_data or {}).get("group") == group_upper]
    if already_generated:
        raise HTTPException(
            status_code=400,
            detail=f"Jogos do Grupo {group_upper} já foram gerados ({len(already_generated)} jogos)"
        )

    base_date = champ.start_date or datetime.now(timezone.utc)
    matchups = _generate_group_round_robin(team_ids)

    games_created = []
    for round_number, home_id, away_id in matchups:
        game = Game(
            championship_id=championship_id,
            home_team_id=home_id,
            away_team_id=away_id,
            scheduled_at=base_date,
            status="scheduled",
            phase="groups",
            round_number=round_number,
            extra_data={"group": group_upper},
        )
        db.add(game)
        games_created.append(game)

    db.commit()
    return {"games_created": len(games_created), "group": group_upper, "rounds": max((m[0] for m in matchups), default=0)}


# ---------------------------------------------------------------------------
# Mata-mata (knockout)
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/knockout")
def get_knockout(championship_id: int, db: Session = Depends(get_db)):
    """Retorna o cruzamento do mata-mata definido manualmente."""
    champ = _get_championship_or_404(championship_id, db)
    return champ.knockout_bracket or {}


@router.post("/{championship_id}/knockout/setup")
def setup_knockout(
    championship_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """
    Define os cruzamentos do mata-mata manualmente.
    Body: { "matches": [{"home": "1A", "away": "2B"}, ...] }
    "1A" = 1º do grupo A, "2B" = 2º do grupo B
    """
    champ = _get_championship_or_404(championship_id, db)
    matches = body.get("matches", [])
    if not matches:
        raise HTTPException(status_code=400, detail="Envie ao menos um confronto em 'matches'")

    champ.knockout_bracket = {"matches": matches}
    db.commit()

    # Resolve slots para mostrar quais times seriam os adversários agora
    groups_data = (champ.extra_data or {}).get("groups", [])
    resolved = []
    for match in matches:
        home_team = _resolve_slot(match.get("home"), champ, db, groups_data)
        away_team = _resolve_slot(match.get("away"), champ, db, groups_data)
        resolved.append({
            "home_slot": match.get("home"),
            "away_slot": match.get("away"),
            "home_team": home_team,
            "away_team": away_team,
        })

    return {"championship_id": championship_id, "matches": matches, "resolved": resolved}


@router.post("/{championship_id}/knockout/generate", status_code=201)
def generate_knockout_games(
    championship_id: int,
    body: dict = {},
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """
    Gera os jogos do mata-mata baseado no knockout_bracket definido.
    Resolve "1A" → time que está em 1º no grupo A na classificação atual.
    Body opcional: { "round_number": int } — padrão 1.
    """
    champ = _get_championship_or_404(championship_id, db)
    bracket = champ.knockout_bracket
    round_number: int = (body or {}).get("round_number", 1)

    if not bracket or not bracket.get("matches"):
        raise HTTPException(
            status_code=400,
            detail="Configure os cruzamentos do mata-mata primeiro (POST /knockout/setup)"
        )

    groups_data = (champ.extra_data or {}).get("groups", [])
    base_date = champ.start_date or datetime.now(timezone.utc)
    games_created = []
    errors = []

    # Calcula total de rodadas a partir do número de confrontos do bracket
    num_matches = len(bracket["matches"])
    total_teams = num_matches * 2
    total_rounds = math.ceil(math.log2(total_teams)) if total_teams >= 2 else 1
    phase_name = get_knockout_phase_name(total_rounds, round_number)

    for match in bracket["matches"]:
        home_id = _resolve_slot(match.get("home"), champ, db, groups_data, id_only=True)
        away_id = _resolve_slot(match.get("away"), champ, db, groups_data, id_only=True)

        if not home_id or not away_id:
            errors.append(f"Não foi possível resolver: {match.get('home')} x {match.get('away')}")
            continue

        game = Game(
            championship_id=championship_id,
            home_team_id=home_id,
            away_team_id=away_id,
            scheduled_at=base_date,
            status="scheduled",
            phase="knockout",
            round_number=round_number,
            extra_data={"phase_name": phase_name},
        )
        db.add(game)
        games_created.append(game)

    db.commit()
    return {
        "phase_name": phase_name,
        "round_number": round_number,
        "games_created": len(games_created),
        "errors": errors,
    }


@router.post("/{championship_id}/knockout/advance")
def advance_knockout(
    championship_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_organizer),
):
    """
    Verifica se todos os jogos da rodada atual do mata-mata foram finalizados,
    determina os vencedores e gera automaticamente os confrontos da próxima rodada.
    Retorna { phase_name, round_number, games_created, champion } onde champion é
    preenchido se a final foi disputada.
    """
    champ = _get_championship_or_404(championship_id, db)

    ko_games = (
        db.query(Game)
        .filter(Game.championship_id == championship_id, Game.phase == "knockout")
        .order_by(Game.round_number)
        .all()
    )

    if not ko_games:
        raise HTTPException(status_code=400, detail="Nenhum jogo de mata-mata encontrado")

    max_round = max((g.round_number or 1) for g in ko_games)
    current_round_games = [g for g in ko_games if (g.round_number or 1) == max_round]

    unfinished = [g for g in current_round_games if g.status != "finished"]
    if unfinished:
        raise HTTPException(
            status_code=400,
            detail=f"Nem todos os jogos da rodada foram finalizados ({len(unfinished)} pendentes)",
        )

    def get_winner_id(game: Game) -> Optional[int]:
        if not game.result:
            return None
        if game.result.home_score > game.result.away_score:
            return game.home_team_id
        elif game.result.away_score > game.result.home_score:
            return game.away_team_id
        # Empate: mandante avança (regra de desempate simples)
        return game.home_team_id

    winners = [get_winner_id(g) for g in current_round_games]
    winners = [w for w in winners if w is not None]

    # Se sobrou só 1 vencedor = final foi disputada → campeão
    if len(winners) == 1:
        team = db.query(Team).filter(Team.id == winners[0]).first()
        return {
            "phase_name": "Final",
            "round_number": max_round,
            "games_created": 0,
            "champion": {"team_id": team.id, "team_name": team.name, "logo_url": getattr(team, "logo_url", None)} if team else None,
        }

    next_round = max_round + 1
    base_date = champ.start_date or datetime.now(timezone.utc)

    # Calcula total de rodadas a partir da primeira rodada do mata-mata
    min_round = min((g.round_number or 1) for g in ko_games)
    first_round_count = sum(1 for g in ko_games if (g.round_number or 1) == min_round)
    total_teams = first_round_count * 2
    total_rounds = math.ceil(math.log2(total_teams)) if total_teams >= 2 else 1
    phase_name = get_knockout_phase_name(total_rounds, next_round)

    new_games = []
    for i in range(0, len(winners) - 1, 2):
        game = Game(
            championship_id=championship_id,
            home_team_id=winners[i],
            away_team_id=winners[i + 1],
            scheduled_at=base_date,
            status="scheduled",
            phase="knockout",
            round_number=next_round,
            extra_data={"phase_name": phase_name},
        )
        db.add(game)
        new_games.append(game)

    db.commit()
    return {
        "phase_name": phase_name,
        "round_number": next_round,
        "games_created": len(new_games),
        "champion": None,
    }


@router.get("/{championship_id}/champion")
def get_champion(championship_id: int, db: Session = Depends(get_db)):
    """
    Retorna o campeão do campeonato (vencedor do último jogo do mata-mata com 1 único confronto)
    ou null se o campeonato ainda não terminou.
    """
    _get_championship_or_404(championship_id, db)

    ko_games = (
        db.query(Game)
        .filter(
            Game.championship_id == championship_id,
            Game.phase == "knockout",
            Game.status == "finished",
        )
        .order_by(Game.round_number.desc())
        .all()
    )

    if not ko_games:
        return {"champion": None}

    max_round = ko_games[0].round_number or 1
    last_round_games = [g for g in ko_games if (g.round_number or 1) == max_round]

    # Só há campeão se a rodada final teve exatamente 1 jogo
    if len(last_round_games) != 1:
        return {"champion": None}

    final = last_round_games[0]
    if not final.result:
        return {"champion": None}

    if final.result.home_score > final.result.away_score:
        winner_id = final.home_team_id
    elif final.result.away_score > final.result.home_score:
        winner_id = final.away_team_id
    else:
        return {"champion": None}  # Empate na final — sem campeão

    team = db.query(Team).filter(Team.id == winner_id).first()
    return {
        "champion": {
            "team_id": team.id,
            "team_name": team.name,
            "logo_url": getattr(team, "logo_url", None),
        } if team else None
    }


def _get_phase_name(match_count: int) -> str:
    """Retorna nome da fase baseado no número de confrontos (= metade dos times)."""
    if match_count == 1:
        return "Final"
    elif match_count == 2:
        return "Semifinal"
    elif match_count <= 4:
        return "Quartas de Final"
    elif match_count <= 8:
        return "Oitavas de Final"
    else:
        return f"Rodada de {match_count * 2}"


def get_knockout_phase_name(total_rounds: int, current_round: int) -> str:
    """Retorna nome fixo da fase com base na posição relativa ao total de rodadas."""
    rounds_from_end = total_rounds - current_round
    if rounds_from_end == 0:
        return "Final"
    if rounds_from_end == 1:
        return "Semifinal"
    if rounds_from_end == 2:
        return "Quartas de Final"
    if rounds_from_end == 3:
        return "Oitavas de Final"
    return f"Mata-mata - Rodada {current_round}"


def _resolve_slot(slot: Optional[str], champ: Championship, db: Session, groups_data: list, id_only: bool = False):
    """Resolve "1A" para o time atualmente em 1º do grupo A."""
    if not slot or len(slot) < 2:
        return None
    try:
        position = int(slot[:-1])
    except ValueError:
        return None
    group = slot[-1].upper()

    standings = _build_standings(champ, db, group=group, phase="groups")
    if position <= len(standings):
        entry = standings[position - 1]
        if id_only:
            return entry.team_id
        return {"team_id": entry.team_id, "team_name": entry.team_name}
    return None


# ---------------------------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------------------------

@router.get("/{championship_id}/stats")
def get_championship_stats(championship_id: int, db: Session = Depends(get_db)):
    """
    Retorna:
    - scorers: artilheiros (top 10 por gols) ou cestinhas para basquete
    - cards: tabela de cartões por atleta (vazio para basquete)
    - suspensions: suspensões ativas (games_remaining > 0)
    - sport: slug da modalidade
    """
    champ = _get_championship_or_404(championship_id, db)

    all_game_ids = [
        row[0] for row in db.query(Game.id).filter(Game.championship_id == championship_id).all()
    ]

    sport_slug_stats = champ.sport.slug if champ.sport else None

    if not all_game_ids:
        return {"scorers": [], "cards": [], "suspensions": [], "sport": sport_slug_stats}

    finished_game_ids = [
        row[0] for row in db.query(Game.id).filter(
            Game.championship_id == championship_id,
            Game.status == "finished",
        ).all()
    ]

    # --- Gols (futsal) ou Cestinhas (basquete) ---
    goal_counts: dict = {}
    bball_scorer_counts: dict = {}

    if sport_slug_stats == "basketball":
        # Basquete: contabiliza pontos por atleta via eventos
        for ev in db.query(GameEvent).filter(
            GameEvent.game_id.in_(all_game_ids),
            GameEvent.event_type.in_(["point_1", "point_2", "free_throw"]),
            GameEvent.athlete_id.isnot(None),
        ).all():
            pts_value = 2 if ev.event_type == "point_2" else 1
            if ev.athlete_id not in bball_scorer_counts:
                bball_scorer_counts[ev.athlete_id] = {
                    "point_1": 0, "point_2": 0, "free_throw": 0,
                    "total": 0, "team_id": ev.team_id,
                }
            bball_scorer_counts[ev.athlete_id][ev.event_type] += 1
            bball_scorer_counts[ev.athlete_id]["total"] += pts_value
    else:
        # Futsal e demais: contabiliza gols
        if finished_game_ids:
            for ev in db.query(GameEvent).filter(
                GameEvent.game_id.in_(finished_game_ids),
                GameEvent.event_type == "goal",
                GameEvent.athlete_id.isnot(None),
            ).all():
                if ev.athlete_id not in goal_counts:
                    goal_counts[ev.athlete_id] = {"count": 0, "team_id": ev.team_id}
                goal_counts[ev.athlete_id]["count"] += 1

    # --- Cartões (não para basquete) ---
    card_counts: dict = {}
    if sport_slug_stats != "basketball":
        for ev in db.query(GameEvent).filter(
            GameEvent.game_id.in_(all_game_ids),
            GameEvent.event_type.in_(["yellow_card", "red_card"]),
            GameEvent.athlete_id.isnot(None),
        ).all():
            if ev.athlete_id not in card_counts:
                card_counts[ev.athlete_id] = {"yellow": 0, "red": 0, "team_id": ev.team_id}
            if ev.event_type == "yellow_card":
                card_counts[ev.athlete_id]["yellow"] += 1
            else:
                card_counts[ev.athlete_id]["red"] += 1

    # --- Carrega atletas e times ---
    all_athlete_ids = set(goal_counts.keys()) | set(card_counts.keys()) | set(bball_scorer_counts.keys())
    athletes: dict = {}
    if all_athlete_ids:
        athletes = {a.id: a for a in db.query(Athlete).filter(Athlete.id.in_(all_athlete_ids)).all()}

    all_team_ids = set()
    for d in list(goal_counts.values()) + list(card_counts.values()) + list(bball_scorer_counts.values()):
        if d.get("team_id"):
            all_team_ids.add(d["team_id"])
    teams_map: dict = {}
    if all_team_ids:
        teams_map = {t.id: t for t in db.query(Team).filter(Team.id.in_(all_team_ids)).all()}

    def _team_name(team_id):
        t = teams_map.get(team_id)
        return t.name if t else "—"

    def _team_logo(team_id):
        t = teams_map.get(team_id)
        return t.logo_url if t else None

    if sport_slug_stats == "basketball":
        scorers = sorted(
            [
                {
                    "athlete_id": aid,
                    "name": athletes[aid].name if aid in athletes else "—",
                    "photo_url": athletes[aid].photo_url if aid in athletes else None,
                    "goals": d["total"],
                    "point_1": d["point_1"],
                    "point_2": d["point_2"],
                    "free_throw": d["free_throw"],
                    "team_id": d["team_id"],
                    "team_name": _team_name(d["team_id"]) if d["team_id"] else "—",
                    "team_logo_url": _team_logo(d["team_id"]) if d["team_id"] else None,
                }
                for aid, d in bball_scorer_counts.items()
            ],
            key=lambda x: -x["goals"],
        )[:10]
    else:
        scorers = sorted(
            [
                {
                    "athlete_id": aid,
                    "name": athletes[aid].name if aid in athletes else "—",
                    "photo_url": athletes[aid].photo_url if aid in athletes else None,
                    "goals": d["count"],
                    "team_id": d["team_id"],
                    "team_name": _team_name(d["team_id"]) if d["team_id"] else "—",
                    "team_logo_url": _team_logo(d["team_id"]) if d["team_id"] else None,
                }
                for aid, d in goal_counts.items()
            ],
            key=lambda x: -x["goals"],
        )[:10]

    cards_list = sorted(
        [
            {
                "athlete_id": aid,
                "name": athletes[aid].name if aid in athletes else "—",
                "photo_url": athletes[aid].photo_url if aid in athletes else None,
                "yellow": d["yellow"],
                "red": d["red"],
                "team_id": d["team_id"],
                "team_name": _team_name(d["team_id"]) if d["team_id"] else "—",
                "team_logo_url": _team_logo(d["team_id"]) if d["team_id"] else None,
            }
            for aid, d in card_counts.items()
        ],
        key=lambda x: -(x["yellow"] + x["red"] * 2),
    )

    susp_list = []
    for s in db.query(Suspension).filter(
        Suspension.championship_id == championship_id,
        Suspension.games_remaining > 0,
    ).all():
        athlete = athletes.get(s.athlete_id)
        if athlete is None:
            athlete = db.query(Athlete).filter(Athlete.id == s.athlete_id).first()
        team_obj = None
        if athlete and athlete.team_id:
            team_obj = teams_map.get(athlete.team_id)
            if team_obj is None:
                team_obj = db.query(Team).filter(Team.id == athlete.team_id).first()
        susp_list.append({
            "suspension_id": s.id,
            "athlete_id": s.athlete_id,
            "name": athlete.name if athlete else "—",
            "photo_url": athlete.photo_url if athlete else None,
            "team_id": athlete.team_id if athlete else None,
            "team_name": team_obj.name if team_obj else "—",
            "team_logo_url": team_obj.logo_url if team_obj else None,
            "games_remaining": s.games_remaining,
            "reason": s.reason,
            "expulsion": s.games_remaining >= 999,
        })

    return {"scorers": scorers, "cards": cards_list, "suspensions": susp_list, "sport": sport_slug_stats}


# ---------------------------------------------------------------------------
# _build_standings — helper interno
# ---------------------------------------------------------------------------

def _build_volleyball_standings(
    champ: Championship,
    db: Session,
    group: Optional[str] = None,
    phase: Optional[str] = None,
) -> list[StandingEntry]:
    """Calcula standings para campeonatos de vôlei usando volleyball_service."""
    from app.services import volleyball_service

    team_names: dict[int, str] = {
        link.team_id: link.team.name for link in champ.team_links
    }

    group_upper = group.upper() if group else None
    if group_upper:
        groups_data = (champ.extra_data or {}).get("groups", [])
        group_data = next((g for g in groups_data if g["group"] == group_upper), None)
        if group_data:
            group_ids = {t["id"] for t in group_data["teams"]}
            team_names = {tid: name for tid, name in team_names.items() if tid in group_ids}

    q = db.query(Game).filter(Game.championship_id == champ.id, Game.status == "finished")
    effective_phase = (phase or "groups") if group_upper else phase
    if effective_phase:
        q = q.filter(Game.phase == effective_phase)

    finished_games = q.all()
    if group_upper:
        finished_games = [g for g in finished_games if (g.extra_data or {}).get("group") == group_upper]

    rules = champ.rules_config or {}
    entries = volleyball_service.calculate_volleyball_standings(finished_games, rules, team_names)

    return [
        StandingEntry(
            position=e["position"],
            team_id=e["team_id"],
            team_name=e["team_name"],
            games_played=e["games_played"],
            wins=e["wins"],
            draws=e["draws"],
            losses=e["losses"],
            goals_for=e["goals_for"],
            goals_against=e["goals_against"],
            goal_diff=e["goal_diff"],
            points=e["points"],
            sets_won=e["sets_won"],
            sets_lost=e["sets_lost"],
            set_difference=e["set_difference"],
            set_average=round(e["set_average"], 3),
            points_scored=e["points_scored"],
            points_against=e["points_against"],
            points_average=round(e["points_average"], 3),
        )
        for e in entries
    ]


def _build_basketball_standings(
    champ: Championship,
    db: Session,
    group: Optional[str] = None,
    phase: Optional[str] = None,
) -> list[StandingEntry]:
    """Calcula standings para campeonatos de basquete usando basketball_service."""
    from app.services import basketball_service

    team_names: dict[int, str] = {
        link.team_id: link.team.name for link in champ.team_links
    }

    group_upper = group.upper() if group else None
    if group_upper:
        groups_data = (champ.extra_data or {}).get("groups", [])
        group_data = next((g for g in groups_data if g["group"] == group_upper), None)
        if group_data:
            group_ids = {t["id"] for t in group_data["teams"]}
            team_names = {tid: name for tid, name in team_names.items() if tid in group_ids}

    q = db.query(Game).filter(Game.championship_id == champ.id, Game.status == "finished")
    effective_phase = (phase or "groups") if group_upper else phase
    if effective_phase:
        q = q.filter(Game.phase == effective_phase)

    finished_games = q.all()
    if group_upper:
        finished_games = [g for g in finished_games if (g.extra_data or {}).get("group") == group_upper]

    rules = champ.rules_config or {}
    entries = basketball_service.calculate_basketball_standings(finished_games, rules, team_names)

    return [
        StandingEntry(
            position=e["position"],
            team_id=e["team_id"],
            team_name=e["team_name"],
            games_played=e["games_played"],
            wins=e["wins"],
            draws=e["draws"],
            losses=e["losses"],
            goals_for=e["goals_for"],
            goals_against=e["goals_against"],
            goal_diff=e["goal_diff"],
            points=e["points"],
            points_scored=e["points_scored"],
            points_against=e["points_against"],
        )
        for e in entries
    ]


def _build_standings(
    champ: Championship,
    db: Session,
    group: Optional[str] = None,
    phase: Optional[str] = None,
) -> list[StandingEntry]:
    # Detecta modalidade — vôlei e basquete usam lógica própria
    sport_slug = champ.sport.slug if champ.sport else None
    if sport_slug == "volleyball":
        return _build_volleyball_standings(champ, db, group, phase)
    if sport_slug == "basketball":
        return _build_basketball_standings(champ, db, group, phase)

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

    # Filtra por grupo se informado (restringe times ao grupo)
    group_upper = group.upper() if group else None
    if group_upper:
        groups_data = (champ.extra_data or {}).get("groups", [])
        group_data = next((g for g in groups_data if g["group"] == group_upper), None)
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

    # Query de jogos finalizados
    q = db.query(Game).filter(Game.championship_id == champ.id, Game.status == "finished")

    # Quando grupo for especificado, filtra apenas jogos da fase de grupos
    if group_upper:
        effective_phase = phase or "groups"
    else:
        effective_phase = phase

    if effective_phase:
        q = q.filter(Game.phase == effective_phase)

    finished_games = q.all()

    # Filtra jogos pelo extra_data->group quando grupo for especificado
    if group_upper:
        finished_games = [g for g in finished_games if (g.extra_data or {}).get("group") == group_upper]

    for g in finished_games:
        if not g.result:
            continue
        hi, ai  = g.home_team_id, g.away_team_id
        hs, as_ = g.result.home_score, g.result.away_score

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
