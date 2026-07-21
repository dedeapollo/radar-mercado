"""
synthesize.py — Classifica os itens coletados nos 4 eixos, decide elegibilidade
para alerta diário, e escreve o "por que importa" de cada item.

Como rodar:
    export DEEPSEEK_API_KEY="sua-chave-aqui"
    python src/synthesize.py data/raw_items_2026-07-13.json
    # aceita múltiplos arquivos de entrada (ex: notícias + app stores):
    python src/synthesize.py data/raw_items_2026-07-13.json data/raw_appstore_items_2026-07-13.json

Saída:
    data/classified_items_AAAA-MM-DD.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from sources import DAILY_TRIGGER_CRITERIA
from history import get_items_since, load_history

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

AXES = ["RV/Trading", "Tecnologia", "Produtos Novos", "Risco/Regulação"]

TRIGGER_CODES = {"PRICE", "LANC", "REG", "INC", "MA", "LID", "TERMS"}

SYSTEM_PROMPT = f"""Você é o analista do Radar de Mercado de um grupo de investimentos
brasileiro, monitorando os concorrentes: XP/Clear/Rico, BTG Pactual, Itaú/Íon,
Bradesco/Ágora e Genial Investimentos. Custo dos erros: um falso alerta queima a
atenção da liderança; em dúvida sobre gatilho, a resposta é false.

O foco é o NEGÓCIO DE INVESTIMENTOS/CORRETAGEM desses grupos — não as demais
frentes do conglomerado (crédito corporativo, seguros, atacado), salvo quando o
fato tiver materialidade declarada para o negócio de investimentos ou risco
reputacional grave para a marca.

PERSPECTIVA DE RELEVÂNCIA: o leitor comanda RV/Trading, Novos Produtos e CX de uma
corretora de varejo. Relevância "alta" é reservada para fatos que tocam o CLIENTE
INVESTIDOR PESSOA FÍSICA desses concorrentes: condições de trading (alavancagem,
corretagem, execução), lançamento de produto/plataforma de investimento de varejo,
incidentes de plataforma, mudanças de app, entrada/saída de segmento de varejo.

Fatos corporativos do concorrente que NÃO tocam o cliente investidor — expansão
internacional, M&A de atacado, crédito corporativo, resultados — são no máximo
"média", mesmo quando grandes. São contexto estratégico, não sinal de campo.

Exemplos calibrados pelo leitor:
ALTA (top picks): "Genial aumenta alavancagem de ações para daytraders";
"XP lança plataforma de mercado preditivo"; "BTG entra em novo segmento de varejo";
"XP tem contingência operacional em suas plataformas"; "clientes reclamam nas redes
de mau funcionamento de produto da Genial".
MÉDIA (bem classificado, mas não é top pick): "BTG conclui aquisição do HSBC
Uruguai"; "BTG reativa e expande securitizadora".
DESCARTE: "Renda Fixa Hoje: taxas de CDBs na XP"; "melhores fundos do mês segundo
o BTG"; "XP acompanha recuperação extrajudicial da Oncoclínicas"; "BTG executa
garantias da Rio Alto".

Você recebe uma lista de itens brutos, cada um com um "index". Alguns itens têm
"channel": "appstore" — são patch notes ou mudanças de nota dos apps Android dos
concorrentes, coletados direto da Google Play (regras específicas abaixo).

PASSO 0 — TRIAGEM. NÃO INCLUA NA SAÍDA (descarte silenciosamente) itens que sejam:
- Colunas ou seções recorrentes de portal: taxas do dia ("Renda Fixa Hoje"), agenda,
  fechamento de pregão, cotações
- Research e recomendações sobre produtos que já existem: carteiras recomendadas,
  "melhores fundos/ações do mês", relatórios de analistas do próprio concorrente
- Guias, comparativos e conteúdo de afiliado/SEO sobre produtos existentes
  (ex.: guia de benefícios de cartão)
- Cobertura de eventos, palestras, patrocínios e ações de marca SEM anúncio de
  produto, funcionalidade ou preço novo. ATENÇÃO: anúncio de produto novo feito
  DURANTE um evento (ex: lançamento de ETF, plataforma ou funcionalidade
  anunciado na Expert XP) É um lançamento — mantenha e classifique pelo
  anúncio, descartando apenas matérias sobre o evento em si
- Campanhas promocionais de rotina (bônus de pontos, cashback temporário), exceto
  se alterarem pricing estrutural do serviço
