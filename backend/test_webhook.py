import json
from app.api.routes.webhook import extract_modalities

# Payload do usuário
payload = {
    "id": 1,
    "event_id": 126393,
    "name": "Miqueias Teles",
    "email": "miqueiasteles9@gmail.com",
    "order_id": 1,
    "order_status": "Ok",
    "ticket_name": "Normal",
    "ticket_sale_price": 20.00,
    "first_name": "Miqueias",
    "last_name": "Teles",
    "phone": "(83)99999-9999",
    "event_name": "Jogos Sinodais",
    "igreja_que_congrega_7933060": "IPB de Sousa",
    "nome_do_seu_pastor_7933061": "Pastor Teste",
    "numero_whatsapp_do_seu_pastor_7933059": "(83)99999-0000",
    "faz_parte_de_qual_federacao_presbiterio_7933057": "Presbiterio Oeste",
    "tipo_de_inscricao_7933056": "Atleta",
    "modalidade_01_7963068": "Futsal Masculino",
    "modalidade_02_7963115": "Volei Misto",
    "modalidade_03_7963116": "",
    "modalidade_04_7963117": ""
}

modalities = extract_modalities(payload)
print("Modalidades extraídas:", modalities)