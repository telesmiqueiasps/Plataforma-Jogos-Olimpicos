"""
tests/test_draw_algorithms.py
==============================
Testes unitários para as funções puras de draw_algorithms.py.

Não requerem banco de dados, mocks ou fixtures de IO —
são executados com `pytest` diretamente.

Rodar:
    cd backend
    pytest tests/test_draw_algorithms.py -v
"""

import pytest

from app.services.draw_algorithms import (
    apply_heads_seeding,
    next_power_of_2,
    phase_name,
    round_robin_pairs,
    seeded_bracket_pairs,
    validate_teams_order,
)


# ===========================================================================
# next_power_of_2
# ===========================================================================

class TestNextPowerOf2:
    @pytest.mark.parametrize("n, expected", [
        (1, 1),
        (2, 2),
        (3, 4),
        (4, 4),
        (5, 8),
        (6, 8),
        (7, 8),
        (8, 8),
        (9, 16),
        (15, 16),
        (16, 16),
        (17, 32),
    ])
    def test_values(self, n, expected):
        assert next_power_of_2(n) == expected

    def test_result_is_always_power_of_2(self):
        import math
        for n in range(1, 100):
            result = next_power_of_2(n)
            assert result >= n
            assert math.log2(result) == int(math.log2(result)), (
                f"next_power_of_2({n})={result} não é potência de 2"
            )


# ===========================================================================
# phase_name
# ===========================================================================

class TestPhaseName:
    @pytest.mark.parametrize("slots, expected", [
        (1, "final"),
        (2, "semifinal"),
        (4, "quarterfinal"),
        (8, "round_of_16"),
        (16, "round_of_32"),
        (32, "round_of_64"),
    ])
    def test_known_phases(self, slots, expected):
        assert phase_name(slots) == expected

    def test_unknown_phase_dynamic(self):
        # Fases não mapeadas → "round_of_<N>"
        assert phase_name(3) == "round_of_6"
        assert phase_name(6) == "round_of_12"


# ===========================================================================
# round_robin_pairs — algoritmo circle-method
# ===========================================================================

class TestRoundRobinPairs:

    # -----------------------------------------------------------------------
    # Cobertura: cada par aparece exatamente uma vez
    # -----------------------------------------------------------------------
    @pytest.mark.parametrize("n_teams", [2, 3, 4, 5, 6, 7, 8])
    def test_all_pairs_appear_exactly_once(self, n_teams):
        teams = list(range(n_teams))
        rounds = round_robin_pairs(teams)

        found_pairs: list[frozenset] = []
        for rnd in rounds:
            for home, away in rnd:
                found_pairs.append(frozenset({home, away}))

        expected = {frozenset({i, j}) for i in teams for j in teams if i < j}
        assert set(found_pairs) == expected, "Algum par faltou ou não foi gerado"
        assert len(found_pairs) == len(expected), "Par duplicado detectado"

    # -----------------------------------------------------------------------
    # Sem jogo duplo na mesma rodada
    # -----------------------------------------------------------------------
    @pytest.mark.parametrize("n_teams", [2, 3, 4, 5, 6, 8])
    def test_no_team_plays_twice_per_round(self, n_teams):
        teams = list(range(n_teams))
        for rnd in round_robin_pairs(teams):
            used: list[int] = []
            for home, away in rnd:
                assert home not in used, f"Time {home} joga duas vezes na mesma rodada"
                assert away not in used, f"Time {away} joga duas vezes na mesma rodada"
                used += [home, away]

    # -----------------------------------------------------------------------
    # Nenhum time joga contra si mesmo
    # -----------------------------------------------------------------------
    @pytest.mark.parametrize("n_teams", [2, 3, 4, 5, 6, 8])
    def test_no_self_game(self, n_teams):
        teams = list(range(n_teams))
        for rnd in round_robin_pairs(teams):
            for home, away in rnd:
                assert home != away, f"Auto-confronto detectado: {home} vs {away}"

    # -----------------------------------------------------------------------
    # Número correto de rodadas
    # -----------------------------------------------------------------------
    def test_even_teams_round_count(self):
        # n par → n-1 rodadas
        assert len(round_robin_pairs(list(range(4)))) == 3
        assert len(round_robin_pairs(list(range(6)))) == 5
        assert len(round_robin_pairs(list(range(8)))) == 7

    def test_odd_teams_round_count(self):
        # n ímpar → n rodadas (com BYE rotativo)
        assert len(round_robin_pairs(list(range(3)))) == 3
        assert len(round_robin_pairs(list(range(5)))) == 5

    # -----------------------------------------------------------------------
    # Número correto de jogos por rodada (sem BYE)
    # -----------------------------------------------------------------------
    def test_even_teams_games_per_round(self):
        # 4 times → 2 jogos por rodada
        rounds = round_robin_pairs([1, 2, 3, 4])
        assert all(len(rnd) == 2 for rnd in rounds)

    def test_odd_teams_games_per_round(self):
        # 3 times (BYE) → 1 jogo por rodada
        rounds = round_robin_pairs([1, 2, 3])
        assert all(len(rnd) == 1 for rnd in rounds)

    # -----------------------------------------------------------------------
    # Algoritmo é determinístico (mesma entrada → mesma saída)
    # -----------------------------------------------------------------------
    def test_determinism(self):
        teams = [10, 20, 30, 40]
        assert round_robin_pairs(teams) == round_robin_pairs(teams)

    # -----------------------------------------------------------------------
    # Funciona com 2 times (mínimo)
    # -----------------------------------------------------------------------
    def test_two_teams(self):
        rounds = round_robin_pairs([1, 2])
        assert len(rounds) == 1
        assert rounds[0] == [(1, 2)]


