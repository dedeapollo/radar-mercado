"""
collect_results.py — Coleta a COBERTURA DE RESULTADOS TRIMESTRAIS dos
concorrentes para a seção "Resultados e Estratégia" do radar.

O foco NÃO é indicador econômico/valuation — é reunir a cobertura do release
de resultados de cada concorrente para que o synthesize_results.py depois
EXTRAIA A ESTRATÉGIA (onde colocam energia, o que lançaram/mudaram, e onde
estão deixando a desejar), sempre no recorte do negócio de investimentos/varejo.

Cadência: varredura SEMANAL. Por padrão roda só no RESULTS_SWEEP_WEEKDAY
(segunda-feira, configurável em sources.py). O coletor é chamado todo dia
junto do pipeline, mas nos dias que não são de varredura ele apenas grava um
arquivo vazio e sai — assim não precisa de um workflow separado. Use --force
para varrer fora do dia (teste).

Fonte: Google News RSS com queries direcionadas a resultado por entidade
(mesma mecânica comprovada do collect.py / collect_incidents.py). A cobertura
de imprensa de um resultado aparece de forma confiável e linka de volta ao
release/apresentação — material suficiente para a extração de estratégia.
Gancho para RI/EDGAR direto pode ser adicionado depois em RESULTS_ENTITIES.

A Genial não está em RESULTS_ENTITIES (empresa fechada, sem release público
padronizado) — entra só quando divulga algo voluntariamente, via collect.py.

Como rodar:
    python src/collect_results.py            # respeita o dia da varredura
    python src/collect_results.py --force    # varre agora (teste)

Saídas:
    data/raw_results_items_AAAA-MM-DD.json   # itens de resultado (channel="results")
    data/results_state.json                  # controle de re-alerta por entidade

IMPORTANTE (igual aos outros coletores): precisa de internet real
(news.google.com) — roda no GitHub Actions ou local, não no sandbox do Claude.
data/results_state.json precisa ser commitado de volta a cada execução.

Dependências: feedparser, requests (já no pipeline).
"""

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).parent))
from sources import (
    RESULTS_ENTITIES,
    RESULTS_LOOKBACK_DAYS,
    RESULTS_NEWS_TERMS,
    RESULTS_REALERT_DAYS,
    RESULTS_SWEEP_WEEKDAY,
)

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_PATH = DATA_DIR / "results_state.json"

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-BR"
REQUEST_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Estado (re-alerta por entidade — evita re-emitir o mesmo resultado semana
# após semana durante a janela em que ele ainda aparece no noticiário)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def recently_alerted(state: dict, key: str, now: datetime) -> bool:
    last = state.get("alerts", {}).get(key)
    if not last:
        return False
    return datetime.fromisoformat(last) > now - timedelta(days=RESULTS_REALERT_DAYS)


def mark_alerted(state: dict, key: str, now: datetime) -> None:
    state.setdefault("alerts", {})[key] = now.isoformat()


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------

def results_query(alias: str) -> str:
    terms = " OR ".join(f'"{t}"' for t in RESULTS_NEWS_TERMS)
    return urllib.parse.quote(f'"{alias}" ({terms})')


def collect_for_group(group: str, cfg: dict, now: datetime) -> list[dict]:
    items = []
    cutoff = now - timedelta(days=RESULTS_LOOKBACK_DAYS)
    for alias in cfg.get("query_aliases", []):
        url = GOOGLE_NEWS_RSS.format(query=results_query(alias))
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[aviso] resultados '{alias}': {e}", file=sys.stderr)
            continue
        for entry in feedparser.parse(resp.content).entries:
            try:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except (AttributeError, TypeError):
                continue
            if pub < cutoff:
                continue
            source = entry.get("source", {}).get("title", "Desconhecida") if hasattr(entry, "get") else "Desconhecida"
            items.append({
                "competitor_group": group,
                "matched_alias": alias,
                "title": entry.title,
                "link": entry.link,
                "source": source,
                "published_at": pub.isoformat(),
                "summary": entry.get("summary", ""),
                "channel": "results",
            })
    # dedup por link (a mesma matéria pode bater em mais de um alias)
    seen, deduped = set(), []
    for item in items:
        if item["link"] not in seen:
            seen.add(item["link"])
            deduped.append(item)
    return deduped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Varre agora, ignorando o dia da varredura")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"raw_results_items_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    is_sweep_day = now.weekday() == RESULTS_SWEEP_WEEKDAY
    if not (is_sweep_day or args.force):
        out_path.write_text("[]", encoding="utf-8")
        print(f"Hoje não é dia de varredura de resultados (weekday={now.weekday()}, "
              f"esperado={RESULTS_SWEEP_WEEKDAY}). Arquivo vazio gravado.")
        return

    state = load_state()
    all_items = []
    for group, cfg in RESULTS_ENTITIES.items():
        key = f"results:{group}"
        if recently_alerted(state, key, now):
            print(f"[skip] {group}: resultado já reportado nos últimos {RESULTS_REALERT_DAYS} dias")
            continue
        group_items = collect_for_group(group, cfg, now)
        if group_items:
            all_items.extend(group_items)
            mark_alerted(state, key, now)
            print(f"[ok] {group}: {len(group_items)} matérias de resultado")

    save_state(state)
    out_path.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Coletados {len(all_items)} itens de resultado → {out_path}")


if __name__ == "__main__":
    main()
