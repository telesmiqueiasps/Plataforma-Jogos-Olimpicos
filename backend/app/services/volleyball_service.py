"""
services/volleyball_service.py
===============================
Lógica de pontuação e classificação para Vôlei.
"""

from functools import cmp_to_key
from typing import Optional


def calculate_match_points(home_sets: int, away_sets: int, best_of: int = 5) -> tuple[int, int]:
    """
    Retorna (pontos_mandante, pontos_visitante) pelo sistema brasileiro de vôlei/tênis de mesa.
    - Melhor de 3: vence quem chegar a 2 sets (2-0 = 3/0 pts; 2-1 = 2/1 pts)
    - Melhor de 5: vence quem chegar a 3 sets (3-0/3-1 = 3/0 pts; 3-2 = 2/1 pts)
    - Melhor de 7: vence quem chegar a 4 sets (4-0/4-1/4-2 = 3/0 pts; 4-3 = 2/1 pts)
    """
    if best_of == 3:
        sets_to_win = 2
    elif best_of == 5:
        sets_to_win = 3
    else:  # best_of == 7
        sets_to_win = 4
    max_close = sets_to_win - 1  # 1 para B3; 2 para B5; 3 para B7

    if home_sets == sets_to_win:
        return (2, 1) if away_sets == max_close else (3, 0)
    if away_sets == sets_to_win:
        return (1, 2) if home_sets == max_close else (0, 3)
    return (0, 0)  # Jogo em andamento ou não finalizado


