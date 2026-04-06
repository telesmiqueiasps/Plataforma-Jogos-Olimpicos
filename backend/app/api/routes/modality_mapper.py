"""
modality_mapper.py
==================
Funções auxiliares para mapeamento e normalização de modalidades.
"""


def map_ticket_to_slug(ticket_name: str) -> str:
    """
    Mapeia nome do ingresso/modalidade do e-inscrições para slug interno.

    Nomes reais que chegam do e-inscrições:
    "Futsal Masculino [Quadra 01] (R$ 20,00)" → "futsal"
    "Futsal Feminino [Quadra 01] (R$ 20,00)" → "futsal"
    "Vôlei Misto [Quadra 02] (R$ 20,00)"     → "volleyball"
    "Basquete 3x3 [Quadra 01] (R$ 20,00)"    → "basketball"
    "100m rasos [Quadra 01] (R$ 12,00)"       → "running"
    "Tênis de Mesa [Quadra 02] (R$ 12,00)"    → "tenis_mesa"
    "Dominó Dupla [Quadra 01] (R$ 12,00)"     → "domino"
    "Xadrez [Quadra 01] (R$ 12,00)"           → "xadrez"
    "Dama [Quadra 01] (R$ 12,00)"             → "dama"
    """
    if not ticket_name:
        return None

    import re
    import unicodedata

    def normalize(s):
        # Remover conteúdo entre colchetes e parênteses
        s = re.sub(r'\[.*?\]', '', s)
        s = re.sub(r'\(.*?\)', '', s)
        # Converter para minúsculas
        s = s.lower().strip()
        # Remover acentos
        s = unicodedata.normalize('NFKD', s)
        s = ''.join(c for c in s if not unicodedata.combining(c))
        # Remover espaços extras
        s = ' '.join(s.split())
        return s

    name = normalize(ticket_name)

    # FUTSAL — verificar antes de qualquer outra coisa
    if "futsal masculino" in name or ("futsal" in name and "masculino" in name):
        return "futsal_masculino"
    if "futsal feminino" in name or ("futsal" in name and "feminino" in name):
        return "futsal_feminino"
    if "futsal" in name or "futebol de salao" in name or "futebol" in name:
        return "futsal"

    # VÔLEI
    if any(x in name for x in ["volei", "volley", "volleyball", "voli"]):
        return "volleyball"

    # BASQUETE
    if any(x in name for x in ["basquete", "basketball", "basquetebol", "basquet", "3x3"]):
        return "basketball"

    # CORRIDA — antes de "tenis" pois "100m" é único
    if any(x in name for x in ["corrida", "running", "100m", "200m", "400m", "5km", "10km", "rasos", "metros rasos"]):
        return "running"

    # TÊNIS DE MESA — antes de "tenis" genérico para não colidir
    if any(x in name for x in ["tenis de mesa", "ping pong", "pingpong", "mesa"]):
        return "tenis_mesa"

    # DOMINÓ
    if any(x in name for x in ["domino", "dupla"]):
        return "domino"

    # XADREZ
    if any(x in name for x in ["xadrez", "chess"]):
        return "xadrez"

    # DAMA
    if any(x in name for x in ["dama", "checkers", "jogo de dama"]):
        return "dama"

    return None  # retorna None se não mapear


def slug_to_label(slug: str) -> str:
    """Converte slug da modalidade para nome amigável para exibição."""
    mapping = {
        "futsal": "Futsal",
        "futsal_masculino": "Futsal Masculino",
        "futsal_feminino": "Futsal Feminino",
        "volleyball": "Vôlei",
        "basketball": "Basquete",
        "running": "Corrida",
        "tenis_mesa": "Tênis de Mesa",
        "domino": "Dominó",
        "xadrez": "Xadrez",
        "dama": "Dama",
        "outro": "Outra"
    }
    return mapping.get(slug, slug.capitalize())
