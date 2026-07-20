"""
collect_social.py — Detecta POLÊMICAS e TRENDS envolvendo os concorrentes
por dois sinais, ambos no desenho de pico contra baseline (nunca leitura de
feed bruto — o custo fica próximo de zero e o ruído morre no limiar):

1. REDDIT — baixa os posts recentes dos subreddits configurados (1 request
   por subreddit), conta menções de cada grupo nas últimas 24h e compara com
   a média dos dias anteriores guardada no estado. Pico = item, com os posts
   mais votados como amostra.

2. GOOGLE TRENDS — interesse de busca das últimas 24h vs. média dos 6 dias
   anteriores para um termo por grupo. Polêmica grande = gente correndo pro
   Google atrás do nome do concorrente.

Na maioria dos dias este coletor emite ZERO itens — comportamento correto.

Como rodar:
    python src/collect_social.py

Saídas:
    data/raw_social_items_AAAA-MM-DD.json
    data/social_state.json — baselines diárias e controle de re-alerta

Credenciais (OPCIONAL, recomendado em CI): o endpoint público do Reddit
funciona sem autenticação, mas IPs de datacenter (GitHub Actions) às vezes
levam 403. Com as variáveis de ambiente REDDIT_CLIENT_ID e
REDDIT_CLIENT_SECRET definidas (app "script" criado em
reddit.com/prefs/apps, gratuito), o coletor usa a API OAuth oficial, muito
mais estável. Sem elas, tenta o endpoint público e degrada com aviso.

Google Trends usa a biblioteca pytrends (não-oficial). Quando o Google muda
algo, ela pode falhar com erro 429 por alguns dias — o coletor avisa e
segue só com o Reddit; não quebra o pipeline.

IMPORTANTE pra produção:
- data/social_state.json precisa ser COMMITADO de volta a cada execução
  (mesmo esquema dos demais state files).

Dependências: requests (já no pipeline), pytrends (adicionar ao
requirements.txt; instala pandas junto).
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from sources import (
    SOCIAL_BASELINE_MIN_DAYS,
    SOCIAL_REALERT_DAYS,
    SOCIAL_REDDIT_ALIASES,
    SOCIAL_SPIKE_MIN_MENTIONS,
    SOCIAL_SPIKE_MULTIPLIER,
    SOCIAL_SUBREDDITS,
    SOCIAL_TRENDS_TERMS,
    TRENDS_MIN_INTEREST,
    TRENDS_SPIKE_MULTIPLIER,
)

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_PATH = DATA_DIR / "social_state.json"

REDDIT_PUBLIC_URL = "https://www.reddit.com/r/{sub}/new.json?limit=100"
REDDIT_OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_OAUTH_URL = "https://oauth.reddit.com/r/{sub}/new?limit=100"
USER_AGENT = "radar-mercado/1.0 (monitoramento competitivo interno)"
REQUEST_TIMEOUT = 15

MENTION_WINDOW_HOURS = 24
BASELINE_KEEP_DAYS = 14  # dias de contagem guardados no estado


# ---------------------------------------------------------------------------
# Estado
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
    return datetime.fromisoformat(last) > now - timedelta(days=SOCIAL_REALERT_DAYS)


def mark_alerted(state: dict, key: str, now: datetime) -> None:
    state.setdefault("alerts", {})[key] = now.isoformat()


# ---------------------------------------------------------------------------
# Sinal 1 — Reddit
# ---------------------------------------------------------------------------

def _reddit_token() -> str | None:
    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        return None
    try:
        resp = requests.post(
            REDDIT_OAUTH_TOKEN_URL,
            auth=(cid, secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:
        print(f"[aviso] OAuth do Reddit falhou ({e}); tentando endpoint público", file=sys.stderr)
        return None


def fetch_subreddit_posts(sub: str, token: str | None) -> list[dict]:
    if token:
        url = REDDIT_OAUTH_URL.format(sub=sub)
        headers = {"User-Agent": USER_AGENT, "Authorization": f"bearer {token}"}
    else:
        url = REDDIT_PUBLIC_URL.format(sub=sub)
        headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    children = resp.json().get("data", {}).get("children", [])
    posts = []
    for child in children:
        d = child.get("data", {})
        posts.append({
            "title": d.get("title") or "",
            "selftext": d.get("selftext") or "",
            "created_utc": d.get("created_utc") or 0,
            "permalink": "https://www.reddit.com" + (d.get("permalink") or ""),
            "ups": d.get("ups") or 0,
            "subreddit": sub,
        })
    return posts


def _compile_alias_patterns() -> dict[str, list[re.Pattern]]:
    return {
        group: [re.compile(rf"\b{re.escape(a)}\b", re.IGNORECASE) for a in aliases]
        for group, aliases in SOCIAL_REDDIT_ALIASES.items()
    }


def count_reddit_mentions(posts: list[dict], now: datetime) -> dict[str, dict]:
    """Menções por grupo nas últimas MENTION_WINDOW_HOURS, com amostras."""
    patterns = _compile_alias_patterns()
    cutoff = now - timedelta(hours=MENTION_WINDOW_HOURS)
    result = {g: {"count": 0, "samples": []} for g in patterns}
    for post in posts:
        created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
        if created < cutoff:
            continue
        text = f'{post["title"]} {post["selftext"]}'
        for group, pats in patterns.items():
            if any(p.search(text) for p in pats):
                result[group]["count"] += 1
                result[group]["samples"].append(post)
    for g in result:
        result[g]["samples"].sort(key=lambda p: p["ups"], reverse=True)
        result[g]["samples"] = result[g]["samples"][:3]
    return result


def collect_reddit_spikes(state: dict, now: datetime) -> list[dict]:
    token = _reddit_token()
    posts: list[dict] = []
    for sub in SOCIAL_SUBREDDITS:
        try:
            posts.extend(fetch_subreddit_posts(sub, token))
        except Exception as e:
            print(f"[aviso] Reddit r/{sub}: {e}", file=sys.stderr)
    if not posts:
        print("[aviso] Reddit indisponível nesta execução; sinal pulado", file=sys.stderr)
        return []

    today = now.strftime("%Y-%m-%d")
    mentions = count_reddit_mentions(posts, now)
    items = []

    for group, data in mentions.items():
        daily = state.setdefault("reddit", {}).setdefault(group, {})
        daily[today] = data["count"]
        # apara o histórico
        for key in sorted(daily.keys())[:-BASELINE_KEEP_DAYS]:
            del daily[key]

        previous = [v for d, v in daily.items() if d != today]
        if len(previous) < SOCIAL_BASELINE_MIN_DAYS:
            continue  # ainda construindo baseline
        avg = sum(previous) / len(previous)
        count = data["count"]
        threshold = max(SOCIAL_SPIKE_MIN_MENTIONS, SOCIAL_SPIKE_MULTIPLIER * avg)
        if count < threshold or recently_alerted(state, f"reddit:{group}", now):
            continue

        sample_txt = " | ".join(
            f'"{p["title"][:90]}" ({p["ups"]} upvotes, r/{p["subreddit"]}, {p["permalink"]})'
            for p in data["samples"]
        )
        items.append({
            "competitor_group": group,
            "matched_alias": "Reddit",
            "title": (
                f"{group}: pico de menções no Reddit — {count} posts em 24h "
                f"(média dos últimos dias: {avg:.1f})"
            ),
            "link": data["samples"][0]["permalink"] if data["samples"] else f"https://www.reddit.com/r/{SOCIAL_SUBREDDITS[0]}/",
            "source": "Reddit",
            "published_at": now.isoformat(),
            "summary": (
                f"Volume de posts citando o grupo saltou para {count} nas últimas 24h, "
                f"contra média de {avg:.1f}/dia. Posts mais votados: {sample_txt}"
            ),
            "channel": "social",
        })
        mark_alerted(state, f"reddit:{group}", now)
    return items


# ---------------------------------------------------------------------------
# Sinal 2 — Google Trends
# ---------------------------------------------------------------------------

def fetch_trends_interest() -> dict[str, dict] | None:
    """Interesse por termo nos últimos 7 dias (horário). None se indisponível."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("[aviso] pytrends não instalado; sinal Trends pulado", file=sys.stderr)
        return None
    try:
        terms = list(SOCIAL_TRENDS_TERMS.values())[:5]
        pt = TrendReq(hl="pt-BR", tz=180, timeout=(10, 25), retries=3, backoff_factor=2)
        pt.build_payload(terms, timeframe="now 7-d", geo="BR")
        df = pt.interest_over_time()
        if df is None or df.empty:
            return None
        result = {}
        for group, term in SOCIAL_TRENDS_TERMS.items():
            if term not in df.columns:
                continue
            series = df[term]
            last24 = series.tail(24)
            previous = series.head(len(series) - 24)
            if previous.empty:
                continue
            result[group] = {
                "term": term,
                "recent_avg": float(last24.mean()),
                "baseline_avg": float(previous.mean()),
                "peak": int(series.max()),
            }
        return result
    except Exception as e:
        # pytrends quebra periodicamente (429 etc.) — degrada sem drama
        print(f"[aviso] Google Trends indisponível nesta execução: {e}", file=sys.stderr)
        return None