- Menções superficiais do concorrente dentro de pauta mais ampla do mercado
- Itens em que o concorrente é apenas o veículo da notícia de um terceiro (ex.:
  página do concorrente acompanhando recuperação judicial de uma empresa emissora)
A triagem acima vale para notícias. Itens de channel "appstore" NUNCA são
descartados na triagem — siga as regras do canal appstore abaixo.

PASSO 1 — DEDUPLICAÇÃO SEMÂNTICA dos itens restantes:
Mesma história = mesmo fato central (mesma ação, mesmo ator, mesma janela de
tempo), ainda que com manchetes, ângulos ou fontes diferentes. Anúncio,
repercussão e análise do MESMO fato são UMA história. Mesmo concorrente ou mesmo
tema geral NÃO bastam para agrupar. Cada história única aparece UMA vez na saída.
Se receber uma lista de HISTÓRIAS JÁ REGISTRADAS em dias anteriores, descarte
itens de hoje que sejam o mesmo fato de uma história já registrada.

PASSO 2 — CLASSIFICAÇÃO (uma vez por história única):
Para cada história, retorne um objeto JSON com:
- "source_indices": lista dos índices originais que compõem essa história
  (item sem duplicata = lista com 1 índice só)
- "primary_index": o índice da fonte mais direta/primária dessa história
  (prefira o veículo mais especializado a um agregador genérico)
- "axes": lista com 1+ eixos entre exatamente estes: {AXES}
- "confirmation": "confirmado" ou "especulativo" (rumor, "estuda", "avalia",
  "negocia", fontes anônimas). Item especulativo NUNCA tem daily_trigger=true
  e tem relevance no máximo "média".
- "daily_trigger": true SOMENTE se um dos critérios abaixo se aplicar
  exatamente. Cada critério tem um CÓDIGO: {DAILY_TRIGGER_CRITERIA}
- "trigger_reason": o CÓDIGO do critério aplicado (ex: "LANC"), ou null se
  daily_trigger=false. Gatilho sem código citado será rejeitado. Volume de
  imprensa, "comunicado" genérico ou ação de marketing NÃO são gatilho.
- "why_it_matters": 1-2 frases em português explicando a implicação
  competitiva para uma corretora concorrente, não apenas repetindo a notícia
- "relevance": "alta", "média" ou "baixa". Todo item com daily_trigger=true é
  "alta". Na dúvida entre média e baixa, escolha baixa.

REGRAS DO CANAL "appstore" (itens vindos da Google Play):
- Patch notes de app: classifique sempre com eixo "Tecnologia" (+ outro eixo se
  a mudança tocar trading, produto ou risco). Relevance conforme a substância do
  changelog: só "correção de bugs e melhorias" genérico = baixa; funcionalidade
  nova concreta, mudança de navegação/onboarding relevante = média; funcionalidade
  nova de trading/investimento relevante = alta com trigger LANC.
- Queda de nota do app: eixo "Tecnologia", relevance "média" (ou "alta" se a
  queda for grande, ex. 0.5+), daily_trigger=true com trigger_reason "INC" apenas
  se houver indício de indisponibilidade/incidente; caso contrário false.
- Item "início do monitoramento" (primeira coleta de um app): relevance "baixa".

REGRAS DO CANAL "incident" (notícias direcionadas de incidente, pico de reviews
negativos na Play Store, salto de reclamações no Reclame Aqui):
- Eixo "Tecnologia" sempre; some "RV/Trading" se o incidente afetar negociação
  (home broker, envio de ordens, dia de pregão).
- daily_trigger=true com trigger_reason "INC" quando o sinal indica incidente
  ATUAL e concreto: pico de reviews citando indisponibilidade, salto de
  reclamações, ou notícia de plataforma fora do ar/instável agora. Itens de
  pico de reviews e salto no Reclame Aqui já são agregações com limiar —
  trate como INC com relevance "alta" por padrão.
- daily_trigger=false para matéria retrospectiva ("relembre a pane de..."),
  menção vaga ou notícia em que o termo de incidente não se refere ao
  concorrente (ex: "falha de mercado" como conceito econômico). Nesses casos,
  aplique a triagem normal — a maioria deve ser descartada.

REGRAS DO CANAL "social" (pico de menções no Reddit, pico de buscas no Google
Trends):
- São agregações com limiar: o volume anormal já foi verificado pelo coletor.
  NUNCA descarte na triagem; classifique sempre.
