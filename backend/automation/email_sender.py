"""
automation/email_sender.py — Envía los emails de candidatura por SMTP.

Los ajustes se leen en cada llamada: sección `email:` de jobhunter.yaml (preset Gmail por defecto:
smtp.gmail.com:587 STARTTLS), usuario `email.username` o, si falta, la variable GMAIL_USER, y contraseña
del llavero (`smtp_password`) o GMAIL_APP_PASSWORD. Sin sección `email:` el comportamiento es el histórico.
La contraseña nunca se registra ni se devuelve.
"""
import smtplib
import logging
import os
import uuid
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import search_config
from secrets_store import get_secret

logger = logging.getLogger(__name__)


def smtp_settings() -> tuple[str, int, bool, str, str, str]:
    """(host, port, starttls, usuario, contraseña, cabecera From) resueltos en este momento.

    Usuario y contraseña pueden venir vacíos si no están configurados."""
    cfg = search_config.get_config().email
    username = cfg.username or os.environ.get("GMAIL_USER", "")
    password = get_secret("smtp_password") or ""
    from_header = formataddr((cfg.from_name, username)) if cfg.from_name else username
    return cfg.smtp_host, cfg.smtp_port, cfg.use_starttls, username, password, from_header


SMTP_TIMEOUT = 30


def _connect(host: str, port: int) -> smtplib.SMTP:
    """Puerto 465 = TLS implícito (SMTP_SSL); el resto, conexión normal (STARTTLS según ajustes)."""
    if port == 465:
        return smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT)
    return smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)


def _build_message(to: str, subject: str, body: str, attachments: list[Path], from_header: str) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = from_header
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{uuid.uuid4()}@jobhunter>"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachments:
        if not path or not path.exists():
            continue
        with path.open("rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={path.name}")
        msg.attach(part)
    return msg


def send_email(
    to: str,
    subject: str,
    body: str,
    cv_path: Path | None = None,
    cover_letter_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    """Send email with CV and (optionally) a cover letter file attached. Returns (success, message_id)."""
    host, port, starttls, username, password, from_header = smtp_settings()
    if not username or not password:
        logger.error("SMTP sin configurar: falta usuario (email.username / GMAIL_USER) o contraseña.")
        return False, None

    if dry_run:
        dry_id = f"<dry-run-{uuid.uuid4()}@jobhunter>"
        logger.info("[DRY-RUN] Would send email to %s: %s", to, subject)
        return True, dry_id

    try:
        msg = _build_message(to, subject, body, [cv_path, cover_letter_path], from_header)
        message_id = msg["Message-ID"]
        with _connect(host, port) as server:
            server.ehlo()
            if starttls and port != 465:
                server.starttls()
            server.login(username, password)
            server.sendmail(username, to, msg.as_string())
        logger.info("Email sent to %s (id=%s)", to, message_id)
        return True, message_id
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, type(e).__name__)
        return False, None


def check_smtp_connection() -> tuple[bool, str]:
    """Conecta y autentica con los ajustes actuales, sin enviar nada. Devuelve (ok, mensaje sin secretos)."""
    host, port, starttls, username, password, _ = smtp_settings()
    if not username or not password:
        return False, "Falta el usuario o la contraseña SMTP."
    try:
        with _connect(host, port) as server:
            server.ehlo()
            if starttls and port != 465:
                server.starttls()
            server.login(username, password)
    except smtplib.SMTPAuthenticationError:
        return False, "El servidor rechazó el usuario o la contraseña."
    except Exception as e:  # noqa: BLE001 — se informa solo el tipo, nunca el detalle (puede citar credenciales)
        return False, f"No se pudo conectar con {host}:{port} ({type(e).__name__})."
    return True, f"Conexión correcta con {host}:{port}."
