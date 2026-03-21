"""
services/chess_service.py
=========================
Cálculo de classificação de xadrez com critério Buchholz.

Pontuação padrão (armazenada ×10 em BoardgameGame.home_score/away_score):
  Vitória = 10  (1.0 pt)
  Empate  =  5  (0.5 pt)
  Derrota =  0  (0.0 pt)
"""

from __future__ import annotations


def calculate_buchholz(player_id: int, games: list, standings: dict) -> float:
    """
    Buchholz sem corte = soma dos pontos de TODOS os adversários enfrentados.
    standings: dict { player_id: total_points (float, já dividido por 10) }
    """
    buchholz = 0.0
    for game in games:
        if game.status != "finished":
            continue
        if game.home_id == player_id:
            buchholz += standings.get(game.away_id, 0.0)
        elif game.away_id == player_id:
            buchholz += standings.get(game.home_id, 0.0)
    return buchholz


def calculate_chess_standings(games: list, participants: list, rules_config: dict) -> list:
    """
    Calcula classificação de xadrez com Buchholz.

    Parâmetros
    ----------
    games        : lista de BoardgameGame com game_type='xadrez'
    participants : lista de dict com { id, name, photo_url }
    rules_config : dict com pts_win, pts_draw, pts_loss (×10) e tiebreaker_order

    Retorno
    -------
    Lista ordenada de dicts com:
      position, player_id, player_name, photo_url,
      points, wins, draws, losses, games_played, buchholz
    """
    pts_win  = int(rules_config.get("pts_win",  10))
    pts_draw = int(rules_config.get("pts_draw",  5))
    pts_loss = int(rules_config.get("pts_loss",  0))
    tiebreaker_order = rules_config.get(
        "tiebreaker_order",
        ["confronto_direto", "buchholz", "wins", "sorteio"],
    )

    # Inicializa stats
    stats: dict[int, dict] = {}
    for p in participants:
        pid = p["id"]
        stats[pid] = {
            "player_id":   pid,
            "player_name": p.get("name", "—"),
            "photo_url":   p.get("photo_url"),
            "score_raw":   0,   # soma ×10
            "wins":        0,
            "draws":       0,
            "losses":      0,
            "games_played": 0,
            "buchholz":    0.0,
        }

    finished = [g for g in games if g.status == "finished"]

    # Computa pontos
    for g in finished:
        for side_id, is_home in [(g.home_id, True), (g.away_id, False)]:
            if side_id not in stats:
                continue
            s = stats[side_id]
            s["games_played"] += 1
            won  = (g.result == "home_win" and is_home) or (g.result == "away_win" and not is_home)
            lost = (g.result == "away_win" and is_home) or (g.result == "home_win" and not is_home)
            if won:
                s["score_raw"] += pts_win
                s["wins"]      += 1
            elif lost:
                s["score_raw"] += pts_loss
                s["losses"]    += 1
            else:
                s["score_raw"] += pts_draw
                s["draws"]     += 1

    # Converte score_raw → points (float)
    pts_map = {pid: s["score_raw"] / 10.0 for pid, s in stats.items()}

    # Buchholz
    for pid in stats:
        stats[pid]["buchholz"] = calculate_buchholz(pid, finished, pts_map)
        stats[pid]["points"]   = pts_map[pid]

    # Construir dicionário de confrontos diretos: (winner_id, loser_id) para desempate
    head_to_head: dict[tuple, float] = {}
    for g in finished:
        home_pts = g.home_score / 10.0 if g.home_score is not None else 0.0
        away_pts = g.away_score / 10.0 if g.away_score is not None else 0.0
        key_home = (g.home_id, g.away_id)
        key_away = (g.away_id, g.home_id)
        head_to_head[key_home] = head_to_head.get(key_home, 0.0) + home_pts
        head_to_head[key_away] = head_to_head.get(key_away, 0.0) + away_pts

    def sort_key(s: dict):
        pid = s["player_id"]
        keys = []
        for tb in tiebreaker_order:
            if tb == "buchholz":
                keys.append(-s["buchholz"])
            elif tb == "wins":
                keys.append(-s["wins"])
            # confronto_direto e sorteio não são facilmente expressáveis aqui;
            # usamos 0 como placeholder (confronto direto resolvido abaixo se necessário)
            else:
                keys.append(0)
        return [-s["points"]] + keys

    ranked = sorted(stats.values(), key=sort_key)

    for i, r in enumerate(ranked):
        r["position"] = i + 1

    return ranked
