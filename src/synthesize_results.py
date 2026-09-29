"""
synthesize_results.py — Lê a cobertura de resultados coletada por
collect_results.py e EXTRAI A ESTRATÉGIA de cada divulgação, no recorte do
negócio de investimentos/varejo. NÃO é análise fundamentalista/valuation.

Pipeline paralelo ao synthesize.py (notícias), com schema e store próprios —
não mexe no history.json de notícias.

Como rodar:
    export DEEPSEEK_API_KEY="sua-chave-aqui"
    python src/synthesize_results.py data/raw_results_items_AAAA-MM-DD.json

Saídas:
    data/classified_results_AAAA-MM-DD.json  # resultados do dia (p/ o e-mail 📊)
    data/results_history.json                # store acumulado (p/ o dashboard)

Melhora de qualidade: para cada matéria sobrevivente, tenta baixar o texto do
artigo (best-effort) e passa isso ao modelo — o resumo do RSS costuma ser curto
demais para uma boa leitura de estratégia. Se o download falhar, cai no resumo.

IMPORTANTE: results_history.json precisa ser commitado de volta a cada execução.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from sources import RESULTS_ENTITIES

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

AXES = ["RV/Trading", "Tecnologia", "Produtos Novos", "Risco/Regulação"]
COPY_LABELS = {"copiar", "observar", "ignorar"}

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_HISTORY_PATH = DATA_DIR / "results_history.json"

ARTICLE_FETCH_TIMEOUT = 15
ARTICLE_MAX_CHARS = 4000

SYSTEM_PROMPT = f"""Você é o analista de inteligência competitiva da corretora Santander.
Recebe a COBERTURA DE RESULTADOS TRIMESTRAIS de concorrentes (manchete, resumo e,
quando disponível, o texto da matéria). Sua tarefa NÃO é análise fundamentalista
nem valuation — é EXTRAIR ESTRATÉGIA no recorte do negócio de investimentos/
corretagem de varejo, e apontar onde o concorrente está deixando a desejar.

O Santander é o time da casa. Foque no que interessa a uma corretora de varejo:
onde o concorrente coloca energia, o que lançou ou mudou, e onde há pressão ou
fraqueza — sempre no recorte de investimentos, ignorando crédito, seguros e
atacado (e, no caso do Nubank, ignorando cartão, conta e crédito).

Cada item traz "competitor_group". Use o FOCO correspondente em "focos" para
calibrar o recorte de cada empresa.

Se vários itens forem a MESMA divulgação (mesma empresa, mesmo trimestre), funda
em UM só resultado (use source_indices/primary_index).

Se a informação não estiver no material, escreva "não informado" ou deixe a lista
vazia — NÃO invente números nem fatos.

Para cada resultado único, retorne um objeto JSON com:
- "source_indices": lista dos índices originais que compõem esse resultado
- "primary_index": índice da fonte principal
- "periodo": trimestre/ano se identificável (ex: "2T26"), senão "não informado"
- "resumo_estrategico": 2 a 4 frases sobre o que a empresa prioriza no negócio de
  investimentos/varejo neste resultado
- "onde_colocam_energia": lista de focos declarados (ex: "captação líquida/NNM",
  "banking dentro da corretora", "IA no app", "expansão de assessoria")
- "movimentos_concretos": lista de lançamentos, mudanças de preço/take rate,
  novos segmentos ou plataformas citados
- "onde_deixam_a_desejar": lista de sinais de pressão/fraqueza no recorte
  corretora (ex: "queda de captação", "churn de assessores", "margem comprimida",
  "perda de share de varejo"); lista vazia se nada visível
- "oportunidade_para_nos": 1 frase — se e como isso abre brecha competitiva para
  o Santander explorar; "nenhuma clara" se não houver
- "copiar_ou_observar": exatamente um entre "copiar" (movimento que vale
  replicar), "observar" (monitorar de perto) ou "ignorar" (não muda nada para nós)
- "leitura_para_o_santander": 1 a 2 frases com a implicação competitiva para a
  corretora Santander
- "eixos": lista com 1+ eixos entre exatamente estes: {AXES}

