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

Para cada item de notícia recebido, retorne um objeto JSON com:
- "axes": lista com 1+ eixos entre exatamente estes: {AXES}
  (um item PODE pertencer a mais de um eixo — ex: mudança de alavancagem
  entra em "Risco/Regulação" E em "Produtos Novos" se for uma feature nova)
- "daily_trigger": true/false — true SOMENTE se o item se encaixar em pelo
  menos um destes critérios: {DAILY_TRIGGER_CRITERIA}
- "why_it_matters": 1-2 frases em português explicando a implicação
  competitiva, não apenas repetindo a notícia
- "relevance": "alta", "média" ou "baixa" — descarte itens irrelevantes
  (ex: notícia de ações/cotação sem relação com produto/tecnologia/risco)
  marcando relevance="baixa"

Responda APENAS com um array JSON, um objeto por item recebido, na mesma
ordem. Sem markdown, sem texto antes ou depois."""


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
    for item, classification in zip(items, classifications):
        merged = {**item, **classification}
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
