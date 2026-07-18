"""
collect_incidents.py — Detecta INCIDENTES operacionais nos concorrentes por
três sinais independentes, do mais lento ao mais antecipado:

1. NOTÍCIAS DIRECIONADAS — queries no Google News combinando cada alias com
   termos de incidente ("fora do ar", "instabilidade"...). Captura incidentes
   grandes o suficiente pra virar pauta (geralmente com atraso de horas).

2. PICO DE REVIEWS NEGATIVOS — reviews recentes de 1-2 estrelas na Play Store
   com palavras de indisponibilidade. Captura incidentes que NUNCA viram
   notícia — o sinal antecipado. É daqui que sai o alerta tipo "clientes
   reclamam de mau funcionamento na Genial".

3. RECLAME AQUI (EXPERIMENTAL) — salto no volume de reclamações recentes.
   Desativado por padrão (RECLAME_AQUI_COMPANIES vazio em sources.py); o site
   tem proteção anti-bot que pode bloquear o runner. Se falhar, o coletor
   segue normalmente sem esse sinal.

Como rodar:
    python src/collect_incidents.py

Saídas:
    data/raw_incident_items_AAAA-MM-DD.json — itens detectados hoje (pode ser
        vazio, e na maioria dos dias VAI ser — incidente é raro, e é isso que
        torna o alerta valioso)
    data/incidents_state.json — controle de re-alerta e baselines

IMPORTANTE pra produção:
- data/incidents_state.json precisa ser COMMITADO de volta a cada execução
  (mesmo esquema de history.json e appstore_state.json).
- Precisa de internet real (news.google.com, play.google.com) — GitHub
  Actions ou local; não roda no sandbox do Claude.

Dependências: feedparser, requests, google-play-scraper (já no pipeline).
"""

import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from google_play_scraper import Sort
from google_play_scraper import reviews as gp_reviews

sys.path.insert(0, str(Path(__file__).parent))
from sources import (
    COMPETITOR_GROUPS,
    INCIDENT_NEWS_TERMS,
    INCIDENT_REALERT_DAYS,
    INCIDENT_REVIEW_KEYWORDS,
    PLAY_STORE_APPS,
    RECLAME_AQUI_COMPANIES,
    RECLAME_AQUI_JUMP_THRESHOLD,
    REVIEW_INCIDENT_THRESHOLD,
    REVIEW_LOOKBACK_DAYS,
    REVIEWS_FETCH_COUNT,
)

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_PATH = DATA_DIR / "incidents_state.json"

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-BR"
PLAY_URL = "https://play.google.com/store/apps/details?id={pkg}&hl=pt_BR&gl=BR"
RECLAME_AQUI_URL = "https://www.reclameaqui.com.br/empresa/{slug}/"
NEWS_LOOKBACK_DAYS = 2
REQUEST_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Estado (re-alerta e baselines)
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
    return datetime.fromisoformat(last) > now - timedelta(days=INCIDENT_REALERT_DAYS)


def mark_alerted(state: dict, key: str, now: datetime) -> None:
    state.setdefault("alerts", {})[key] = now.isoformat()


# ---------------------------------------------------------------------------
# Sinal 1 — Google News direcionado
# ---------------------------------------------------------------------------

def news_incident_query(alias: str) -> str:
    terms = " OR ".join(f'"{t}"' for t in INCIDENT_NEWS_TERMS)
    return urllib.parse.quote(f'"{alias}" ({terms})')


def collect_news_incidents() -> list[dict]:
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_LOOKBACK_DAYS)
    for group, aliases in COMPETITOR_GROUPS.items():
        for alias in aliases:
            url = GOOGLE_NEWS_RSS.format(query=news_incident_query(alias))
            try:
                resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"[aviso] news incidente '{alias}': {e}", file=sys.stderr)
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
                    "channel": "incident",
                })
    # dedup por link (a mesma matéria pode bater em mais de um alias/termo)
    seen, deduped = set(), []
    for item in items:
        if item["link"] not in seen:
            seen.add(item["link"])
            deduped.append(item)
    return deduped


# ---------------------------------------------------------------------------
# Sinal 2 — pico de reviews negativos na Play Store
# ---------------------------------------------------------------------------

def _clean_excerpt(text: str, max_len: int = 100) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[: max_len - 1] + "…" if len(text) > max_len else text


def scan_app_reviews(pkg: str) -> tuple[int, int, list[str]]:
    """Retorna (negativos na janela, negativos com palavra de incidente, amostras)."""
    result, _ = gp_reviews(
        pkg, lang="pt", country="br", sort=Sort.NEWEST, count=REVIEWS_FETCH_COUNT
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=REVIEW_LOOKBACK_DAYS)
    negatives = 0
    incident_hits = 0
    samples: list[str] = []
    for r in result:
        at = r.get("at")
        if at is None:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at < cutoff:
            continue
        if (r.get("score") or 5) > 2:
            continue
        negatives += 1
        content = (r.get("content") or "").lower()
        if any(kw in content for kw in INCIDENT_REVIEW_KEYWORDS):
            incident_hits += 1
            if len(samples) < 3:
                samples.append(_clean_excerpt(r.get("content", "")))
    return negatives, incident_hits, samples


