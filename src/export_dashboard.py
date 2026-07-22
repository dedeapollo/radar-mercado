"""
export_dashboard.py — Gera docs/data.json a partir de data/history.json
(notícias) e data/results_history.json (resultados), no formato que o
dashboard espera.

Além dos itens de notícia e resultado, calcula um STATUS DERIVADO por
concorrente — base da página "Status & Intercorrências". O status NÃO é
tempo real: é a situação segundo o ÚLTIMO INCIDENTE CONHECIDO (itens com
trigger_reason == "INC" no histórico). Se houve incidente nos últimos
STATUS_RECENT_DAYS dias → "instavel_recente"; senão → "estavel". A página
também recebe o histórico de intercorrências por concorrente.

Como rodar:
    python src/export_dashboard.py

Roda depois de report.py / report_results.py no workflow, para exportar o
histórico mais recente pro dashboard.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sources import COMPETITOR_GROUPS

DASHBOARD_WINDOW_DAYS = 90       # janela de notícias carregada no navegador
RESULTS_WINDOW_DAYS = 400        # resultados são trimestrais — janela ampla
INCIDENT_WINDOW_DAYS = 180       # histórico de intercorrências exibido
STATUS_RECENT_DAYS = 3           # INC nos últimos N dias => "instavel_recente"

BASE_DIR = Path(__file__).parent.parent


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _parse(dt: str) -> datetime | None:
    try:
        return datetime.fromisoformat(dt)
    except (ValueError, TypeError):
        return None


def within(item: dict, cutoff: datetime) -> bool:
    d = _parse(item.get("published_at", ""))
    return d is not None and d >= cutoff


def build_status(history: list[dict], now: datetime) -> dict:
    """Status derivado por concorrente + histórico de intercorrências (INC)."""
    inc_cutoff = now - timedelta(days=INCIDENT_WINDOW_DAYS)
    recent_cutoff = now - timedelta(days=STATUS_RECENT_DAYS)
    status = {}
    for group in COMPETITOR_GROUPS:
        incs = [
            i for i in history
            if i.get("competitor_group") == group and i.get("trigger_reason") == "INC"
        ]
        incs.sort(key=lambda i: i.get("published_at", ""), reverse=True)
        last = incs[0] if incs else None
        last_dt = _parse(last["published_at"]) if last else None
        is_recent = last_dt is not None and last_dt >= recent_cutoff

        status[group] = {
            "status": "instavel_recente" if is_recent else "estavel",
            "last_incident_at": last["published_at"] if last else None,
            "last_incident_title": last["title"] if last else None,
            "incident_count_window": sum(1 for i in incs if within(i, inc_cutoff)),
            "incidents": [
                {
                    "published_at": i.get("published_at"),
                    "title": i.get("title"),
                    "link": i.get("link"),
                    "source": i.get("source"),
                    "why_it_matters": i.get("why_it_matters", ""),
                    "axes": i.get("axes", []),
                }
                for i in incs if within(i, inc_cutoff)
            ][:60],
        }
    return status


def main():
    history = load_json(BASE_DIR / "data" / "history.json", [])
    results_history = load_json(BASE_DIR / "data" / "results_history.json", [])
    out_path = BASE_DIR / "docs" / "data.json"

    now = datetime.now(timezone.utc)
    news_cutoff = now - timedelta(days=DASHBOARD_WINDOW_DAYS)
    results_cutoff = now - timedelta(days=RESULTS_WINDOW_DAYS)

    recent_news = [i for i in history if within(i, news_cutoff)]
    recent_results = [r for r in results_history if within(r, results_cutoff)]
    recent_results.sort(key=lambda r: r.get("published_at", ""), reverse=True)

    payload = {
        "generated_at": now.isoformat(),
        "items": recent_news,
        "results": recent_results,
        "status_by_competitor": build_status(history, now),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Dashboard atualizado: {len(recent_news)} notícias, {len(recent_results)} resultados, "
        f"status de {len(payload['status_by_competitor'])} concorrentes → {out_path}"
    )


if __name__ == "__main__":
    main()
