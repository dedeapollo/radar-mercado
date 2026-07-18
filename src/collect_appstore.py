"""
collect_appstore.py — Monitora os apps Android dos concorrentes na Google
Play: patch notes ("O que há de novo") e nota média. Emite itens no mesmo
formato do collect.py sempre que detecta mudança em relação ao último
estado salvo.

Como rodar:
    python src/collect_appstore.py

Saídas:
    data/raw_appstore_items_AAAA-MM-DD.json — itens novos detectados hoje
        (pode ser vazio: nenhum app atualizou = nenhum item, e está certo)
    data/appstore_state.json — estado por app (versão, patch notes, nota)

IMPORTANTE pra produção:
- data/appstore_state.json precisa ser COMMITADO de volta no repositório a
  cada execução (mesmo esquema do history.json) — sem isso, toda execução
  acha que tudo é "novo" e dispara itens repetidos.
- Precisa de acesso real a play.google.com — funciona no GitHub Actions e
  localmente; não roda no sandbox do Claude (rede restrita).

Dependência: google-play-scraper (adicionar ao requirements.txt)
    pip install google-play-scraper
"""

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from google_play_scraper import app as gp_app
from google_play_scraper.exceptions import NotFoundError

sys.path.insert(0, str(Path(__file__).parent))
from sources import APPSTORE_SCORE_DROP_THRESHOLD, PLAY_STORE_APPS

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_PATH = DATA_DIR / "appstore_state.json"
PLAY_URL = "https://play.google.com/store/apps/details?id={pkg}&hl=pt_BR&gl=BR"

TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def strip_html(text: str | None) -> str:
    """Patch notes vêm com HTML (<br>, <b>...) — converte pra texto puro."""
    if not text:
        return ""
    text = BR_RE.sub("\n", text)
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    # normaliza linhas em branco múltiplas
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_app(pkg: str) -> dict | None:
    """Busca os dados atuais de um app na Play Store."""
    try:
        info = gp_app(pkg, lang="pt", country="br")
    except NotFoundError:
        print(f"[aviso] app não encontrado na Play Store: {pkg} "
              f"(foi removido ou o package ID mudou — atualize sources.py)", file=sys.stderr)
        return None
    except Exception as e:  # rede, parse, mudança de layout da Play Store
        print(f"[aviso] falha ao buscar {pkg}: {e}", file=sys.stderr)
        return None

    updated_ts = info.get("updated")
    updated_iso = (
        datetime.fromtimestamp(updated_ts, tz=timezone.utc).isoformat()
        if updated_ts
        else datetime.now(timezone.utc).isoformat()
    )
    return {
        "version": info.get("version") or "",
        "recent_changes": strip_html(info.get("recentChanges")),
        "score": round(info["score"], 2) if info.get("score") else None,
        "ratings": info.get("ratings"),
        "updated_at": updated_iso,
        "app_title": info.get("title") or "",
    }


def make_patch_item(group: str, app_name: str, pkg: str, current: dict, previous: dict | None) -> dict:
    version = current["version"]
    version_txt = f" (v{version})" if version else ""
    if previous is None:
        title = f"{app_name}: início do monitoramento do app Android{version_txt}"
    else:
        title = f"{app_name} atualiza app Android{version_txt} — novidades no changelog"

    notes = current["recent_changes"] or "(sem descrição de mudanças publicada)"
    return {
        "competitor_group": group,
        "matched_alias": app_name,
        "title": title,
        "link": PLAY_URL.format(pkg=pkg),
        "source": "Google Play",
        "published_at": current["updated_at"],
        "summary": notes,
        "channel": "appstore",
    }


def make_score_drop_item(group: str, app_name: str, pkg: str, current: dict, previous: dict) -> dict:
    return {
        "competitor_group": group,
        "matched_alias": app_name,
        "title": (
            f"{app_name}: nota do app Android caiu de {previous['score']} "
            f"para {current['score']} na Play Store"
        ),
        "link": PLAY_URL.format(pkg=pkg),
        "source": "Google Play",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "summary": (
            f"A nota média do app caiu {previous['score']} → {current['score']} "
            f"({current.get('ratings') or '?'} avaliações no total). Queda de nota costuma "
            f"indicar onda recente de avaliações negativas — possível problema de "
            f"estabilidade, mudança mal recebida ou incidente. Vale abrir as avaliações "
            f"recentes na Play Store para entender o motivo."
        ),
        "channel": "appstore",
    }


def collect_all() -> list[dict]:
    state = load_state()
    items: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for group, apps in PLAY_STORE_APPS.items():
        for app_name, pkg in apps.items():
            current = fetch_app(pkg)
            if current is None:
                continue  # falha pontual: mantém estado anterior intacto

            previous = state.get(pkg)

            changed = (
                previous is None
                or current["version"] != previous.get("version")
                or current["recent_changes"] != previous.get("recent_changes", "")
            )
            if changed:
                items.append(make_patch_item(group, app_name, pkg, current, previous))

            if (
                previous is not None
                and current["score"] is not None
                and previous.get("score") is not None
                and (previous["score"] - current["score"]) >= APPSTORE_SCORE_DROP_THRESHOLD
            ):
                items.append(make_score_drop_item(group, app_name, pkg, current, previous))

            state[pkg] = {**current, "checked_at": now_iso, "group": group, "app_name": app_name}

    save_state(state)
    return items


def main():
    items = collect_all()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"raw_appstore_items_{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"App stores: {len(items)} itens novos → {out_path}")


if __name__ == "__main__":
    main()
