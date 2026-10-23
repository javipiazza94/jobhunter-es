"""
automation/followup.py — Seguimiento de candidaturas silenciosas.

Idea tomada de `/outcome followup` y `/outcome stale` de MadsLorentzen/ai-job-search:
  * candidatura 'sent' sin respuesta ≥ FOLLOWUP_MIN_DAYS (contando desde el último recordatorio)
    y con menos de FOLLOWUP_MAX recordatorios → se propone un borrador corto, según el canal;
  * NUNCA se envía nada: Javi copia el borrador, lo manda y lo marca como enviado
    (mark_followup_sent), que lleva la cuenta para el siguiente cálculo;
  * ≥ STALE_DAYS sin respuesta → se propone cerrarla como 'no_response' (resolve_stale), solo las
    que Javi elija.
El borrador no añade méritos: el recordatorio de valor es la primera frase del `summary` del perfil
del CV que se envió (sap / ia / general), que ya está en ese CV.
"""
import json
import re
import sqlite3
from datetime import date, datetime

from jinja2 import Environment, FileSystemLoader

from automation.filter_engine import classify_track
from config import FOLLOWUP_MAX, FOLLOWUP_MIN_DAYS, PROFILE_PATH, STALE_DAYS
from search_config import get_config

# method de la candidatura → canal del recordatorio
_LINKEDIN = {"linkedin_easy_apply", "linkedin_direct", "linkedin"}
_EMAIL = {"email"}
_PLACEHOLDER_TITLE = re.compile(r"^\s*\(.*\)\s*$")

_QUIET_SQL = """
    SELECT * FROM (
    SELECT a.id, a.status, a.method, a.sent_at, a.cv_profile, a.notes,
           COALESCE(a.followup_count, 0) AS followup_count, a.last_followup_at,
           c.name AS company_name, jo.title AS job_title, jo.url AS offer_url,
           ct.value AS contact_value, ct.type AS contact_type,
           -- solo la fecha (10 primeros caracteres): sent_at llega en varios formatos, alguno malformado
           CAST(julianday('now', 'localtime')
                - julianday(MAX(substr(a.sent_at, 1, 10), COALESCE(substr(a.last_followup_at, 1, 10), '')))
                AS INTEGER) AS days_quiet
    FROM applications a
    LEFT JOIN companies c ON c.id = a.company_id
    LEFT JOIN job_offers jo ON jo.id = a.job_offer_id
    LEFT JOIN contacts ct ON ct.id = a.contact_id
    WHERE a.status = 'sent' AND a.sent_at IS NOT NULL
    ) WHERE days_quiet >= ?
"""


def channel_for(method: str | None) -> str:
    if method in _LINKEDIN:
        return "linkedin"
    if method in _EMAIL:
        return "email"
    return "portal"


def _profile() -> dict:
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _reminder(profile: dict, cv_profile: str | None, job_title: str | None, lang: str = "es") -> str:
    cfg = get_config()
    if cfg.track(cv_profile or "") is None and job_title:
        cv_profile = classify_track({"title": job_title})[0]
    track = cfg.track(cv_profile or "")
    key = track.summary_key if track else None
    summary = (profile.get("summary") or {}).get(key, "") if key else ""
    first = re.split(r"(?<=\.)\s", summary.strip(), maxsplit=1)[0] if summary else ""
    if not first:
        return ""
    if lang == "en":
        return f"To briefly recap my background: {first}"
    return f"Les recuerdo brevemente mi perfil: {first}"


def _fmt_date(value: str | None, lang: str = "es") -> str:
    try:
        dt = datetime.fromisoformat((value or "")[:10])
        if lang == "en":
            return dt.strftime("%B %d, %Y")
        return dt.strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value or ""


def draft_followup(app: dict, profile: dict | None = None, lang: str | None = None) -> str:
    """Borrador del recordatorio (texto plano) para una fila de list_followups."""
    from automation.cover_letter import letter_language, template_search_dirs

    profile = profile if profile is not None else _profile()
    lang = lang or letter_language(app, profile)
    personal = profile.get("personal", {})
    title = app.get("job_title")
    if title and _PLACEHOLDER_TITLE.match(title):
        title = None  # "(ver Gmail)", "(por confirmar)": relleno del inbox, no un puesto
    search_dirs = template_search_dirs(lang)
    env = Environment(loader=FileSystemLoader([str(p) for p in search_dirs]), keep_trailing_newline=False)
    default_company = "the company" if lang == "en" else "la empresa"
    return env.get_template("followup.j2").render(
        channel=channel_for(app.get("method")),
        company_name=app.get("company_name") or default_company,
        job_title=title,
        sent_date=_fmt_date(app.get("sent_at"), lang=lang),
        reminder=_reminder(profile, app.get("cv_profile"), title, lang=lang),
        name=personal.get("name", ""),
        first_name=personal.get("first_name", ""),
        email=personal.get("email", ""),
        phone=personal.get("phone", ""),
    ).strip()


def list_followups(conn: sqlite3.Connection, days: int = FOLLOWUP_MIN_DAYS) -> list[dict]:
    """Candidaturas 'sent' que piden recordatorio, más silenciosas primero, con su borrador."""
    rows = conn.execute(
        _QUIET_SQL + " AND followup_count < ? ORDER BY days_quiet DESC", (days, FOLLOWUP_MAX),
    ).fetchall()
    profile = _profile()
    out = []
    for r in rows:
        app = dict(r)
        app["channel"] = channel_for(app["method"])
        app["draft"] = draft_followup(app, profile)
        out.append(app)
    return out


def list_stale(conn: sqlite3.Connection, days: int = STALE_DAYS) -> list[dict]:
    """Candidaturas 'sent' sin respuesta desde hace ≥ days (propuesta: cerrarlas como no_response)."""
    rows = conn.execute(
        _QUIET_SQL + " ORDER BY days_quiet DESC", (days,)
    ).fetchall()
    return [{**dict(r), "channel": channel_for(r["method"])} for r in rows]


def mark_followup_sent(conn: sqlite3.Connection, app_id: str, when: date | None = None) -> bool:
    """Registra que Javi ha enviado un recordatorio. False si no existe, no está 'sent' o ya lleva el máximo."""
    day = (when or date.today()).isoformat()
    cur = conn.execute(
        """UPDATE applications
           SET followup_count = COALESCE(followup_count, 0) + 1, last_followup_at = ?,
               notes = COALESCE(notes, '') || ?
           WHERE id = ? AND status = 'sent' AND COALESCE(followup_count, 0) < ?""",
        (day, f" | Seguimiento enviado {day}", app_id, FOLLOWUP_MAX),
    )
    conn.commit()
    return cur.rowcount == 1


def resolve_stale(conn: sqlite3.Connection, app_ids: list[str]) -> int:
    """Pasa a 'no_response' las candidaturas indicadas que sigan en 'sent'. Devuelve cuántas."""
    if not app_ids:
        return 0
    day = date.today().isoformat()
    placeholders = ",".join("?" * len(app_ids))
    cur = conn.execute(
        f"""UPDATE applications SET status = 'no_response',
                   notes = COALESCE(notes, '') || ?
            WHERE status = 'sent' AND id IN ({placeholders})""",
        (f" | Cerrada sin respuesta {day}", *app_ids),
    )
    conn.commit()
    return cur.rowcount