Responda APENAS com um array JSON, sem markdown, sem texto antes ou depois."""


# ---------------------------------------------------------------------------
# Store de resultados (separado do history.json de notícias)
# ---------------------------------------------------------------------------

def load_results_history() -> list[dict]:
    if not RESULTS_HISTORY_PATH.exists():
        return []
    return json.loads(RESULTS_HISTORY_PATH.read_text(encoding="utf-8"))


def append_results_history(new_items: list[dict]) -> list[dict]:
    history = load_results_history()
    seen_links = {i.get("link") for i in history}
    for item in new_items:
        if item.get("link") not in seen_links:
            history.append(item)
            seen_links.add(item.get("link"))
    history.sort(key=lambda i: i.get("published_at", ""))
    RESULTS_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


# ---------------------------------------------------------------------------
# Download best-effort do texto do artigo
# ---------------------------------------------------------------------------

def fetch_article_text(link: str) -> str:
    try:
        resp = requests.get(link, timeout=ARTICLE_FETCH_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException:
        return ""
    html = resp.text
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:ARTICLE_MAX_CHARS]


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------

def _extract_classifications(parsed) -> list[dict]:
    """Normaliza a resposta do DeepSeek (modo json_object) para lista de dicts.

    Formatos aceitos: lista direta; lista dentro de uma chave (ex.: {"itens": [...]});
    uma classificação solta (acontece quando há um único item). Qualquer entrada
    que não seja objeto é descartada em vez de derrubar a execução.
    """
    if isinstance(parsed, dict) and ("primary_index" in parsed or "source_indices" in parsed or "axes" in parsed):
        candidates = [parsed]  # classificação única, sem o array em volta
    elif isinstance(parsed, list):
        candidates = parsed
    elif isinstance(parsed, dict):
        lists = [v for v in parsed.values() if isinstance(v, list) and any(isinstance(x, dict) for x in v)]
        candidates = lists[0] if lists else []
    else:
        candidates = []
    return [c for c in candidates if isinstance(c, dict)]


def classify_results(items: list[dict], api_key: str) -> list[dict]:
    if not items:
        return []

    payload_items = []
    for i, item in enumerate(items):
        body = fetch_article_text(item.get("link", ""))
        payload_items.append({
            "index": i,
            "competitor_group": item["competitor_group"],
            "title": item["title"],
            "summary": item.get("summary", ""),
            "texto": body or "(texto do artigo indisponível — use manchete e resumo)",
            "source": item.get("source", ""),
            "published_at": item.get("published_at", ""),
        })

    user_payload = {
        "focos": {group: cfg.get("focus", "") for group, cfg in RESULTS_ENTITIES.items()},
        "itens": payload_items,
    }

    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw_content = resp.json()["choices"][0]["message"]["content"]

    parsed = json.loads(raw_content)
    classifications = _extract_classifications(parsed)

    enriched = []
    for c in classifications:
        # ---- Validações determinísticas ----
        c["eixos"] = [a for a in c.get("eixos", []) if a in AXES]
        if not c["eixos"]:
            c["eixos"] = ["RV/Trading"]  # resultado sempre toca o negócio de RV/varejo
        if c.get("copiar_ou_observar") not in COPY_LABELS:
            c["copiar_ou_observar"] = "observar"

        source_indices = c.get("source_indices") or [c.get("primary_index", 0)]
        primary_idx = c.get("primary_index", source_indices[0])
        if not (0 <= primary_idx < len(items)):
            continue  # índice alucinado — descarta
        primary_item = items[primary_idx]

        other_sources = [
            {"source": items[i]["source"], "link": items[i]["link"]}
            for i in source_indices
            if i != primary_idx and 0 <= i < len(items)
        ]

        merged = {
            "competitor_group": primary_item["competitor_group"],
            "title": primary_item["title"],
            "link": primary_item["link"],
            "source": primary_item["source"],
            "published_at": primary_item["published_at"],
            "channel": "results",
            "also_reported_by": other_sources,
            **{k: v for k, v in c.items() if k not in ("source_indices", "primary_index")},
        }
        enriched.append(merged)
    return enriched


def main():
    if len(sys.argv) < 2:
        print("Uso: python src/synthesize_results.py data/raw_results_items_AAAA-MM-DD.json", file=sys.stderr)
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

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"classified_results_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not items:
        out_path.write_text("[]", encoding="utf-8")
        print("Sem itens de resultado hoje (não é dia de varredura ou nada novo). Nada a classificar.")
        return

    classified = classify_results(items, api_key)
    out_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    append_results_history(classified)
    print(f"Extraídos {len(classified)} resultados → {out_path}")


if __name__ == "__main__":
    main()