# ===========================================================================
# seeded_bracket_pairs
# ===========================================================================

class TestSeededBracketPairs:

    def test_8_teams_standard_seeding(self):
        seeds = [1, 2, 3, 4, 5, 6, 7, 8]
        pairs = seeded_bracket_pairs(seeds)
        assert len(pairs) == 4
        assert (1, 8) in pairs
        assert (2, 7) in pairs
        assert (3, 6) in pairs
        assert (4, 5) in pairs

    def test_4_teams(self):
        seeds = [1, 2, 3, 4]
        pairs = seeded_bracket_pairs(seeds)
        assert (1, 4) in pairs
        assert (2, 3) in pairs

    def test_2_teams(self):
        seeds = [1, 2]
        pairs = seeded_bracket_pairs(seeds)
        assert pairs == [(1, 2)]

    def test_byes_assigned_to_top_seeds(self):
        # 6 times → bracket de 8, 2 BYEs no final
        seeds = [1, 2, 3, 4, 5, 6, None, None]
        pairs = seeded_bracket_pairs(seeds)
        assert len(pairs) == 4
        # seeds 1 e 2 devem receber BYE (enfrentam None)
        assert (1, None) in pairs
        assert (2, None) in pairs

    def test_top_two_seeds_never_meet_in_round_1(self):
        seeds = [1, 2, 3, 4, 5, 6, 7, 8]
        pairs = seeded_bracket_pairs(seeds)
        for h, a in pairs:
            assert not (h in (1, 2) and a in (1, 2)), (
                "Seeds 1 e 2 não devem se enfrentar na primeira rodada"
            )

    def test_bracket_size_8_covers_all_seeds(self):
        seeds = list(range(1, 9))
        pairs = seeded_bracket_pairs(seeds)
        all_teams = {t for pair in pairs for t in pair}
        assert all_teams == set(seeds)

    def test_result_length_is_half_bracket_size(self):
        for size in [2, 4, 8, 16]:
            seeds = list(range(1, size + 1))
            pairs = seeded_bracket_pairs(seeds)
            assert len(pairs) == size // 2


# ===========================================================================
# apply_heads_seeding
# ===========================================================================

