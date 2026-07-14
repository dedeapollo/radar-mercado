"""
Configuração central do Radar de Mercado.
Editar este arquivo é a forma principal de ajustar quem/o que é monitorado —
não devia ser necessário mexer em collect.py ou synthesize.py pra isso.
"""

# Grupos de concorrentes e os nomes/aliases usados nas buscas.
# Cada alias vira uma query separada no Google News RSS.
COMPETITOR_GROUPS = {
    "XP/Clear/Rico": ["XP Investimentos", "Clear corretora", "Rico investimentos"],
    "BTG Pactual": ["BTG Pactual", "BTG Trends"],
    "Itaú/Íon": ["Itaú investimentos", "Íon Itaú"],
    "Bradesco/Ágora": ["Ágora investimentos", "Bradesco corretora"],
    "Genial": ["Genial Investimentos"],
}

# Os 4 eixos fixos do radar. A LISTA de keywords aqui é só um AUXILIAR pra
# montar queries mais direcionadas — a classificação final de cada notícia
# em um ou mais eixos é feita pela LLM em synthesize.py, não por essas
# palavras-chave.
AXIS_KEYWORDS = {
    "RV/Trading": ["renda variável", "home broker", "day trade", "negociação"],
    "Tecnologia": ["inteligência artificial", "aplicativo", "plataforma"],
    "Produtos Novos": ["lança", "lançamento", "novo produto"],
    "Risco/Regulação": ["alavancagem", "margem", "CVM", "regulação"],
}

# Fontes institucionais/regulatórias monitoradas à parte (não são "notícia",
# são páginas oficiais — tratamento diferente, sem passar por Google News).
# Preenchido como próxima iteração (ver README) — CVM, changelog de app
# store dos concorrentes, etc.
INSTITUTIONAL_SOURCES: dict[str, str] = {
    # "CVM - Ofícios Circulares": "https://www.gov.br/cvm/...",
}

# Critérios que tornam um item elegível para alerta DIÁRIO (gatilho).
# Usado como instrução para a LLM em synthesize.py — mantém em português
# porque é injetado direto no prompt.
DAILY_TRIGGER_CRITERIA = [
    "Mudança em modelo de risco ou alavancagem",
    "Comunicado direto a cliente (pop-up, e-mail, alteração de termos)",
    "Lançamento de produto ou feature anunciado na mídia",
    "Ação regulatória envolvendo o concorrente (CVM, B3, Bacen)",
]
