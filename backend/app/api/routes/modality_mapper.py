"""
modality_mapper.py
==================
Funções auxiliares para mapeamento e normalização de modalidades.
"""


def map_ticket_to_slug(ticket_name: str) -> str:
    """Mapeia nome do ingresso/modalidade do e-inscrições para slug da modalidade."""
    name = ticket_name.lower().strip()
    if "futsal" in name or "futebol" in name:
        return "futsal"
    if "vôlei" in name or "volei" in name or "vólei" in name or "volleyball" in name:
        return "volleyball"
    if "basquete" in name or "basketball" in name or "basquetebol" in name:
        return "basketball"
    if "corrida" in name or "running" in name or "100m" in name or "200m" in name or "rasos" in name:
        return "running"
    if "tênis de mesa" in name or "tenis de mesa" in name or "ping pong" in name or "tênis" in name:
        return "tenis_mesa"
    if "dominó" in name or "domino" in name or "dupla" in name:
        return "domino"
    if "xadrez" in name or "chess" in name:
        return "xadrez"
    if "dama" in name or "checkers" in name:
        return "dama"
    return "outro"


def slug_to_label(slug: str) -> str:
    """Converte slug da modalidade para nome amigável para exibição."""
    mapping = {
        "futsal": "Futsal",
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