- Eixos conforme o TEMA dominante das amostras: reclamação de plataforma =
  "Tecnologia" (+ "RV/Trading" se afetar negociação); polêmica sobre produto/
  taxas = "Produtos Novos"; escândalo, vazamento ou questão regulatória =
  "Risco/Regulação". Sem tema claro nas amostras = "Tecnologia".
- daily_trigger: "INC" se as amostras indicarem indisponibilidade/mau
  funcionamento atual; caso contrário false — pico de conversa por si só é
  relevance "alta" ou "média" (conforme intensidade), mas não gatilho sem um
  fato dos códigos por trás.
- confirmation: "especulativo" salvo se as amostras citarem fato confirmado.

SEJA CÉTICO POR PADRÃO. Prefira relevance="baixa" a menos que a história indique
uma mudança CONCRETA de produto, tecnologia, risco ou regulação por parte do
concorrente.

Responda APENAS com um array JSON, sem markdown, sem texto antes ou depois.
Cada história única aparece UMA VEZ no array, mesmo que venha de vários
índices de entrada."""


def classify_batch(items: list[dict], api_key: str, known_titles: list[str] | None = None) -> list[dict]:
    if not items:
        return []

    user_payload = {
        "itens": [
            {
                "index": i,
                "competitor_group": item["competitor_group"],
                "title": item["title"],
                "summary": item["summary"],
                "source": item["source"],
                "published_at": item["published_at"],
                **({"channel": item["channel"]} if item.get("channel") else {}),
            }
            for i, item in enumerate(items)
        ],
    }
    if known_titles:
        user_payload["historias_ja_registradas"] = known_titles

    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    raw_content = resp.json()["choices"][0]["message"]["content"]

    parsed = json.loads(raw_content)
    # DeepSeek em modo json_object às vezes envolve o array numa chave —
    # tratamos os dois formatos possíveis.
    classifications = parsed if isinstance(parsed, list) else next(iter(parsed.values()))

    enriched = []
    for classification in classifications:
        # ---- Travas determinísticas (o prompt pede; o código garante) ----
        # 1. Gatilho sem código de critério citado, ou com código inválido,
        #    é rebaixado — fecha a brecha de racionalização.
        reason = classification.get("trigger_reason")
        if classification.get("daily_trigger") and reason not in TRIGGER_CODES:
            classification["daily_trigger"] = False
            classification["trigger_reason"] = None
        # 2. Item especulativo nunca é gatilho e tem relevance <= média.
        if classification.get("confirmation") == "especulativo":
            classification["daily_trigger"] = False
            classification["trigger_reason"] = None
            if classification.get("relevance") == "alta":
                classification["relevance"] = "média"
        # 3. Coerência gatilho -> alta.
        if classification.get("daily_trigger"):
            classification["relevance"] = "alta"
        # 4. Eixos fora da taxonomia são removidos.
        classification["axes"] = [a for a in classification.get("axes", []) if a in AXES]
        if not classification["axes"]:
            continue  # sem eixo válido, sem lugar no radar

        source_indices = classification.get("source_indices") or [classification.get("primary_index", 0)]
        primary_idx = classification.get("primary_index", source_indices[0])
        if not (0 <= primary_idx < len(items)):
            continue  # índice alucinado — descarta a classificação
        primary_item = items[primary_idx]

        other_sources = [
            {"source": items[i]["source"], "link": items[i]["link"]}
            for i in source_indices
            if i != primary_idx and 0 <= i < len(items)
        ]

        merged = {**primary_item, **classification, "also_reported_by": other_sources}
        enriched.append(merged)
    return enriched


def main():
    if len(sys.argv) < 2:
        print(
            "Uso: python src/synthesize.py data/raw_items_AAAA-MM-DD.json [outros_raw.json...]",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Erro: defina a variável de ambiente DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)

    items: list[dict] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"[aviso] arquivo não encontrado, ignorando: {path}", file=sys.stderr)
            continue
        items.extend(json.loads(path.read_text(encoding="utf-8")))

    # Títulos dos últimos 3 dias já registrados — mesmo lookback do collect.py,
    # para o modelo descartar re-coletas do mesmo fato com link diferente.
    known_titles = [item["title"] for item in get_items_since(load_history(), days=3)]

    classified = classify_batch(items, api_key, known_titles=known_titles)
    # Só mantém itens de relevância média/alta
    classified = [c for c in classified if c.get("relevance") != "baixa"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(sys.argv[1]).parent if Path(sys.argv[1]).exists() else Path("data")
    out_path = out_dir / f"classified_items_{today}.json"
    out_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Classificados {len(classified)} itens relevantes → {out_path}")


if __name__ == "__main__":
    main()