class TestApplyHeadsSeeding:

    def test_heads_placed_at_front(self):
        all_teams = [1, 2, 3, 4, 5, 6, 7, 8]
        result = apply_heads_seeding(all_teams, seeded_ids=[3, 7], randomize_rest=False)
        assert result[0] == 3
        assert result[1] == 7

    def test_all_teams_preserved(self):
        all_teams = [1, 2, 3, 4, 5, 6]
        result = apply_heads_seeding(all_teams, seeded_ids=[2, 5], randomize_rest=False)
        assert set(result) == set(all_teams)
        assert len(result) == len(all_teams)

    def test_no_duplicates_in_result(self):
        all_teams = [1, 2, 3, 4]
        result = apply_heads_seeding(all_teams, seeded_ids=[1, 3], randomize_rest=False)
        assert len(result) == len(set(result))

    def test_deduplicates_seeded_ids(self):
        # Se o mesmo ID aparecer duas vezes em seeded_ids, deduplica
        all_teams = [1, 2, 3, 4]
        result = apply_heads_seeding(all_teams, seeded_ids=[1, 1, 2], randomize_rest=False)
        assert result[0] == 1
        assert result[1] == 2
        assert len(result) == len(all_teams)

    def test_raises_for_unknown_seeded_id(self):
        with pytest.raises(ValueError, match="não está inscrita"):
            apply_heads_seeding([1, 2, 3], seeded_ids=[99])

    def test_rest_order_preserved_when_no_randomize(self):
        all_teams = [1, 2, 3, 4, 5]
        result = apply_heads_seeding(all_teams, seeded_ids=[3], randomize_rest=False)
        # rest = [1, 2, 4, 5] em ordem original
        assert result == [3, 1, 2, 4, 5]

    def test_heads_in_opposite_bracket_halves(self):
        """
        Com 2 cabeças de chave num bracket de 8:
        seed1 vs seed8, seed2 vs seed7 → lados opostos, só se encontram na final.
        """
        all_teams = list(range(1, 9))
        seed_order = apply_heads_seeding(all_teams, seeded_ids=[1, 2], randomize_rest=False)
        # seed_order = [1, 2, 3, 4, 5, 6, 7, 8]
        seeds = seed_order + [None] * (next_power_of_2(len(seed_order)) - len(seed_order))
        pairs = seeded_bracket_pairs(seeds)
        for h, a in pairs:
            assert not (h == 1 and a == 2), "Cabeças de chave não devem se enfrentar no 1º turno"
            assert not (h == 2 and a == 1)

    def test_4_heads_cover_all_bracket_halves(self):
        """
        Com 4 cabeças de chave num bracket de 8:
        seeds 1,2 em lados opostos; seeds 3,4 em lados opostos.
        Nenhum par de cabeças deve se enfrentar na 1ª rodada.
        """
        all_teams = list(range(1, 9))
        seeded = [1, 2, 3, 4]
        seed_order = apply_heads_seeding(all_teams, seeded_ids=seeded, randomize_rest=False)
        pairs = seeded_bracket_pairs(seed_order)
        for h, a in pairs:
            both_heads = h in seeded and a in seeded
            assert not both_heads, (
                f"Duas cabeças de chave {h} e {a} se enfrentam na 1ª rodada"
            )


# ===========================================================================
# validate_teams_order
# ===========================================================================

class TestValidateTeamsOrder:

    def test_valid_order(self):
        # Não deve lançar exceção
        validate_teams_order([3, 1, 4, 2], {1, 2, 3, 4})

    def test_raises_missing_teams(self):
        with pytest.raises(ValueError, match="faltando"):
            validate_teams_order([1, 2, 3], {1, 2, 3, 4})

    def test_raises_extra_teams(self):
        with pytest.raises(ValueError, match="não inscritos"):
            validate_teams_order([1, 2, 3, 99], {1, 2, 3})

    def test_raises_duplicates(self):
        with pytest.raises(ValueError, match="duplicados"):
            validate_teams_order([1, 1, 2, 3], {1, 2, 3})

    def test_raises_both_missing_and_extra(self):
        # Falta o time 4, sobra o 99
        with pytest.raises(ValueError):
            validate_teams_order([1, 2, 3, 99], {1, 2, 3, 4})

    def test_single_team_both_sides(self):
        validate_teams_order([42], {42})

    def test_empty_lists(self):
        validate_teams_order([], set())


# ===========================================================================
# Propriedades de integração entre funções
# ===========================================================================

class TestAlgorithmIntegration:

    def test_round_robin_total_games_formula(self):
        """Total de jogos = n*(n-1)/2 (turno único)."""
        for n in range(2, 10):
            teams = list(range(n))
            all_games = sum(len(r) for r in round_robin_pairs(teams))
            expected = n * (n - 1) // 2
            assert all_games == expected, (
                f"n={n}: esperado {expected} jogos, obteve {all_games}"
            )

    def test_bracket_size_covers_all_teams(self):
        """O bracket deve ter slots suficientes para todos os times."""
        for n in range(2, 17):
            size = next_power_of_2(n)
            assert size >= n

    def test_seeded_pairs_count_equals_bracket_size_div_2(self):
        for size in [2, 4, 8, 16]:
            seeds = list(range(size))
            pairs = seeded_bracket_pairs(seeds)
            assert len(pairs) == size // 2

    def test_full_bracket_workflow_6_teams(self):
        """
        Simula o fluxo completo: 6 times, 2 cabeças de chave.
        Verifica que bracket de 8 é gerado com 2 BYEs nos slots das cabeças.
        """
        all_teams = [10, 20, 30, 40, 50, 60]
        seeded = [10, 20]  # cabeças de chave

        seed_order = apply_heads_seeding(all_teams, seeded, randomize_rest=False)
        bracket_size = next_power_of_2(len(seed_order))
        n_byes = bracket_size - len(seed_order)

        assert bracket_size == 8
        assert n_byes == 2

        seeds = seed_order + [None] * n_byes
        pairs = seeded_bracket_pairs(seeds)

        assert len(pairs) == 4
        # Cabeças de chave devem receber BYE (estão nas posições 0 e 1)
        assert (10, None) in pairs
        assert (20, None) in pairs
