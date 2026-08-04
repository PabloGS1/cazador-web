#!/usr/bin/env python3
"""
NOTIFY — resumen diario por email con las mejores ofertas.
Lee web/data/jobs.json (salida de matcher.py) y manda un digest vía SMTP.

Config vía variables de entorno (GitHub Secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM, MAIL_TO
  DASHBOARD_URL (opcional, enlace al dashboard en el pie)

Si no hay configuración de email, imprime el digest en stdout
(útil en local y evita que el CI falle sin secrets).
"""
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

BASE = Path(__file__).parent
JOBS = BASE / "web" / "data" / "jobs.json"
MIN_MATCH = int(os.environ.get("NOTIFY_MIN_MATCH", "60"))
LIMIT = int(os.environ.get("NOTIFY_LIMIT", "10"))
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://TU-SITIO.netlify.app")


def load_jobs():
    data = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    return [j for j in jobs if (j.get("match") or 0) >= MIN_MATCH]


def build_digest(jobs, limit=LIMIT):
    if not jobs:
        return "Sin ofertas por encima de " + str(MIN_MATCH) + " hoy.\n\nRevisa el dashboard: " + DASHBOARD_URL
    lines = [f"El Cazador · {len(jobs)} ofertas con match >= {MIN_MATCH}",
             f"Top {min(limit, len(jobs))}:", ""]
    for j in jobs[:limit]:
        sal = j.get("salary") or (f"EUR {j.get('salary_eur'):,}" if j.get("salary_eur") else "")
        lines += [
            f"[{j.get('match')}] {j.get('title')} @ {j.get('company')}",
            f"     {j.get('location') or '-'} | {sal} | {j.get('source')}",
            f"     {j.get('url')}",
            "",
        ]
    lines.append("Dashboard: " + DASHBOARD_URL)
    return "\n".join(lines)


def send(subject, body):
    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("MAIL_TO")
    if not host or not to:
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pwd = os.environ.get("SMTP_PASS", "")
    frm = os.environ.get("MAIL_FROM", user)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("El Cazador", frm))
    msg["To"] = to

    try:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        if port == 587:
            server.starttls()
            server.ehlo()
        if user:
            server.login(user, pwd)
        server.sendmail(frm, [t.strip() for t in to.split(",")], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[notify] error de email: {e}")
        return False


def main():
    jobs = sorted(load_jobs(), key=lambda j: -j["match"])
    digest = build_digest(jobs)
    top = f" · mejor {jobs[0]['match']}" if jobs else ""
    subject = f"[El Cazador] {len(jobs)} ofertas de hoy{top}"
    sent = send(subject, digest)
    print(digest)
    print(f"[notify] email: {'enviado' if sent else 'no configurado (Solo stdout)'}")


if __name__ == "__main__":
    main()
