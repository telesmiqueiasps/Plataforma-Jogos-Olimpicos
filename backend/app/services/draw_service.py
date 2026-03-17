"""
draw_service.py
===============
Camada de serviço para sorteio: orquestra a lógica do banco de dados em torno
dos algoritmos puros de draw_algorithms.py.

Todas as funções recebem uma AsyncSession já aberta e são responsáveis
pelo próprio commit.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Championship, ChampionshipTeam, Game, Team
from app.schemas.draw import (
    GameSlot,
    ManualGameCreate,
    ManualGameResponse,
    RoundDetail,
    RoundRobinDrawResponse,
)
from app.schemas.standings import BracketGame, BracketResult, BracketRound
from app.services.draw_algorithms import (
    apply_heads_seeding,
    next_power_of_2,
    phase_name,
    round_robin_pairs,
    seeded_bracket_pairs,
    validate_teams_order,
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _get_champ(db: AsyncSession, championship_id: int) -> Championship:
    champ = await db.get(Championship, championship_id)
    if champ is None:
        raise LookupError(f"Campeonato {championship_id} não encontrado")
    return champ


async def _load_enrolled_teams(db: AsyncSession, championship_id: int) -> list[Team]:
    rows = (
        await db.execute(
            select(ChampionshipTeam)
            .options(selectinload(ChampionshipTeam.team))
            .where(ChampionshipTeam.championship_id == championship_id)
        )
    ).scalars().all()
    return [row.team for row in rows]


async def _guard_no_existing_games(db: AsyncSession, championship_id: int) -> None:
    """Impede sorteio duplicado: levanta se já existem jogos cadastrados."""
    existing = (
        await db.execute(
            select(Game.id)
            .where(Game.championship_id == championship_id)
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise ValueError(
            "O campeonato já possui jogos cadastrados. "
            "Remova os jogos existentes antes de realizar um novo sorteio."
        )


async def _load_team_map(db: AsyncSession, team_ids: set[int]) -> dict[int, Team]:
    rows = (
        await db.execute(select(Team).where(Team.id.in_(team_ids)))
    ).scalars().all()
    return {t.id: t for t in rows}


# ---------------------------------------------------------------------------
# 1. Sorteio round-robin
# ---------------------------------------------------------------------------

async def execute_round_robin_draw(
    db: AsyncSession,
    championship_id: int,
    randomize: bool = True,
    teams_order: Optional[list[int]] = None,
    legs: int = 2,
) -> RoundRobinDrawResponse:
    """
    Gera e persiste todos os jogos de um campeonato por pontos corridos.

    - `legs=1` → turno único; `legs=2` → turno + returno.
    - Com `randomize=True` embaralha os times antes do algoritmo.
    - Com `randomize=False` e `teams_order` fornecido, usa essa ordem exata.
    - `scheduled_at` de cada jogo = `start_date` do campeonato + 1 semana × rodada.
    """
    champ = await _get_champ(db, championship_id)
    await _guard_no_existing_games(db, championship_id)

    enrolled = await _load_enrolled_teams(db, championship_id)
    if len(enrolled) < 2:
        raise ValueError("São necessários ao menos 2 times inscritos para o sorteio")

    enrolled_ids = {t.id for t in enrolled}
    team_map = {t.id: t for t in enrolled}

    # --- define ordem dos times ---
    if not randomize and teams_order:
        validate_teams_order(teams_order, enrolled_ids)
        ordered = [team_map[tid] for tid in teams_order]
    elif randomize:
        ordered = list(enrolled)
        random.shuffle(ordered)
    else:
        ordered = list(enrolled)  # ordem de inscrição como fallback

    base_date = champ.start_date or _now_utc()
    first_leg = round_robin_pairs(ordered)

    games_to_create: list[Game] = []
    # round_number → lista de (home, away) Team objects
    round_pairs: dict[int, list[tuple[Team, Team]]] = {}

    for leg in range(1, legs + 1):
        rounds = first_leg if leg == 1 else [
            [(away, home) for home, away in rnd] for rnd in first_leg
        ]
        for r_idx, pairs in enumerate(rounds):
            round_number = (leg - 1) * len(first_leg) + r_idx + 1
            scheduled_at = base_date + timedelta(weeks=round_number - 1)
            round_pairs[round_number] = []
            for home, away in pairs:
                round_pairs[round_number].append((home, away))
                games_to_create.append(
                    Game(
                        championship_id=championship_id,
                        home_team_id=home.id,
                        away_team_id=away.id,
                        scheduled_at=scheduled_at,
                        status="scheduled",
                        phase="grupo",
                        round_number=round_number,
                    )
                )

    db.add_all(games_to_create)
    await db.flush()
    await db.commit()

    # --- monta resposta agrupada por rodada ---
    g_iter = iter(games_to_create)
    round_details: list[RoundDetail] = []

    for rn in sorted(round_pairs):
        slots: list[GameSlot] = []
        for home, away in round_pairs[rn]:
            g = next(g_iter)
            slots.append(
                GameSlot(
                    game_id=g.id,
                    home_team_id=home.id,
                    home_team_name=home.name,
                    away_team_id=away.id,
                    away_team_name=away.name,
                    scheduled_at=g.scheduled_at,
                    status=g.status,
                )
            )
        round_details.append(RoundDetail(round_number=rn, phase="grupo", games=slots))

    return RoundRobinDrawResponse(
        championship_id=championship_id,
        championship_name=champ.name,
        legs=legs,
        total_rounds=len(round_details),
        total_games=len(games_to_create),
        rounds=round_details,
    )


# ---------------------------------------------------------------------------
# 2. Sorteio eliminatório
# ---------------------------------------------------------------------------

async def execute_elimination_draw(
    db: AsyncSession,
    championship_id: int,
    randomize: bool = True,
    seeded_team_ids: Optional[list[int]] = None,
    teams_order: Optional[list[int]] = None,
) -> BracketResult:
    """
    Gera a chave eliminatória e persiste os jogos da primeira rodada.

    - Cabeças de chave (`seeded_team_ids`) ficam nos seeds 1, 2, 3... garantindo
      que estejam em lados opostos do bracket.
    - `teams_order` define a ordem completa manualmente (ignora tudo mais).
    - BYEs são inseridos automaticamente quando o número de times não é potência de 2.
    - Rodadas seguintes à primeira ficam como placeholders (sem game_id).
    """
    champ = await _get_champ(db, championship_id)
    await _guard_no_existing_games(db, championship_id)

    enrolled = await _load_enrolled_teams(db, championship_id)
    if len(enrolled) < 2:
        raise ValueError("São necessários ao menos 2 times inscritos para o sorteio")

    enrolled_id_list = [t.id for t in enrolled]
    enrolled_ids_set = {t.id for t in enrolled}
    team_map = {t.id: t for t in enrolled}

    # --- define ordem dos seeds ---
    if teams_order is not None:
        validate_teams_order(teams_order, enrolled_ids_set)
        seed_order = teams_order
    elif seeded_team_ids:
        seed_order = apply_heads_seeding(
            enrolled_id_list, seeded_team_ids, randomize_rest=randomize
        )
    elif randomize:
        seed_order = list(enrolled_id_list)
        random.shuffle(seed_order)
    else:
        seed_order = enrolled_id_list

    bracket_size = next_power_of_2(len(seed_order))
    n_byes = bracket_size - len(seed_order)
    seeds: list[Optional[int]] = seed_order + [None] * n_byes  # type: ignore[assignment]

    first_round_pairs = seeded_bracket_pairs(seeds)
    base_date = champ.start_date or _now_utc()
    first_rnd_phase = phase_name(bracket_size // 2)

    # --- primeira rodada: persiste jogos reais ---
    first_round_games: list[BracketGame] = []
    games_to_create: list[Game] = []

    for slot_idx, (home_id, away_id) in enumerate(first_round_pairs, start=1):
        is_bye = home_id is None or away_id is None
        real_home = home_id if home_id is not None else away_id
        real_away = None if is_bye else away_id

        bg = BracketGame(
            slot=slot_idx,
            round_number=1,
            phase=first_rnd_phase,
            home_team_id=real_home,
            home_team_name=team_map[real_home].name if real_home else None,
            away_team_id=real_away,
            away_team_name=team_map[real_away].name if real_away else None,
            is_bye=is_bye,
        )
        first_round_games.append(bg)

        if not is_bye:
            games_to_create.append(
                Game(
                    championship_id=championship_id,
                    home_team_id=real_home,
                    away_team_id=real_away,
                    scheduled_at=base_date,
                    status="scheduled",
                    phase=first_rnd_phase,
                    round_number=1,
                    # slot gravado no extra_data para reconstrução do bracket
                    extra_data={"bracket_slot": slot_idx},
                )
            )

    if games_to_create:
        db.add_all(games_to_create)
        await db.flush()
        await db.commit()

    # associa IDs gerados
    g_iter = iter(games_to_create)
    for bg in first_round_games:
        if not bg.is_bye:
            bg.game_id = next(g_iter).id

    all_rounds: list[BracketRound] = [
        BracketRound(round_number=1, phase=first_rnd_phase, games=first_round_games)
    ]

    # --- rodadas seguintes: placeholders ---
    n_rounds_total = int(math.log2(bracket_size))
    for rnd in range(2, n_rounds_total + 1):
        slots_in_round = bracket_size // (2 ** rnd)
        p = phase_name(slots_in_round)
        all_rounds.append(
            BracketRound(
                round_number=rnd,
                phase=p,
                games=[
                    BracketGame(
                        slot=s,
                        round_number=rnd,
                        phase=p,
                        home_team_id=None,
                        home_team_name="A definir",
                        away_team_id=None,
                        away_team_name="A definir",
                    )
                    for s in range(1, slots_in_round + 1)
                ],
            )
        )

    return BracketResult(
        championship_id=championship_id,
        bracket_size=bracket_size,
        total_byes=n_byes,
        rounds=all_rounds,
    )


# ---------------------------------------------------------------------------
# 3. Consulta do bracket atual
# ---------------------------------------------------------------------------

async def get_championship_bracket(
    db: AsyncSession,
    championship_id: int,
) -> BracketResult:
    """
    Reconstrói o bracket a partir dos jogos existentes no banco.

    Usa `extra_data.bracket_slot` (gravado no sorteio) para ordenar os slots
    dentro de cada rodada. Funciona para campeonatos em andamento.
    """
    await _get_champ(db, championship_id)

    games = (
        await db.execute(
            select(Game)
            .options(selectinload(Game.result))
            .where(Game.championship_id == championship_id)
            .order_by(Game.round_number)
        )
    ).scalars().all()

    if not games:
        raise ValueError("Nenhum jogo encontrado para este campeonato")

    # carrega times referenciados
    team_ids = {gm.home_team_id for gm in games if gm.home_team_id} | \
               {gm.away_team_id for gm in games if gm.away_team_id}
    team_map = await _load_team_map(db, team_ids)

    max_round = max((gm.round_number or 1) for gm in games)
    bracket_size = 2 ** max_round

    # agrupa por rodada
    round_map: dict[int, list[Game]] = {}
    for gm in games:
        rn = gm.round_number or 1
        round_map.setdefault(rn, []).append(gm)

    all_rounds: list[BracketRound] = []
    for rn in sorted(round_map):
        slots_in_round = bracket_size // (2 ** rn)
        p = phase_name(slots_in_round)
        sorted_games = sorted(
            round_map[rn],
            key=lambda g: (g.extra_data or {}).get("bracket_slot", 9999),
        )
        bracket_games = [
            BracketGame(
                slot=(gm.extra_data or {}).get("bracket_slot", idx + 1),
                round_number=rn,
                phase=p,
                home_team_id=gm.home_team_id,
                home_team_name=team_map[gm.home_team_id].name if gm.home_team_id in team_map else None,
                away_team_id=gm.away_team_id,
                away_team_name=team_map[gm.away_team_id].name if gm.away_team_id in team_map else None,
                is_bye=False,
                game_id=gm.id,
            )
            for idx, gm in enumerate(sorted_games)
        ]
        all_rounds.append(BracketRound(round_number=rn, phase=p, games=bracket_games))

    return BracketResult(
        championship_id=championship_id,
        bracket_size=bracket_size,
        total_byes=0,
        rounds=all_rounds,
    )


# ---------------------------------------------------------------------------
# 4. Criação manual de jogo
# ---------------------------------------------------------------------------

async def create_manual_game(
    db: AsyncSession,
    championship_id: int,
    data: ManualGameCreate,
) -> ManualGameResponse:
    """
    Cria um único jogo sem passar pelo sorteio automático.

    Valida que ambos os times estão inscritos no campeonato.
    """
    await _get_champ(db, championship_id)

    enrolled = await _load_enrolled_teams(db, championship_id)
    enrolled_ids = {t.id for t in enrolled}
    team_map = {t.id: t for t in enrolled}

    for tid, label in [(data.home_team_id, "home"), (data.away_team_id, "away")]:
        if tid not in enrolled_ids:
            raise ValueError(
                f"Time {tid} ({label}) não está inscrito neste campeonato"
            )

    game = Game(
        championship_id=championship_id,
        home_team_id=data.home_team_id,
        away_team_id=data.away_team_id,
        scheduled_at=data.scheduled_at,
        venue=data.venue,
        status="scheduled",
        phase=data.phase,
        round_number=data.round_number,
        extra_data=data.extra_data,
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)

    return ManualGameResponse(
        game_id=game.id,
        championship_id=championship_id,
        home_team_id=data.home_team_id,
        home_team_name=team_map[data.home_team_id].name,
        away_team_id=data.away_team_id,
        away_team_name=team_map[data.away_team_id].name,
        scheduled_at=game.scheduled_at,
        venue=game.venue,
        phase=game.phase,
        round_number=game.round_number,
        status=game.status,
    )
