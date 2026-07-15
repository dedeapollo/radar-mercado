"""
email_delivery.py — Envio de e-mail via Resend API.

ATENÇÃO — restrição importante do plano gratuito:
Sem um domínio verificado no Resend, só é possível enviar para o e-mail
associado à sua própria conta Resend (usando o remetente onboarding@resend.dev).
Pra mandar pra lideranças (endereços diferentes), é preciso verificar um
domínio próprio em resend.com/domains — o que normalmente exige acesso aos
registros DNS do domínio da empresa. Pode precisar de TI para essa parte
específica, mesmo no resto o projeto sendo só seu.
"""

import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "onboarding@resend.dev"  # trocar após verificar domínio próprio


def send_email(to: list[str], subject: str, html: str, from_address: str = DEFAULT_FROM) -> dict:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("Defina a variável de ambiente RESEND_API_KEY")

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": from_address, "to": to, "subject": subject, "html": html},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
