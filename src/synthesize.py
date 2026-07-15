"""
synthesize.py — Classifica os itens coletados nos 4 eixos, decide elegibilidade
para alerta diário, e escreve o "por que importa" de cada item.

Como rodar:
    export DEEPSEEK_API_KEY="sua-chave-aqui"
    python src/synthesize.py data/raw_items_2026-07-13.json

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

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

AXES = ["RV/Trading", "Tecnologia", "Produtos Novos", "Risco/Regulação"]

SYSTEM_PROMPT = f"""Você é o analista do Radar de Mercado de um grupo de investimentos
brasileiro, monitorando os concorrentes: XP/Clear/Rico, BTG Pactual, Itaú/Íon,
Bradesco/Ágora e Genial Investimentos.

Você recebe uma lista de itens de notícia brutos, cada um com um "index".

PASSO 1 — Deduplicação semântica:
Vários itens podem descrever o MESMO fato/evento, mesmo vindo de fontes ou
manchetes diferentes (ex: dois portais cobrindo a mesma aquisição no mesmo
dia). Agrupe esses itens como UMA história só. NÃO agrupe itens que só
compartilham o mesmo concorrente ou tema geral — só agrupe quando é
literalmente o mesmo fato.

PASSO 2 — Classificação (uma vez por história única, não por item bruto):
Para cada história, retorne um objeto JSON com:
- "source_indices": lista dos índices originais que compõem essa história
  (item sem duplicata = lista com 1 índice só)
- "primary_index": o índice da fonte mais direta/primária dessa história
  (prefira o veículo mais especializado a um agregador genérico, quando dá
  pra notar diferença)
- "axes": lista com 1+ eixos entre exatamente estes: {AXES}
- "daily_trigger": true/false — true SOMENTE se a história se encaixar em
  pelo menos um destes critérios: {DAILY_TRIGGER_CRITERIA}
- "why_it_matters": 1-2 frases em português explicando a implicação
  competitiva, não apenas repetindo a notícia
- "relevance": "alta", "média" ou "baixa"

SEJA CÉTICO POR PADRÃO. Prefira relevance="baixa" a menos que a história
indique uma mudança CONCRETA de produto, tecnologia, risco ou regulação por
parte do concorrente. Especificamente, NÃO conte como "Produtos Novos" nem
como gatilho diário:
- Carteiras recomendadas, listas de "melhores fundos/ações do mês" ou
  qualquer recomendação de research/analista sobre produtos que já existem
- Eventos, palestras, participações em conferências ou ações de marca/
  marketing sem anúncio de produto novo
- Notícias de cotação, resultado financeiro trimestral ou desempenho de
  ações, a menos que sinalizem mudança estratégica relevante (ex: troca de
  CEO/CFO, pivô de modelo de negócio)
- Menções superficiais do concorrente dentro de uma pauta mais ampla do
  mercado

"Produtos Novos" é para lançamentos, funcionalidades novas, aquisições,
parcerias ou expansões que o concorrente está CRIANDO ou ANUNCIANDO agora —
não para conteúdo editorial ou promocional sobre algo que já existia.

Responda APENAS com um array JSON, sem markdown, sem texto antes ou depois.
Cada história única aparece UMA VEZ no array, mesmo que venha de vários
índices de entrada."""


def classify_batch(items: list[dict], api_key: str) -> list[dict]:
    if not items:
        return []

    user_content = json.dumps(
        [
            {
                "index": i,
                "competitor_group": item["competitor_group"],
                "title": item["title"],
                "summary": item["summary"],
                "source": item["source"],
                "published_at": item["published_at"],
            }
            for i, item in enumerate(items)
        ],
        ensure_ascii=False,
    )

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
                {"role": "user", "content": user_content},
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
        source_indices = classification.get("source_indices") or [classification.get("primary_index", 0)]
        primary_idx = classification.get("primary_index", source_indices[0])
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
    if len(sys.argv) != 2:
        print("Uso: python src/synthesize.py data/raw_items_AAAA-MM-DD.json", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Erro: defina a variável de ambiente DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    items = json.loads(input_path.read_text(encoding="utf-8"))

    classified = classify_batch(items, api_key)
    # Só mantém itens de relevância média/alta
    classified = [c for c in classified if c.get("relevance") != "baixa"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = input_path.parent / f"classified_items_{today}.json"
    out_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Classificados {len(classified)} itens relevantes → {out_path}")


if __name__ == "__main__":
    main()
