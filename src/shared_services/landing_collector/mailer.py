"""Envoi d'email transactionnel (Chap 18 — double opt-in des leads).

Copie autonome de app/core/mailer.py (Chap 9, invitations Waitlist) : ce
service n'importe jamais de code d'un autre service (voir schemas.py, où
LeadOut est déjà dupliqué plutôt que partagé) — même contrat fail-closed,
même mécanique SMTP générique (fonctionne avec un compte Gmail dès
aujourd'hui, swappable vers un vrai fournisseur plus tard).
"""

import os
import smtplib
from email.message import EmailMessage


def send_email(to: str, subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "")
    if not host:
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "SMTP_HOST manquant alors que ENVIRONMENT=production — "
                "refus d'échouer silencieusement (fail-closed)"
            )
        print(f"[DEV email stub] to={to} subject={subject}\n{body}")
        return
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", host)
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        user = os.environ.get("SMTP_USER", "")
        if user:
            server.login(user, os.environ.get("SMTP_PASSWORD", ""))
        server.send_message(msg)
