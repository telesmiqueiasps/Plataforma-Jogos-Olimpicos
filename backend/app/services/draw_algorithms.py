"""
draw_algorithms.py
==================
Funções puramente algorítmicas para sorteio de campeonatos.

Sem nenhuma dependência de banco de dados — ideais para testes unitários.
Todas as funções são determinísticas quando `random` não é chamado.
"""

from __future__ import annotations

import math
import random
from typing import Optional

# ---------------------------------------------------------------------------
# Fases de uma chave eliminatória
# ---------------------------------------------------------------------------

_PHASE_NAMES: dict[int, str] = {
    1: "final",
    2: "semifinal",
    4: "quarterfinal",
    8: "round_of_16",
    16: "round_of_32",
    32: "round_of_64",
}


def next_power_of_2(n: int) -> int:
    """Retorna a menor potência de 2 >= n."""
    if n <= 1:
        return 1
    return 2 ** math.ceil(math.log2(n))


def phase_name(slots_in_round: int) -> str:
    """
    Converte o número de jogos em uma rodada eliminatória no nome da fase.

    Ex.: 4 slots → 'quarterfinal', 1 slot → 'final'.
    Para valores não mapeados retorna 'round_of_<N>' dinamicamente.
    """
    return _PHASE_NAMES.get(slots_in_round, f"round_of_{slots_in_round * 2}")


# ---------------------------------------------------------------------------
# Algoritmo circle-method (pontos corridos)
# ---------------------------------------------------------------------------

def round_robin_pairs(teams: list) -> list[list[tuple]]:
    """
    Gera o calendário completo de pontos corridos usando o circle-method.

    Parâmetros
    ----------
    teams : list
        Lista de quaisquer objetos. Identidade usada para emparelhamento.

    Retorna
    -------
    list[list[tuple]]
        Lista de rodadas; cada rodada é uma lista de pares (home, away).
        Se `n` for ímpar, um None (BYE) é inserido internamente e os pares
        que o contêm são omitidos do resultado.

    Propriedades garantidas
    -----------------------
    - Cada par (A, B) aparece exatamente uma vez em todo o calendário.
    - Nenhum time joga duas vezes na mesma rodada.
    - Número de rodadas = n-1 (n par) ou n (n ímpar, com BYE rotativo).
    - Complexidade: O(n²) confrontos em O(n) rodadas.
    """
    pool = list(teams)
    if len(pool) % 2 == 1:
        pool.append(None)  # BYE placeholder

    n = len(pool)
    rounds: list[list[tuple]] = []

    for _ in range(n - 1):
        pairs = [
            (pool[i], pool[n - 1 - i])
            for i in range(n // 2)
            if pool[i] is not None and pool[n - 1 - i] is not None
        ]
        rounds.append(pairs)
        # Rotaciona todos exceto o âncora pool[0]
        pool = [pool[0]] + [pool[-1]] + pool[1:-1]

    return rounds


# ---------------------------------------------------------------------------
# Algoritmo de seeding (chave eliminatória)
# ---------------------------------------------------------------------------

def seeded_bracket_pairs(seeds: list) -> list[tuple]:
    """
    Emparelha seeds para a primeira rodada de uma chave eliminatória.

    Padrão: seed[0] vs seed[-1], seed[1] vs seed[-2], ...
    Isso garante que os melhores seeds (índices mais baixos) só se encontrem
    nas rodadas finais.

    Parâmetros
    ----------
    seeds : list
        Lista de team_ids ou None (BYE). Comprimento deve ser potência de 2.

    Retorna
    -------
    list[tuple]
        Lista de pares (home_seed, away_seed). None indica BYE.
    """
    result = []
    left, right = 0, len(seeds) - 1
    while left < right:
        result.append((seeds[left], seeds[right]))
        left += 1
        right -= 1
    return result


# ---------------------------------------------------------------------------
# Distribuição de cabeças de chave
# ---------------------------------------------------------------------------

def apply_heads_seeding(
    all_team_ids: list[int],
    seeded_ids: list[int],
    randomize_rest: bool = True,
) -> list[int]:
    """
    Retorna a lista de team_ids ordenada para uso como seeds no bracket.

    Os `seeded_ids` (cabeças de chave) ocupam as posições iniciais
    (seeds 1, 2, 3...), garantindo que estejam em partes opostas do bracket
    quando combinado com `seeded_bracket_pairs`. Os demais times preenchem
    as posições restantes.

    Parâmetros
    ----------
    all_team_ids : list[int]
        Todos os times inscritos no campeonato.
    seeded_ids : list[int]
        Times designados cabeças de chave, em ordem de preferência.
    randomize_rest : bool
        Se True, embaralha os times não-cabeça antes de preenchê-los.

    Raises
    ------
    ValueError
        Se algum ID em `seeded_ids` não estiver em `all_team_ids`.
    """
    enrolled = set(all_team_ids)
    for sid in seeded_ids:
        if sid not in enrolled:
            raise ValueError(
                f"Cabeça de chave id={sid} não está inscrita no campeonato"
            )

    # Deduplica preservando a ordem declarada
    seen: set[int] = set()
    unique_seeds: list[int] = []
    for sid in seeded_ids:
        if sid not in seen:
            unique_seeds.append(sid)
            seen.add(sid)

    rest = [tid for tid in all_team_ids if tid not in seen]
    if randomize_rest:
        random.shuffle(rest)

    return unique_seeds + rest


# ---------------------------------------------------------------------------
# Validação de ordem manual
# ---------------------------------------------------------------------------

def validate_teams_order(
    teams_order: list[int],
    enrolled_ids: set[int],
) -> None:
    """
    Valida que `teams_order` contém exatamente os times inscritos, sem repetições.

    Raises
    ------
    ValueError
        Com mensagem descritiva indicando times faltando, extras ou duplicados.
    """
    if len(teams_order) != len(set(teams_order)):
        raise ValueError("teams_order contém IDs de times duplicados")

    order_set = set(teams_order)
    missing = enrolled_ids - order_set
    extra = order_set - enrolled_ids

    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"faltando times inscritos: {sorted(missing)}")
        if extra:
            parts.append(f"times não inscritos incluídos: {sorted(extra)}")
        raise ValueError(f"teams_order inválido — {'; '.join(parts)}")
