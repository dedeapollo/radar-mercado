"""
report_results.py — Monta o tranche 📊 "Resultados & Estratégia" a partir dos
resultados extraídos por synthesize_results.py e envia por e-mail via Resend.

É um relatório à parte dos 3 tranches de notícia (diário/semanal/mensal): sai
só quando houve resultado novo na varredura semanal.

Como rodar:
    export RESEND_API_KEY="..."
    python src/report_results.py data/classified_results_AAAA-MM-DD.json --to seu@email.com

Flags:
    --dry-run   monta o conteúdo e imprime, sem enviar
    --to        e-mail de destino para teste (senão usa EMAIL_RECIPIENTS)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from email_delivery import send_email


def esc(value) -> str:
    """Escape mínimo de HTML para texto vindo do modelo."""
    s = "" if value is None else str(value)
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _list_html(values: list) -> str:
    values = [v for v in (values or []) if str(v).strip()]
    if not values:
        return '<span style="color:#888;">—</span>'
    lis = "".join(f"<li>{esc(v)}</li>" for v in values)
    return f'<ul style="margin:4px 0 0 18px;padding:0;">{lis}</ul>'


def _badge(label: str) -> str:
    colors = {
        "copiar": ("#EC0000", "#fff"),     # vermelho Santander — atenção máxima
        "observar": ("#FFE9E9", "#B30000"),
        "ignorar": ("#eee", "#666"),
    }
    bg, fg = colors.get(label, ("#eee", "#666"))
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'font-size:12px;font-weight:600;background:{bg};color:{fg};">{esc(label)}</span>'
    )


def result_card_html(item: dict) -> str:
    periodo = item.get("periodo", "")
    periodo_txt = f' · <span style="color:#666;">{esc(periodo)}</span>' if periodo and periodo != "não informado" else ""
    fontes = f'<a href="{esc(item.get("link", "#"))}" style="color:#EC0000;">{esc(item.get("source", "fonte"))}</a>'
    return f"""
    <div style="margin-bottom:20px;padding:16px;border:1px solid #eee;border-left:4px solid #EC0000;border-radius:6px;">
      <div style="font-size:16px;font-weight:700;color:#111;">
        {esc(item.get("competitor_group", ""))}{periodo_txt}
        &nbsp; {_badge(item.get("copiar_ou_observar", "observar"))}
      </div>
      <p style="margin:8px 0;color:#333;">{esc(item.get("resumo_estrategico", ""))}</p>
      <div style="font-size:13px;color:#111;margin-top:10px;"><strong>Onde colocam energia</strong></div>
      {_list_html(item.get("onde_colocam_energia"))}
      <div style="font-size:13px;color:#111;margin-top:10px;"><strong>Movimentos concretos</strong></div>
      {_list_html(item.get("movimentos_concretos"))}
      <div style="font-size:13px;color:#111;margin-top:10px;"><strong>Onde deixam a desejar</strong></div>
      {_list_html(item.get("onde_deixam_a_desejar"))}
      <div style="margin-top:12px;padding:10px;background:#FFF6F6;border-radius:4px;">
        <div style="font-size:13px;color:#111;"><strong>Oportunidade para nós</strong></div>
        <div style="color:#333;margin-top:2px;">{esc(item.get("oportunidade_para_nos", "nenhuma clara"))}</div>
        <div style="font-size:13px;color:#111;margin-top:8px;"><strong>Leitura para o Santander</strong></div>
        <div style="color:#333;margin-top:2px;">{esc(item.get("leitura_para_o_santander", ""))}</div>
      </div>
      <div style="margin-top:10px;font-size:12px;color:#777;">Fonte: {fontes} · {esc(item.get("published_at", "")[:10])}</div>
    </div>
    """


def build_results_report(items: list[dict], report_date: str) -> dict | None:
    if not items:
        return None
    body = "".join(result_card_html(i) for i in items)
    html = (
        f'<h2 style="color:#111;">📊 Resultados &amp; Estratégia</h2>'
        f'<p style="color:#666;margin-top:-6px;">Leitura estratégica dos resultados divulgados — recorte corretora de varejo.</p>'
        f'{body}'
    )
    return {"subject": f"📊 Radar de Mercado — Resultados & Estratégia ({report_date})", "html": html}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("classified_file")
    parser.add_argument("--date", help="Simula uma data (AAAA-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Monta o conteúdo mas não envia")
    parser.add_argument("--to", help="E-mail de destino para teste")
    args = parser.parse_args()

    path = Path(args.classified_file)
    if not path.exists():
        print(f"[aviso] arquivo não encontrado: {path} — nada a enviar.")
        return

    items = json.loads(path.read_text(encoding="utf-8"))
    ref_date = (
        datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.date else datetime.now(timezone.utc)
    )
    report = build_results_report(items, ref_date.strftime("%Y-%m-%d"))

    if not report:
        print("Sem resultados novos hoje — nenhum e-mail de resultados a enviar.")
        return

    if args.to:
        recipients = [args.to]
    else:
        recipients = [r.strip() for r in os.environ.get("EMAIL_RECIPIENTS", "").split(",") if r.strip()]

    if args.dry_run:
        print(f"\n=== {report['subject']} ===\n{report['html']}\n")
    elif not recipients:
        print(f"[aviso] sem destinatário definido, pulando envio de: {report['subject']}", file=sys.stderr)
    else:
        result = send_email(to=recipients, subject=report["subject"], html=report["html"])
        print(f"Enviado: {report['subject']} → {result}")


if __name__ == "__main__":
    main()