def collect_trends_spikes(state: dict, now: datetime) -> list[dict]:
    interest = fetch_trends_interest()
    if not interest:
        return []
    items = []
    for group, data in interest.items():
        recent, baseline = data["recent_avg"], data["baseline_avg"]
        key = f"trends:{group}"
        spiked = (
            recent >= TRENDS_MIN_INTEREST
            and baseline > 0
            and recent >= TRENDS_SPIKE_MULTIPLIER * baseline
        )
        # baseline zerada + interesse relevante do nada também é pico
        if baseline == 0 and recent >= TRENDS_MIN_INTEREST:
            spiked = True
        if not spiked or recently_alerted(state, key, now):
            continue
        term_q = data["term"].replace(" ", "%20")
        items.append({
            "competitor_group": group,
            "matched_alias": "Google Trends",
            "title": (
                f"{group}: pico de buscas no Google por \"{data['term']}\" "
                f"(interesse {recent:.0f} nas últimas 24h vs. média {baseline:.0f})"
            ),
            "link": f"https://trends.google.com.br/trends/explore?date=now%207-d&geo=BR&q={term_q}",
            "source": "Google Trends",
            "published_at": now.isoformat(),
            "summary": (
                f"O interesse de busca por \"{data['term']}\" no Brasil saltou para "
                f"{recent:.0f} (escala 0-100) nas últimas 24h, contra média de "
                f"{baseline:.0f} nos 6 dias anteriores (pico da semana: {data['peak']}). "
                f"Salto de busca costuma indicar polêmica, incidente ou notícia grande "
                f"em circulação — cruze com os demais sinais do radar do dia."
            ),
            "channel": "social",
        })
        mark_alerted(state, key, now)
    return items


# ---------------------------------------------------------------------------

def main():
    now = datetime.now(timezone.utc)
    state = load_state()

    items = []
    items += collect_reddit_spikes(state, now)
    items += collect_trends_spikes(state, now)

    save_state(state)

    today = now.strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"raw_social_items_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Social: {len(items)} itens → {out_path}")


if __name__ == "__main__":
    main()
