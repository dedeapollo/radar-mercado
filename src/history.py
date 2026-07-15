"""
history.py — Mantém um histórico acumulado de itens classificados ao longo
do tempo. Semanal e mensal olham pra trás no tempo, não só pro dia de hoje,
então precisam desse acúmulo.

IMPORTANTE pra produção: data/history.json precisa ser commitado de volta
no repositório a cada execução do GitHub Actions — runners são efêmeros,
sem isso o histórico se perde a cada execução. Isso entra no workflow.yml
quando montarmos o agendador.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY_PATH = Path(__file__).parent.parent / "data" / "history.json"


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def append_to_history(new_items: list[dict]) -> list[dict]:
    history = load_history()
    seen_links = {item["link"] for item in history}
    for item in new_items:
        if item["link"] not in seen_links:
            history.append(item)
            seen_links.add(item["link"])
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def get_items_since(history: list[dict], days: int, reference_date: datetime | None = None) -> list[dict]:
    reference_date = reference_date or datetime.now(timezone.utc)
    cutoff = reference_date - timedelta(days=days)
    result = []
    for item in history:
        published = datetime.fromisoformat(item["published_at"])
        if published >= cutoff:
            result.append(item)
    return result