def calculate_volleyball_standings(
    games: list,
    rules_config: dict,
    team_names: dict,
) -> list:
    """
    Calcula tabela de classificação para vôlei.

    Args:
        games: lista de Game ORM objects com resultado e extra_data
        rules_config: configurações do campeonato incluindo tiebreaker_order
        team_names: {team_id: team_name}

    Retorna lista de dicts com todos os campos necessários para StandingEntry.
    """
    # Configuração de melhor-de (3, 5 ou 7); afeta quantos sets são necessários para vencer
    best_of = int(rules_config.get("best_of", 5))
    if best_of == 3:
        sets_to_win = 2
    elif best_of == 5:
        sets_to_win = 3
    else:  # best_of == 7
        sets_to_win = 4
    max_close = sets_to_win - 1

    # Pontuação configurável (padrão: 3-2-1-0)
    pts_win_easy  = int(rules_config.get("pts_win_easy",  3))   # vitória fácil (ex: 3-0 ou 3-1)
    pts_win_hard  = int(rules_config.get("pts_win_hard",  2))   # vitória apertada (ex: 3-2 ou 2-1)
    pts_loss_close = int(rules_config.get("pts_loss_close", 1)) # derrota apertada
    pts_loss_easy  = int(rules_config.get("pts_loss_easy",  0)) # derrota fácil

    tiebreakers = rules_config.get(
        "tiebreaker_order",
        ["points", "wins", "set_difference", "set_average", "points_average"],
    )

    entry: dict[int, dict] = {
        tid: {
            "team_id":        tid,
            "team_name":      name,
            "games_played":   0,
            "wins":           0,
            "draws":          0,
            "losses":         0,
            "points":         0,
            "sets_won":       0,
            "sets_lost":      0,
            "set_difference": 0,
            "set_average":    0.0,
            "points_scored":  0,
            "points_against": 0,
            "points_average": 0.0,
            # Aliases para compatibilidade com StandingEntry (futsal-style)
            "goals_for":      0,
            "goals_against":  0,
            "goal_diff":      0,
        }
        for tid, name in team_names.items()
    }

    # H2H: h2h[a][b] = {"pts": int, "set_diff": int}
    h2h: dict[int, dict[int, dict]] = {tid: {} for tid in team_names}

    for g in games:
        if not g.result:
            continue

        home_id  = g.home_team_id
        away_id  = g.away_team_id
        home_sets = g.result.home_score
        away_sets = g.result.away_score

        # Determina pontos do jogo por resultado (usa sets_to_win dinâmico)
        if home_sets == sets_to_win:
            if away_sets == max_close:
                home_pts, away_pts = pts_win_hard, pts_loss_close
            else:
                home_pts, away_pts = pts_win_easy, pts_loss_easy
        elif away_sets == sets_to_win:
            if home_sets == max_close:
                home_pts, away_pts = pts_loss_close, pts_win_hard
            else:
                home_pts, away_pts = pts_loss_easy, pts_win_easy
        else:
            home_pts, away_pts = 0, 0

        # Pontos individuais (parciais dos sets) do extra_data do jogo
        extra_g    = g.extra_data or {}
        vball_data = extra_g.get("volleyball", {})
        sets_detail = vball_data.get("sets", [])

        home_pts_scored = sum(s.get("home_points", 0) for s in sets_detail)
        away_pts_scored = sum(s.get("away_points", 0) for s in sets_detail)

        for tid, opp, sets_w, sets_l, pts_earned, pts_s, pts_a in [
            (home_id, away_id, home_sets, away_sets, home_pts, home_pts_scored, away_pts_scored),
            (away_id, home_id, away_sets, home_sets, away_pts, away_pts_scored, home_pts_scored),
        ]:
            if tid not in entry:
                continue
            e = entry[tid]
            e["games_played"]   += 1
            e["sets_won"]       += sets_w
            e["sets_lost"]      += sets_l
            e["points"]         += pts_earned
            e["points_scored"]  += pts_s
            e["points_against"] += pts_a
            if pts_earned >= pts_win_hard:   # 2 ou 3 pts = vitória
                e["wins"] += 1
            else:
                e["losses"] += 1

        # Registra H2H
        for tid_a, tid_b, pts_a_val, sd_a in [
            (home_id, away_id, home_pts, home_sets - away_sets),
            (away_id, home_id, away_pts, away_sets - home_sets),
        ]:
            if tid_a not in h2h:
                continue
            if tid_b not in h2h[tid_a]:
                h2h[tid_a][tid_b] = {"pts": 0, "set_diff": 0}
            h2h[tid_a][tid_b]["pts"]      += pts_a_val
            h2h[tid_a][tid_b]["set_diff"] += sd_a

    # Finaliza campos calculados
    for e in entry.values():
        e["set_difference"] = e["sets_won"] - e["sets_lost"]
        e["set_average"]    = (
            e["sets_won"] / e["sets_lost"] if e["sets_lost"] > 0
            else float(e["sets_won"])
        )
        e["points_average"] = (
            e["points_scored"] / e["points_against"] if e["points_against"] > 0
            else float(e["points_scored"])
        )
        # Aliases
        e["goals_for"]     = e["sets_won"]
        e["goals_against"] = e["sets_lost"]
        e["goal_diff"]     = e["set_difference"]

    def compare(a: dict, b: dict) -> int:
        for tb in tiebreakers:
            if tb == "points":
                diff = b["points"] - a["points"]
            elif tb == "wins":
                diff = b["wins"] - a["wins"]
            elif tb == "set_difference":
                diff = b["set_difference"] - a["set_difference"]
            elif tb == "set_average":
                diff_f = b["set_average"] - a["set_average"]
                diff = 1 if diff_f > 0 else (-1 if diff_f < 0 else 0)
            elif tb == "points_average":
                diff_f = b["points_average"] - a["points_average"]
                diff = 1 if diff_f > 0 else (-1 if diff_f < 0 else 0)
            elif tb == "head_to_head":
                ap = h2h.get(a["team_id"], {}).get(b["team_id"], {}).get("pts", 0)
                bp = h2h.get(b["team_id"], {}).get(a["team_id"], {}).get("pts", 0)
                diff = bp - ap
                if diff == 0:
                    ag = h2h.get(a["team_id"], {}).get(b["team_id"], {}).get("set_diff", 0)
                    bg = h2h.get(b["team_id"], {}).get(a["team_id"], {}).get("set_diff", 0)
                    diff = bg - ag
            else:
                diff = 0
            if diff != 0:
                return diff
        return 0

    sorted_list = sorted(entry.values(), key=cmp_to_key(compare))
    for i, e in enumerate(sorted_list):
        e["position"] = i + 1
    return sorted_list
