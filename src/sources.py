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

# Apps Android dos concorrentes na Google Play, monitorados por
# collect_appstore.py (patch notes + nota média) e por collect_incidents.py
# (pico de reviews negativos). Package IDs verificados em jul/2026 contra as
# páginas oficiais da Play Store — se um app for renomeado/substituído (como
# a Clear fez em 2026), atualize aqui.
PLAY_STORE_APPS = {
    "XP/Clear/Rico": {
        "XP (app principal)": "br.com.xp.carteira",
        "XP Trader": "br.com.tecfinance.xpmobile",
        "Rico": "br.com.rico.mobile",
        "Clear (novo app)": "br.com.xpinc.clear.app.android",
        "Clear (app legado)": "br.com.clear.app.android",
    },
    "BTG Pactual": {
        "BTG Investimentos": "com.btg.pactual.digital.mobile",
        "BTG Pactual Trader": "com.btg.pactual.homebroker.mobile",
    },
    "Itaú/Íon": {
        "íon Itaú": "com.itau.investimentos",
    },
    "Bradesco/Ágora": {
        "Ágora Investimentos": "br.com.valemobi.agora",
    },
    "Genial": {
        "Genial Investimentos": "com.br.GeraTech.Genial.NovaPlataforma",
        "Genial HB": "com.br.GeraTech.Genial.HB.Nelogica",
    },
}

# Queda de nota média (0-5) em relação ao último estado salvo que gera um
# item de alerta de percepção de clientes. 0.1 é sensível demais (flutuação
# normal); 0.2 já indica movimento real de avaliações negativas.
APPSTORE_SCORE_DROP_THRESHOLD = 0.2

# ---------------------------------------------------------------------------
# Monitoramento de INCIDENTES (collect_incidents.py) — gatilho INC
# ---------------------------------------------------------------------------

# Termos combinados com cada alias em queries direcionadas no Google News
# (captura incidentes grandes o suficiente pra virar notícia).
INCIDENT_NEWS_TERMS = ["fora do ar", "instabilidade", "pane", "falha"]

# Palavras que, em reviews recentes de 1-2 estrelas na Play Store, indicam
# indisponibilidade/mau funcionamento (captura incidentes que NÃO viram
# notícia — o sinal antecipado).
INCIDENT_REVIEW_KEYWORDS = [
    "fora do ar", "não abre", "nao abre", "não consigo", "nao consigo",
    "trava", "travando", "erro", "caiu", "instável", "instavel",
    "instabilidade", "não funciona", "nao funciona", "não carrega",
    "nao carrega", "lento demais",
]

# Janela de análise dos reviews e limiar do pico: N reviews negativos com
# palavra de incidente dentro da janela → alerta. 5 em 48h num app de
# corretora é anormal; ajuste com a experiência real de cada app.
REVIEW_LOOKBACK_DAYS = 2
REVIEW_INCIDENT_THRESHOLD = 5
REVIEWS_FETCH_COUNT = 150  # reviews mais recentes buscados por app

# Não repete alerta do mesmo app dentro desta janela (o mesmo incidente
# gera reviews por dias — um alerta basta).
INCIDENT_REALERT_DAYS = 2

# Reclame Aqui — EXPERIMENTAL. Slug de cada empresa é o trecho final da URL
# pública (reclameaqui.com.br/empresa/<slug>/). CONFIRME cada slug abrindo a
# URL no navegador antes de ativar; os comentados abaixo são os prováveis,
# não verificados. Deixe o dict vazio pra desativar o módulo.
RECLAME_AQUI_COMPANIES: dict[str, str] = {
    # "XP/Clear/Rico": "xp-investimentos",
    # "BTG Pactual": "btg-pactual",
    # "Itaú/Íon": "itau-corretora-de-valores",
    # "Bradesco/Ágora": "agora-investimentos",
    # "Genial": "genial-investimentos",
}

# Salto no total de reclamações recentes vs. último estado salvo que gera
# alerta de tendência.
RECLAME_AQUI_JUMP_THRESHOLD = 15