def collect_review_spikes(state: dict, now: datetime) -> list[dict]:
    items = []
    for group, apps in PLAY_STORE_APPS.items():
        for app_name, pkg in apps.items():
            key = f"reviews:{pkg}"
            if recently_alerted(state, key, now):
                continue
            try:
                negatives, incident_hits, samples = scan_app_reviews(pkg)
            except Exception as e:
                print(f"[aviso] reviews {pkg}: {e}", file=sys.stderr)
                continue
            if incident_hits < REVIEW_INCIDENT_THRESHOLD:
                continue
            quotes = " | ".join(f'"{s}"' for s in samples)
            items.append({
                "competitor_group": group,
                "matched_alias": app_name,
                "title": (
                    f"{app_name}: pico de reclamações de mau funcionamento na Play Store "
                    f"({incident_hits} avaliações negativas citando indisponibilidade em "
                    f"{REVIEW_LOOKBACK_DAYS * 24}h)"
                ),
                "link": PLAY_URL.format(pkg=pkg),
                "source": "Google Play (reviews)",
                "published_at": now.isoformat(),
                "summary": (
                    f"{negatives} avaliações de 1-2 estrelas na janela, {incident_hits} delas "
                    f"citando problemas de funcionamento. Amostras: {quotes}"
                ),
                "channel": "incident",
            })
            mark_alerted(state, key, now)
    return items


# ---------------------------------------------------------------------------
# Sinal 3 — Reclame Aqui (experimental, desativado por padrão)
# ---------------------------------------------------------------------------

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def fetch_reclameaqui_total(slug: str) -> int | None:
    """Tenta extrair o total de reclamações recentes da página pública.

    EXPERIMENTAL: o Reclame Aqui usa proteção anti-bot; em runners de CI a
    requisição pode voltar bloqueada. Qualquer falha retorna None e o
    coletor segue sem esse sinal.
    """
    try:
        resp = requests.get(
            RECLAME_AQUI_URL.format(slug=slug),
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR"},
        )
        resp.raise_for_status()
        match = _NEXT_DATA_RE.search(resp.text)
        if not match:
            return None
        payload = json.loads(match.group(1))
        # procura recursivamente por um campo de total de reclamações no
        # payload do Next.js (a estrutura interna muda sem aviso)
        def find_total(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in ("complains", "totalComplains", "complainsCount") and isinstance(v, int):
                        return v
                    found = find_total(v)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for v in node:
                    found = find_total(v)
                    if found is not None:
                        return found
            return None
        return find_total(payload)
    except Exception as e:
        print(f"[aviso] Reclame Aqui '{slug}': {e}", file=sys.stderr)
        return None


def collect_reclameaqui(state: dict, now: datetime) -> list[dict]:
    items = []
    for group, slug in RECLAME_AQUI_COMPANIES.items():
        key = f"reclameaqui:{slug}"
        total = fetch_reclameaqui_total(slug)
        if total is None:
            continue
        baseline = state.get("reclameaqui", {}).get(slug)
        state.setdefault("reclameaqui", {})[slug] = total
        if baseline is None:
            continue  # primeira leitura: só grava baseline
        jump = total - baseline
        if jump < RECLAME_AQUI_JUMP_THRESHOLD or recently_alerted(state, key, now):
            continue
        items.append({
            "competitor_group": group,
            "matched_alias": f"Reclame Aqui ({slug})",
            "title": f"{group}: salto de {jump} reclamações no Reclame Aqui desde a última verificação",
            "link": RECLAME_AQUI_URL.format(slug=slug),
            "source": "Reclame Aqui",
            "published_at": now.isoformat(),
            "summary": (
                f"Total de reclamações recentes foi de {baseline} para {total} "
                f"(+{jump}). Salto atípico costuma indicar incidente, mudança mal "
                f"recebida ou polêmica em curso — vale abrir as reclamações recentes "
                f"para identificar o tema dominante."
            ),
            "channel": "incident",
        })
        mark_alerted(state, key, now)
    return items


# ---------------------------------------------------------------------------

def main():
    now = datetime.now(timezone.utc)
    state = load_state()

    items = []
    items += collect_news_incidents()
    items += collect_review_spikes(state, now)
    items += collect_reclameaqui(state, now)

    save_state(state)

    today = now.strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"raw_incident_items_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Incidentes: {len(items)} itens → {out_path}")


if __name__ == "__main__":
    main()
