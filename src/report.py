"""
report.py — Decide quais relatórios (diário/semanal/mensal) devem ser
gerados hoje, monta o conteúdo em HTML e envia por e-mail via Resend.

Como rodar:
    export RESEND_API_KEY="..."
    export DEEPSEEK_API_KEY="..."   # só necessário se for gerar o mensal
    python src/report.py data/classified_items_AAAA-MM-DD.json --to seu@email.com

Flags úteis pra testar sem esperar o calendário:
    --date AAAA-MM-DD   simula "hoje" como outra data (testa lógica semanal/mensal)
    --dry-run           monta o conteúdo e imprime no terminal, sem enviar de verdade
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from history import append_to_history, get_items_since
from email_delivery import send_email

AXES = ["RV/Trading", "Tecnologia", "Produtos Novos", "Risco/Regulação"]
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


def item_html(item: dict) -> str:
    return f"""
    <div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #eee;">
      <strong>[{item['competitor_group']}] {item['title']}</strong><br>
      <span style="color:#555;">{item['why_it_matters']}</span><br>
      <a href="{item['link']}">{item['source']}</a> · {item['published_at'][:10]}
    </div>
    """


def build_daily_report(today_items: list[dict], report_date: str) -> dict | None:
    triggered = [i for i in today_items if i.get("daily_trigger")]
    if not triggered:
        return None
    body = "".join(item_html(i) for i in triggered)
    return {"subject": f"🔴 Radar de Mercado — Alerta ({report_date})", "html": f"<h2>Alertas do dia</h2>{body}"}


def build_weekly_report(week_items: list[dict], report_date: str) -> dict:
    sections = ""
    for axis in AXES:
        axis_items = [i for i in week_items if axis in i.get("axes", [])]
        if not axis_items:
            continue
        sections += f"<h3>{axis}</h3>" + "".join(item_html(i) for i in axis_items)
    return {
        "subject": f"🟡 Radar de Mercado — Semanal ({report_date})",
        "html": f"<h2>Resumo da semana</h2>{sections or '<p>Nenhum item relevante nesta semana.</p>'}",
    }


def generate_cross_cutting_signals(month_items: list[dict], api_key: str) -> str:
    if not month_items:
        return ""
    titles = "\n".join(f"- [{i['competitor_group']}] {i['title']}" for i in month_items)
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Você é analista de inteligência competitiva do setor de investimentos "
                        "brasileiro. Dada uma lista de eventos do mês envolvendo concorrentes, "
                        "identifique de 2 a 4 sinais transversais — padrões que conectam múltiplos "
                        "concorrentes ou sugerem uma tendência de mercado. Responda em HTML simples "
                        "(uma lista <ul><li>), em português, sem markdown."
                    ),
                },
                {"role": "user", "content": titles},
            ],
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def build_monthly_report(month_items: list[dict], report_date: str, deepseek_key: str | None) -> dict:
    sections = ""
    for axis in AXES:
        axis_items = [i for i in month_items if axis in i.get("axes", [])]
        if not axis_items:
            continue
        sections += f"<h3>{axis}</h3>" + "".join(item_html(i) for i in axis_items)

    signals_html = ""
    if deepseek_key:
        signals = generate_cross_cutting_signals(month_items, deepseek_key)
        signals_html = f"<h2>Sinais transversais</h2>{signals}"

    return {
        "subject": f"🟢 Radar de Mercado — Panorama Mensal ({report_date})",
        "html": f"<h2>Panorama do mês</h2>{sections}{signals_html}",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("classified_file")
    parser.add_argument("--date", help="Simula uma data (AAAA-MM-DD) em vez de usar hoje")
    parser.add_argument("--dry-run", action="store_true", help="Monta o conteúdo mas não envia e-mail")
    parser.add_argument("--to", help="E-mail de destino para teste")
    args = parser.parse_args()

    today_items = json.loads(Path(args.classified_file).read_text(encoding="utf-8"))
    history = append_to_history(today_items)

    ref_date = (
        datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.date
        else datetime.now(timezone.utc)
    )
    report_date = ref_date.strftime("%Y-%m-%d")

    reports = []

    daily = build_daily_report(today_items, report_date)
    if daily:
        reports.append(daily)

    if ref_date.weekday() == 0:  # segunda-feira
        week_items = get_items_since(history, days=7, reference_date=ref_date)
        reports.append(build_weekly_report(week_items, report_date))

    if ref_date.day == 1:
        month_items = get_items_since(history, days=30, reference_date=ref_date)
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        reports.append(build_monthly_report(month_items, report_date, deepseek_key))

    if not reports:
        print("Nenhum relatório elegível para hoje (sem gatilho diário, não é segunda, não é dia 1).")
        return

    if args.to:
        recipients = [args.to]
    else:
        env_recipients = os.environ.get("EMAIL_RECIPIENTS", "")
        recipients = [r.strip() for r in env_recipients.split(",") if r.strip()]

    for report in reports:
        if args.dry_run:
            print(f"\n=== {report['subject']} ===\n{report['html']}\n")
        elif not recipients:
            print(f"[aviso] sem destinatário definido, pulando envio de: {report['subject']}", file=sys.stderr)
        else:
            result = send_email(to=recipients, subject=report["subject"], html=report["html"])
            print(f"Enviado: {report['subject']} → {result}")


if __name__ == "__main__":
    main()
