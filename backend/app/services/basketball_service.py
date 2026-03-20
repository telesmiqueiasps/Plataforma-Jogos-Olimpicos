"""
services/basketball_service.py
===============================
Lógica de pontuação e classificação para Basquete.
"""

from functools import cmp_to_key


def calculate_match_points_table(home_score: int, away_score: int) -> tuple[int, int]:
    """
    Pontuação na tabela: vitória=2, derrota=1.
    Empate não ocorre em basquete (prorrogação decide), mas é tratado como fallback.
    """
    if home_score > away_score:
        return (2, 1)
    if away_score > home_score:
        return (1, 2)
    return (1, 1)  # fallback empate


def is_sudden_death(home_score: int, away_score: int, rules_config: dict) -> bool:
    """Verifica se algum time atingiu a pontuação de morte súbita no tempo normal."""
    threshold = int(rules_config.get("sudden_death_points", 21))
    return home_score >= threshold or away_score >= threshold


def calculate_basketball_standings(
    games: list,
    rules_config: dict,
    team_names: dict,
) -> list:
    """
    Calcula tabela de classificação para basquete.

    Args:
        games: lista de Game ORM objects com resultado e extra_data
        rules_config: configurações do campeonato incluindo tiebreaker_order
        team_names: {team_id: team_name}

    Campos extras por time:
    - points_scored: total de pontos marcados em todos os jogos
    - points_against: total de pontos sofridos
    - point_difference: saldo de pontos (scored - against)
    - wins, losses
    - points: pontos na tabela (2 por vitória, 1 por derrota, 0 por WO)

    Retorna lista de dicts com todos os campos necessários para StandingEntry.
    """
    pts_win  = int(rules_config.get("pts_win",  2))
    pts_loss = int(rules_config.get("pts_loss", 1))
    pts_wo   = int(rules_config.get("pts_wo",   0))

    tiebreakers = rules_config.get(
        "tiebreaker_order",
        ["table_points", "wins", "point_difference", "points_scored"],
    )

    entry: dict[int, dict] = {
        tid: {
            "team_id":          tid,
            "team_name":        name,
            "games_played":     0,
            "wins":             0,
            "draws":            0,
            "losses":           0,
            "points":           0,
            "points_scored":    0,
            "points_against":   0,
            "point_difference": 0,
            # Aliases para compatibilidade com StandingEntry
            "goals_for":        0,
            "goals_against":    0,
            "goal_diff":        0,
        }
        for tid, name in team_names.items()
    }

    # H2H: h2h[a][b] = {"pts": int, "pd": int}
    h2h: dict[int, dict[int, dict]] = {tid: {} for tid in team_names}

    for g in games:
        if not g.result:
            continue

        home_id    = g.home_team_id
        away_id    = g.away_team_id
        home_score = g.result.home_score
        away_score = g.result.away_score

        extra  = g.extra_data or {}
        bball  = extra.get("basketball", {})
        is_wo  = bball.get("wo", False)

        if is_wo:
            if home_score > away_score:
                home_table, away_table = pts_win, pts_wo
            else:
                home_table, away_table = pts_wo, pts_win
        else:
            home_table, away_table = calculate_match_points_table(home_score, away_score)

        for tid, gf, ga, tab_pts in [
            (home_id, home_score, away_score, home_table),
            (away_id, away_score, home_score, away_table),
        ]:
            if tid not in entry:
                continue
            e = entry[tid]
            e["games_played"]   += 1
            e["points_scored"]  += gf
            e["points_against"] += ga
            e["points"]         += tab_pts
            if tab_pts >= pts_win:
                e["wins"] += 1
            else:
                e["losses"] += 1

        # Registra H2H
        for tid_a, tid_b, pts_a_val, pd_a in [
            (home_id, away_id, home_table, home_score - away_score),
            (away_id, home_id, away_table, away_score - home_score),
        ]:
            if tid_a not in h2h:
                continue
            if tid_b not in h2h[tid_a]:
                h2h[tid_a][tid_b] = {"pts": 0, "pd": 0}
            h2h[tid_a][tid_b]["pts"] += pts_a_val
            h2h[tid_a][tid_b]["pd"]  += pd_a

    # Finaliza campos calculados
    for e in entry.values():
        e["point_difference"] = e["points_scored"] - e["points_against"]
        e["goals_for"]        = e["points_scored"]
        e["goals_against"]    = e["points_against"]
        e["goal_diff"]        = e["point_difference"]

    def compare(a: dict, b: dict) -> int:
        for tb in tiebreakers:
            if tb in ("table_points", "points"):
                diff = b["points"] - a["points"]
            elif tb == "wins":
                diff = b["wins"] - a["wins"]
            elif tb in ("point_difference", "saldo_pontos"):
                diff = b["point_difference"] - a["point_difference"]
            elif tb in ("points_scored", "pontos_convertidos"):
                diff = b["points_scored"] - a["points_scored"]
            elif tb in ("points_against", "pontos_sofridos"):
                # Menos pontos sofridos = melhor
                diff = a["points_against"] - b["points_against"]
            elif tb in ("head_to_head", "confronto_direto"):
                ap = h2h.get(a["team_id"], {}).get(b["team_id"], {}).get("pts", 0)
                bp = h2h.get(b["team_id"], {}).get(a["team_id"], {}).get("pts", 0)
                diff = bp - ap
                if diff == 0:
                    apd = h2h.get(a["team_id"], {}).get(b["team_id"], {}).get("pd", 0)
                    bpd = h2h.get(b["team_id"], {}).get(a["team_id"], {}).get("pd", 0)
                    diff = bpd - apd
            else:
                diff = 0
            if diff != 0:
                return diff
        return 0

    sorted_list = sorted(entry.values(), key=cmp_to_key(compare))
    for i, e in enumerate(sorted_list):
        e["position"] = i + 1
    return sorted_list
