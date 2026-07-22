"""
collect.py — Coleta notícias recentes sobre os concorrentes via Google News RSS.

Como rodar:
    python src/collect.py

Saída:
    data/raw_items_AAAA-MM-DD.json — lista de itens brutos coletados hoje.

IMPORTANTE: este script precisa de acesso real à internet (news.google.com).
Não roda dentro do sandbox do Claude (rede restrita) — foi testado aqui
apenas com um feed RSS mock, de forma isolada. Vai funcionar normalmente
no GitHub Actions ou rodando localmente na sua máquina.

Nota sobre a query: por padrão cada alias vira uma busca por FRASE EXATA
("XP Investimentos"). Para grupos listados em NEWS_GROUP_QUALIFIERS (ex.:
Nubank, que não tem marca de investimento própria no noticiário), a query
passa a ser o alias-base combinado com qualificadores de investimento —
"Nubank" ("corretora" OR "renda variável" OR ...) — para separar a pauta de
investimentos do ruído de cartão/conta.
"""

import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).parent))
from sources import COMPETITOR_GROUPS, NEWS_GROUP_QUALIFIERS

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-BR"
LOOKBACK_DAYS = 3  # margem de segurança para não perder itens entre execuções
REQUEST_TIMEOUT = 15


def build_query(group: str, alias: str) -> str:
    """Monta a query do Google News para um grupo/alias.

    - Grupo sem qualificadores: busca a frase exata do alias.
    - Grupo com qualificadores (ex.: Nubank): alias-base + (q1 OR q2 OR ...),
      para restringir ao recorte de investimentos.
    """
    qualifiers = NEWS_GROUP_QUALIFIERS.get(group)
    if qualifiers:
        terms = " OR ".join(f'"{q}"' if " " in q else q for q in qualifiers)
        raw = f'"{alias}" ({terms})'
    else:
        raw = f'"{alias}"'
    return urllib.parse.quote(raw)


def fetch_feed(group: str, alias: str) -> list[dict]:
    """Busca e faz parse do feed RSS do Google News para um grupo/alias."""
    url = GOOGLE_NEWS_RSS.format(query=build_query(group, alias))
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    return parsed.entries


def parse_entry(entry, competitor_group: str, alias: str) -> dict | None:
    """Converte uma entrada do feedparser no formato interno do radar."""
    try:
        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    except (AttributeError, TypeError):
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    if pub_date < cutoff:
        return None

    source = entry.get("source", {}).get("title", "Desconhecida") if hasattr(entry, "get") else "Desconhecida"

    return {
        "competitor_group": competitor_group,
        "matched_alias": alias,
        "title": entry.title,
        "link": entry.link,
        "source": source,
        "published_at": pub_date.isoformat(),
        "summary": entry.get("summary", ""),
    }


def collect_all() -> list[dict]:
    all_items = []
    for group, aliases in COMPETITOR_GROUPS.items():
        for alias in aliases:
            try:
                entries = fetch_feed(group, alias)
            except requests.RequestException as e:
                print(f"[aviso] falha ao buscar '{alias}': {e}", file=sys.stderr)
                continue
            for entry in entries:
                item = parse_entry(entry, group, alias)
                if item:
                    all_items.append(item)

    # Dedup por link (mesma notícia pode aparecer em mais de um alias)
    seen = set()
    deduped = []
    for item in all_items:
        if item["link"] not in seen:
            seen.add(item["link"])
            deduped.append(item)
    return deduped


def main():
    items = collect_all()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = Path(__file__).parent.parent / "data" / f"raw_items_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Coletados {len(items)} itens únicos → {out_path}")


if __name__ == "__main__":
    main()
