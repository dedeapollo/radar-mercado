"""
export_dashboard.py — Gera docs/data.json a partir de data/history.json,
no formato que o dashboard (docs/index.html) espera.

Como rodar:
    python src/export_dashboard.py

Roda depois de report.py no workflow, pra sempre exportar o histórico mais
recente pro dashboard.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DASHBOARD_WINDOW_DAYS = 90  # não faz sentido carregar o histórico inteiro pro navegador


def main():
    history_path = Path(__file__).parent.parent / "data" / "history.json"
    out_path = Path(__file__).parent.parent / "docs" / "data.json"

    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []

    cutoff = datetime.now(timezone.utc) - timedelta(days=DASHBOARD_WINDOW_DAYS)
    recent = [item for item in history if datetime.fromisoformat(item["published_at"]) >= cutoff]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": recent,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Dashboard atualizado: {len(recent)} itens (janela de {DASHBOARD_WINDOW_DAYS} dias) → {out_path}")


if __name__ == "__main__":
    main()