# ---------------------------------------------------------------------------
# Monitoramento SOCIAL (collect_social.py) — polêmicas e trends
# Desenho: detector de PICO contra baseline, nunca leitura de feed bruto.
# ---------------------------------------------------------------------------

# Subreddits monitorados (posts recentes são baixados e as menções contadas
# localmente — 1 request por subreddit por execução).
SOCIAL_SUBREDDITS = ["investimentos", "farialimabets"]

# Termos que contam como menção ao grupo em posts do Reddit (regex com
# borda de palavra, case-insensitive, acento respeitado). CUIDADO com termos
# ambíguos em português: "rico" (adjetivo), "agora" (advérbio) e "genial"
# (adjetivo) só entram qualificados ou acentuados. Ajuste com a prática —
# se um grupo gerar falso positivo, restrinja o termo aqui.
SOCIAL_REDDIT_ALIASES = {
    "XP/Clear/Rico": ["xp", "clear", "rico investimentos", "corretora rico"],
    "BTG Pactual": ["btg"],
    "Itaú/Íon": ["íon", "itaú"],
    "Bradesco/Ágora": ["ágora", "agora investimentos", "bradesco"],
    "Genial": ["genial"],
}

# Alerta quando as menções de hoje >= MIN e >= MULTIPLIER x média dos dias
# anteriores. Exige BASELINE_MIN_DAYS de histórico antes de poder alertar
# (senão o primeiro dia sempre "estoura" uma média vazia).
SOCIAL_SPIKE_MIN_MENTIONS = 5
SOCIAL_SPIKE_MULTIPLIER = 3.0
SOCIAL_BASELINE_MIN_DAYS = 3
SOCIAL_REALERT_DAYS = 2

# Google Trends: um termo representativo por grupo (máximo 5 — limite de
# uma consulta do Trends). Interesse de busca é o detector mais puro de
# polêmica grande: gente correndo pro Google atrás do nome do concorrente.
SOCIAL_TRENDS_TERMS = {
    "XP/Clear/Rico": "XP Investimentos",
    "BTG Pactual": "BTG Pactual",
    "Itaú/Íon": "íon Itaú",
    "Bradesco/Ágora": "Ágora Investimentos",
    "Genial": "Genial Investimentos",
}

# Alerta quando o interesse médio das últimas 24h >= MULTIPLIER x média dos
# 6 dias anteriores E o valor absoluto passa de MIN_INTEREST (escala 0-100
# do Trends — picos abaixo de 20 costumam ser ruído de série rala).
TRENDS_SPIKE_MULTIPLIER = 3.0
TRENDS_MIN_INTEREST = 20

# Fontes institucionais/regulatórias monitoradas à parte (não são "notícia",
# são páginas oficiais — tratamento diferente, sem passar por Google News).
# Preenchido como próxima iteração (ver README) — CVM, changelog de app
# store dos concorrentes, etc.
INSTITUTIONAL_SOURCES: dict[str, str] = {
    # "CVM - Ofícios Circulares": "https://www.gov.br/cvm/...",
}

# Critérios que tornam um item elegível para alerta DIÁRIO (gatilho).
# Cada critério tem um CÓDIGO — a LLM deve citar o código em trigger_reason.
# Se nenhum código se aplica exatamente, daily_trigger = false.
DAILY_TRIGGER_CRITERIA = [
    "PRICE — Mudança confirmada de preço, taxa, corretagem, limites de alavancagem ou modelo de margem/risco",
    "LANC — Lançamento ou descontinuação CONFIRMADA de produto, funcionalidade ou plataforma de investimentos",
    "REG — Ato regulatório novo (CVM, B3, Bacen, ANBIMA) com efeito sobre corretagem/RV, ou ação regulatória contra o concorrente",
    "INC — Incidente operacional: indisponibilidade de plataforma, falha de execução, vazamento de dados",
    "MA — Aquisição, fusão, entrada ou saída de mercado no negócio de investimentos",
    "LID — Troca de CEO/CFO/head de área core ou pivô estratégico declarado",
    "TERMS — Alteração confirmada de termos de uso, contrato ou condições de serviço ao cliente",
]
