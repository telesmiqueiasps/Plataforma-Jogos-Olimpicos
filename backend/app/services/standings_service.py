"""
standings_service.py
====================
Serviço responsável por:
  - Calcular tabela de classificação com critérios configuráveis (calculate_standings)
  - Gerar calendário round-robin (generate_round_robin_schedule)
  - Gerar chave eliminatória com BYEs (generate_elimination_bracket)
  - Verificar e criar suspensões automáticas (check_suspensions)

Usa SQLAlchemy async (asyncpg). Todas as funções públicas recebem
uma AsyncSession já aberta — o chamador (rota ou test) gerencia o ciclo de vida.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import cmp_to_key
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Athlete,
    Championship,
    ChampionshipTeam,
    Game,
    GameEvent,
    GameResult,
    Suspension,
    Team,
)
from app.schemas.standings import (
    BracketGame,
    BracketResult,
    BracketRound,
    MatchupSlot,
    ScheduleResult,
    StandingEntry,
    StandingsResult,
    SuspensionCreated,
)

# ---------------------------------------------------------------------------
# Constantes / defaults do rules_config
# ---------------------------------------------------------------------------

_D_POINTS_WIN   = 3
_D_POINTS_DRAW  = 1
_D_POINTS_LOSS  = 0
_D_TIEBREAKERS  = ["points", "wins", "goal_difference", "goals_scored"]

_D_YELLOW_THRESHOLD       = 3   # cartões para gerar suspensão
_D_YELLOW_SUSPENSION_GAMES = 1
_D_RED_SUSPENSION_GAMES    = 1

_PHASE_NAMES = {
    1: "final",
    2: "semifinal",
    4: "quarterfinal",
    8: "round_of_16",
    16: "round_of_32",
}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _next_power_of_2(n: int) -> int:
    if n <= 1:
        return 1
    return 2 ** math.ceil(math.log2(n))


def _phase_name(remaining_slots: int) -> str:
    """Converte nº de slots restantes no nome da fase."""
    return _PHASE_NAMES.get(remaining_slots, f"round_of_{remaining_slots * 2}")


class _TeamStats:
    """Acumulador de estatísticas para um time num campeonato."""

    __slots__ = (
        "team_id", "team_name",
        "wins", "draws", "losses",
        "goals_for", "goals_against",
    )

    def __init__(self, team_id: int, team_name: str):
        self.team_id = team_id
        self.team_name = team_name
        self.wins = self.draws = self.losses = 0
        self.goals_for = self.goals_against = 0

    @property
    def games_played(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def points(self, pts_win: int, pts_draw: int, pts_loss: int) -> int:
        return self.wins * pts_win + self.draws * pts_draw + self.losses * pts_loss


class _H2HRecord:
    """Resultado acumulado de confrontos diretos entre dois times."""

    __slots__ = ("points", "gf", "ga")

    def __init__(self):
        self.points = self.gf = self.ga = 0


# ---------------------------------------------------------------------------
# 1. calculate_standings
# ---------------------------------------------------------------------------

async def calculate_standings(
    db: AsyncSession,
    championship_id: int,
) -> StandingsResult:
    """
    Calcula a tabela de classificação do campeonato.

    Critérios de desempate são lidos de championship.rules_config:
      - points_win          (default 3)
      - points_draw         (default 1)
      - points_loss         (default 0)
      - tiebreaker_order    (default ["points","wins","goal_difference","goals_scored"])
        Valores aceitos: "points", "wins", "draws", "losses",
                         "goal_difference", "goals_scored", "goals_against",
                         "head_to_head"
    """
    # --- carrega campeonato ---
    champ = await db.get(Championship, championship_id)
    if champ is None:
        raise ValueError(f"Campeonato {championship_id} não encontrado")

    cfg = champ.rules_config or {}
    pts_win  = cfg.get("points_win",  _D_POINTS_WIN)
    pts_draw = cfg.get("points_draw", _D_POINTS_DRAW)
    pts_loss = cfg.get("points_loss", _D_POINTS_LOSS)
    tiebreakers: list[str] = cfg.get("tiebreaker_order", _D_TIEBREAKERS)

    # --- times inscritos ---
    ct_rows = (
        await db.execute(
            select(ChampionshipTeam)
            .options(selectinload(ChampionshipTeam.team))
            .where(ChampionshipTeam.championship_id == championship_id)
        )
    ).scalars().all()

    stats: dict[int, _TeamStats] = {
        ct.team_id: _TeamStats(ct.team_id, ct.team.name) for ct in ct_rows
    }

    # h2h[team_a][team_b] = _H2HRecord (resultados de team_a contra team_b)
    h2h: dict[int, dict[int, _H2HRecord]] = defaultdict(lambda: defaultdict(_H2HRecord))

    # --- jogos encerrados ---
    games_q = (
        await db.execute(
            select(Game)
            .options(selectinload(Game.result))
            .where(
                Game.championship_id == championship_id,
                Game.status == "finished",
            )
        )
    ).scalars().all()

    for game in games_q:
        result = game.result
        if result is None:
            continue

        hs = result.home_score
        as_ = result.away_score
        home_id = game.home_team_id
        away_id = game.away_team_id

        # ignora times não inscritos (dados inconsistentes)
        if home_id not in stats or away_id not in stats:
            continue

        # --- acumula stats gerais ---
        stats[home_id].goals_for      += hs
        stats[home_id].goals_against  += as_
        stats[away_id].goals_for      += as_
        stats[away_id].goals_against  += hs

        if hs > as_:
            stats[home_id].wins   += 1
            stats[away_id].losses += 1
        elif hs < as_:
            stats[away_id].wins   += 1
            stats[home_id].losses += 1
        else:
            stats[home_id].draws += 1
            stats[away_id].draws += 1

        # --- acumula head-to-head ---
        home_pts = pts_win if hs > as_ else (pts_draw if hs == as_ else pts_loss)
        away_pts = pts_win if as_ > hs else (pts_draw if as_ == hs else pts_loss)

        h2h[home_id][away_id].gf      += hs
        h2h[home_id][away_id].ga      += as_
        h2h[home_id][away_id].points  += home_pts

        h2h[away_id][home_id].gf      += as_
        h2h[away_id][home_id].ga      += hs
        h2h[away_id][home_id].points  += away_pts

    # --- monta entradas ---
    entries: list[StandingEntry] = []
    for s in stats.values():
        pts = s.points(pts_win, pts_draw, pts_loss)
        entries.append(
            StandingEntry(
                position=0,         # preenchido após sort
                team_id=s.team_id,
                team_name=s.team_name,
                games_played=s.games_played,
                wins=s.wins,
                draws=s.draws,
                losses=s.losses,
                goals_for=s.goals_for,
                goals_against=s.goals_against,
                goal_difference=s.goal_difference,
                points=pts,
            )
        )

    # --- ordena ---
    entries = _sort_standings(entries, tiebreakers, h2h, pts_win, pts_draw, pts_loss)

    for i, entry in enumerate(entries, start=1):
        entry.position = i

    return StandingsResult(
        championship_id=championship_id,
        championship_name=champ.name,
        entries=entries,
    )


def _sort_standings(
    entries: list[StandingEntry],
    tiebreakers: list[str],
    h2h: dict,
    pts_win: int,
    pts_draw: int,
    pts_loss: int,
) -> list[StandingEntry]:
    """
    Ordena as entradas aplicando os critérios em sequência.
    "head_to_head" é tratado como confronto direto pairwise usando cmp_to_key.
    """
    def _cmp(a: StandingEntry, b: StandingEntry) -> int:
        for criterion in tiebreakers:
            diff = _criterion_diff(a, b, criterion, h2h)
            if diff != 0:
                return diff
        return 0

    return sorted(entries, key=cmp_to_key(_cmp))


def _criterion_diff(a: StandingEntry, b: StandingEntry, criterion: str, h2h: dict) -> int:
    """
    Retorna valor negativo se a > b (a deve vir antes), positivo se b > a.
    Convenção: maior é melhor para todos os critérios.
    """
    if criterion == "points":
        return b.points - a.points
    if criterion == "wins":
        return b.wins - a.wins
    if criterion == "draws":
        return b.draws - a.draws
    if criterion == "losses":
        # menos derrotas é melhor → a é melhor se a.losses < b.losses
        return a.losses - b.losses
    if criterion == "goal_difference":
        return b.goal_difference - a.goal_difference
    if criterion == "goals_scored":
        return b.goals_for - a.goals_for
    if criterion == "goals_against":
        # menos gols sofridos é melhor
        return a.goals_against - b.goals_against
    if criterion == "head_to_head":
        return _h2h_diff(a, b, h2h)
    return 0


def _h2h_diff(a: StandingEntry, b: StandingEntry, h2h: dict) -> int:
    """Compara confrontos diretos entre dois times (pairwise)."""
    rec_a = h2h.get(a.team_id, {}).get(b.team_id)
    rec_b = h2h.get(b.team_id, {}).get(a.team_id)

    pts_a = rec_a.points if rec_a else 0
    pts_b = rec_b.points if rec_b else 0
    if pts_a != pts_b:
        return pts_b - pts_a  # maior pontuação h2h vem primeiro

    gd_a = (rec_a.gf - rec_a.ga) if rec_a else 0
    gd_b = (rec_b.gf - rec_b.ga) if rec_b else 0
    if gd_a != gd_b:
        return gd_b - gd_a

    gf_a = rec_a.gf if rec_a else 0
    gf_b = rec_b.gf if rec_b else 0
    return gf_b - gf_a


# ---------------------------------------------------------------------------
# 2. generate_round_robin_schedule
# ---------------------------------------------------------------------------

async def generate_round_robin_schedule(
    db: AsyncSession,
    championship_id: int,
    randomize: bool = True,
    legs: int = 2,
) -> ScheduleResult:
    """
    Gera o calendário completo de um campeonato por pontos corridos.

    Parâmetros
    ----------
    legs : int
        1 = turno único  |  2 = turno + returno (padrão)

    O algoritmo circle-method garante que cada par de times se encontre
    exatamente uma vez por turno. Quando `randomize=True`, a ordem dos
    times é embaralhada antes de gerar as rodadas (mas preserva o
    algoritmo determinístico dentro de cada geração).

    Os jogos são persistidos com `scheduled_at` igual ao `start_date` do
    campeonato + 7 dias por rodada (placeholder; o organizador pode
    reagendar depois).
    """
    champ = await db.get(Championship, championship_id)
    if champ is None:
        raise ValueError(f"Campeonato {championship_id} não encontrado")

    ct_rows = (
        await db.execute(
            select(ChampionshipTeam)
            .options(selectinload(ChampionshipTeam.team))
            .where(ChampionshipTeam.championship_id == championship_id)
        )
    ).scalars().all()

    if len(ct_rows) < 2:
        raise ValueError("É necessário pelo menos 2 times para gerar calendário")

    teams = [ct.team for ct in ct_rows]
    if randomize:
        random.shuffle(teams)

    # base para datas
    base_date = champ.start_date or _now_utc()

    # gera pares por turno
    first_leg_rounds = _round_robin_pairs(teams)

    all_matchups: list[MatchupSlot] = []
    games_to_create: list[Game] = []

    for leg in range(1, legs + 1):
        rounds = first_leg_rounds if leg == 1 else [
            [(away, home) for home, away in rnd] for rnd in first_leg_rounds
        ]
        for round_idx, pairs in enumerate(rounds):
            round_number = (leg - 1) * len(first_leg_rounds) + round_idx + 1
            scheduled_at = base_date + timedelta(weeks=round_number - 1)

            for home, away in pairs:
                slot = MatchupSlot(
                    round_number=round_number,
                    phase="grupo",
                    home_team_id=home.id,
                    home_team_name=home.name,
                    away_team_id=away.id,
                    away_team_name=away.name,
                )
                all_matchups.append(slot)

                game = Game(
                    championship_id=championship_id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    scheduled_at=scheduled_at,
                    status="scheduled",
                    phase="grupo",
                    round_number=round_number,
                )
                games_to_create.append(game)

    db.add_all(games_to_create)
    await db.flush()          # popula os IDs sem commitar
    await db.commit()

    return ScheduleResult(
        championship_id=championship_id,
        total_rounds=len(all_matchups) // max(len(teams) // 2, 1),
        total_games=len(games_to_create),
        games_created=[g.id for g in games_to_create],
        matchups=all_matchups,
    )


def _round_robin_pairs(teams: list) -> list[list[tuple]]:
    """
    Algoritmo circle-method.
    Retorna lista de rodadas; cada rodada é lista de (home, away).
    Se `n` for ímpar, insere None (BYE) e ignora pares que o contêm.
    """
    pool = list(teams)
    if len(pool) % 2 == 1:
        pool.append(None)   # BYE

    n = len(pool)
    rounds: list[list[tuple]] = []

    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            home = pool[i]
            away = pool[n - 1 - i]
            if home is not None and away is not None:
                pairs.append((home, away))
        rounds.append(pairs)
        # rotaciona tudo exceto pool[0]
        pool = [pool[0]] + [pool[-1]] + pool[1:-1]

    return rounds


# ---------------------------------------------------------------------------
# 3. generate_elimination_bracket
# ---------------------------------------------------------------------------

async def generate_elimination_bracket(
    db: AsyncSession,
    championship_id: int,
    teams_list: list[int],      # lista ordenada de team_ids (seed 1, seed 2, ...)
) -> BracketResult:
    """
    Gera chave eliminatória completa.

    - Calcula a próxima potência de 2 >= len(teams_list).
    - Distribui BYEs automaticamente (seeds mais altos recebem BYEs para
      que os melhores times se encontrem apenas nas fases finais).
    - Cria os jogos da primeira rodada no banco; rodadas seguintes ficam
      como placeholder (game_id=None) — são criadas conforme os resultados
      são registrados.
    """
    champ = await db.get(Championship, championship_id)
    if champ is None:
        raise ValueError(f"Campeonato {championship_id} não encontrado")

    if len(teams_list) < 2:
        raise ValueError("São necessários ao menos 2 times para o bracket")

    # carrega times
    team_rows = (
        await db.execute(select(Team).where(Team.id.in_(teams_list)))
    ).scalars().all()
    team_map: dict[int, Team] = {t.id: t for t in team_rows}

    bracket_size = _next_power_of_2(len(teams_list))
    n_byes = bracket_size - len(teams_list)

    # preenche a lista de seeds com None (BYE) no final
    seeds: list[Optional[int]] = list(teams_list) + [None] * n_byes

    # monta pares da primeira rodada com seeding padrão (1 vs last, 2 vs penultimate, ...)
    first_round_pairs = _seeded_bracket_pairs(seeds)

    base_date = champ.start_date or _now_utc()
    all_rounds: list[BracketRound] = []

    # --- Primeira rodada: persiste no banco ---
    first_round_games: list[BracketGame] = []
    games_to_create: list[Game] = []
    phase = _phase_name(bracket_size // 2)

    for slot_idx, (home_id, away_id) in enumerate(first_round_pairs, start=1):
        is_bye = home_id is None or away_id is None
        real_home = home_id if home_id is not None else away_id   # quem avança direto
        real_away = None if is_bye else away_id

        bg = BracketGame(
            slot=slot_idx,
            round_number=1,
            phase=phase,
            home_team_id=real_home,
            home_team_name=team_map[real_home].name if real_home else None,
            away_team_id=real_away,
            away_team_name=team_map[real_away].name if real_away else None,
            is_bye=is_bye,
        )
        first_round_games.append(bg)

        if not is_bye:
            game = Game(
                championship_id=championship_id,
                home_team_id=real_home,
                away_team_id=real_away,
                scheduled_at=base_date,
                status="scheduled",
                phase=phase,
                round_number=1,
            )
            games_to_create.append(game)

    if games_to_create:
        db.add_all(games_to_create)
        await db.flush()
        await db.commit()

    # associa IDs persistidos
    g_iter = iter(games_to_create)
    for bg in first_round_games:
        if not bg.is_bye:
            bg.game_id = next(g_iter).id

    all_rounds.append(BracketRound(round_number=1, phase=phase, games=first_round_games))

    # --- Rodadas seguintes: apenas placeholders ---
    n_rounds_total = int(math.log2(bracket_size))
    for rnd in range(2, n_rounds_total + 1):
        slots_in_round = bracket_size // (2 ** rnd)
        phase = _phase_name(slots_in_round)
        placeholder_games = [
            BracketGame(
                slot=s,
                round_number=rnd,
                phase=phase,
                home_team_id=None,
                home_team_name="A definir",
                away_team_id=None,
                away_team_name="A definir",
            )
            for s in range(1, slots_in_round + 1)
        ]
        all_rounds.append(BracketRound(round_number=rnd, phase=phase, games=placeholder_games))

    return BracketResult(
        championship_id=championship_id,
        bracket_size=bracket_size,
        total_byes=n_byes,
        rounds=all_rounds,
    )


def _seeded_bracket_pairs(seeds: list[Optional[int]]) -> list[tuple[Optional[int], Optional[int]]]:
    """
    Emparelha seeds na ordem padrão: seed[0] vs seed[-1], seed[1] vs seed[-2], ...
    Garante que os melhores times só se encontrem nas finais.
    """
    pairs = []
    left, right = 0, len(seeds) - 1
    while left < right:
        pairs.append((seeds[left], seeds[right]))
        left += 1
        right -= 1
    return pairs


# ---------------------------------------------------------------------------
# 4. check_suspensions
# ---------------------------------------------------------------------------

async def check_suspensions(
    db: AsyncSession,
    game_id: int,
) -> list[SuspensionCreated]:
    """
    Verifica e cria suspensões automáticas após o registro de resultado de um jogo.

    Regras lidas de championship.rules_config:
      - yellow_card_threshold        (default 3): nº de amarelos que gera suspensão
      - yellow_card_suspension_games (default 1): jogos de suspensão por acúmulo
      - red_card_suspension_games    (default 1): jogos de suspensão por vermelho

    Idempotência:
      - Cartão vermelho: verifica se já existe suspensão com tag [red:game_id:athlete_id]
      - Acúmulo de amarelos: compara `floor(total_yellows / threshold)` com o nº de
        suspensões por amarelo já existentes para o atleta no campeonato.

    Retorna lista de SuspensionCreated com o que foi criado nesta chamada.
    """
    # --- carrega jogo com campeonato ---
    game = await db.get(Game, game_id)
    if game is None:
        raise ValueError(f"Jogo {game_id} não encontrado")

    champ = await db.get(Championship, game.championship_id)
    cfg = champ.rules_config or {}

    yellow_threshold   = cfg.get("yellow_card_threshold",        _D_YELLOW_THRESHOLD)
    yellow_susp_games  = cfg.get("yellow_card_suspension_games", _D_YELLOW_SUSPENSION_GAMES)
    red_susp_games     = cfg.get("red_card_suspension_games",    _D_RED_SUSPENSION_GAMES)

    # --- eventos deste jogo (apenas cartões) ---
    events = (
        await db.execute(
            select(GameEvent)
            .options(selectinload(GameEvent.athlete))
            .where(
                GameEvent.game_id == game_id,
                GameEvent.event_type.in_(["yellow_card", "red_card"]),
            )
        )
    ).scalars().all()

    if not events:
        return []

    athlete_ids = {ev.athlete_id for ev in events if ev.athlete_id is not None}
    if not athlete_ids:
        return []

    # --- pre-carrega atletas (para nome) ---
    athletes_map: dict[int, Athlete] = {
        a.id: a
        for a in (
            await db.execute(select(Athlete).where(Athlete.id.in_(athlete_ids)))
        ).scalars().all()
    }

    # --- jogos encerrados do campeonato (para contar amarelos históricos) ---
    finished_game_ids_q = await db.execute(
        select(Game.id).where(
            Game.championship_id == game.championship_id,
            Game.status == "finished",
        )
    )
    finished_game_ids = [row[0] for row in finished_game_ids_q.fetchall()]

    created: list[SuspensionCreated] = []

    for athlete_id in athlete_ids:
        athlete = athletes_map.get(athlete_id)
        if athlete is None:
            continue

        # ---- Cartão vermelho ----
        red_events_this_game = [
            ev for ev in events
            if ev.athlete_id == athlete_id and ev.event_type == "red_card"
        ]
        for ev in red_events_this_game:
            tag = f"[red:game={game_id}:event={ev.id}]"
            already = (
                await db.execute(
                    select(func.count(Suspension.id)).where(
                        Suspension.athlete_id == athlete_id,
                        Suspension.championship_id == game.championship_id,
                        Suspension.reason.contains(tag),
                    )
                )
            ).scalar_one()

            if already == 0:
                susp = Suspension(
                    athlete_id=athlete_id,
                    championship_id=game.championship_id,
                    games_remaining=red_susp_games,
                    reason=f"Cartão vermelho {tag}",
                    auto_generated=True,
                )
                db.add(susp)
                created.append(
                    SuspensionCreated(
                        athlete_id=athlete_id,
                        athlete_name=athlete.name,
                        championship_id=game.championship_id,
                        games_remaining=red_susp_games,
                        reason=susp.reason,
                    )
                )

        # ---- Acúmulo de cartões amarelos ----
        # total histórico de amarelos do atleta em todos os jogos encerrados
        total_yellows: int = (
            await db.execute(
                select(func.count(GameEvent.id)).where(
                    GameEvent.athlete_id == athlete_id,
                    GameEvent.event_type == "yellow_card",
                    GameEvent.game_id.in_(finished_game_ids),
                )
            )
        ).scalar_one()

        expected_yellow_susps = total_yellows // yellow_threshold

        # suspensões por amarelo já criadas
        existing_yellow_susps: int = (
            await db.execute(
                select(func.count(Suspension.id)).where(
                    Suspension.athlete_id == athlete_id,
                    Suspension.championship_id == game.championship_id,
                    Suspension.auto_generated == True,      # noqa: E712
                    Suspension.reason.like("%amarelo%"),
                )
            )
        ).scalar_one()

        new_yellow_susps = expected_yellow_susps - existing_yellow_susps

        for n in range(new_yellow_susps):
            accumulation = existing_yellow_susps + n + 1
            susp = Suspension(
                athlete_id=athlete_id,
                championship_id=game.championship_id,
                games_remaining=yellow_susp_games,
                reason=(
                    f"Suspensão automática: {accumulation}º acúmulo de cartão amarelo "
                    f"(a cada {yellow_threshold} amarelos) [game={game_id}]"
                ),
                auto_generated=True,
            )
            db.add(susp)
            created.append(
                SuspensionCreated(
                    athlete_id=athlete_id,
                    athlete_name=athlete.name,
                    championship_id=game.championship_id,
                    games_remaining=yellow_susp_games,
                    reason=susp.reason,
                )
            )

    if created:
        await db.commit()

    return created
