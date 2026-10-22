"""
config.py — Centralised settings for Job Hunter Spain.
All tunable parameters live here; never hardcode in other modules.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent        # backend/ (código)
# Congelado con PyInstaller (app de escritorio) código y datos de serie conviven en una sola carpeta
# (ver backend/desktop_freeze.spec): ahí no hay un «repo» por encima.
REPO_ROOT = BASE_DIR if getattr(sys, "frozen", False) else BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")          # backend/.env
load_dotenv(REPO_ROOT / ".env")         # project root .env (fallback)

# ── Datos del usuario: todo vive en JH_HOME (por defecto <repo>/data); el código sigue en backend/ ──
JH_HOME = Path(os.getenv("JH_HOME") or REPO_ROOT / "data")
# JH_DB_PATH / JH_INBOX_DIR / JH_PROFILE_PATH siguen mandando sobre JH_HOME (copia de la BD, inbox temporal...).
DB_PATH = Path(os.getenv("JH_DB_PATH") or JH_HOME / "job_hunter.db")
INBOX_DIR = Path(os.getenv("JH_INBOX_DIR") or JH_HOME / "inbox")
# Los tests usan profile.example.json si no hay profile.json (ver tests/conftest.py).
PROFILE_PATH = Path(os.getenv("JH_PROFILE_PATH") or JH_HOME / "profile.json")
CV_DIR = JH_HOME / "cv"
APPLICATIONS_DIR = JH_HOME / "applications"
COMPANY_RESEARCH_DIR = JH_HOME / "company_research"
LOGS_DIR = JH_HOME / "logs"
BACKUPS_DIR = JH_HOME / "backups"
SESSIONS_DIR = JH_HOME / "sessions"
TEMPLATES_OVERRIDE_DIR = JH_HOME / "templates"  # plantillas propias del usuario (mandan sobre backend/templates)
SEEDS_PATH = REPO_ROOT / "seeds" / "companies_public_salary.json"
TEMPLATES_DIR = BASE_DIR / "templates"
DEFAULT_LATEX_TEMPLATES_DIR = REPO_ROOT / "templates" / "latex"
LATEX_TEMPLATES_OVERRIDE_DIR = JH_HOME / "templates" / "latex"


def ensure_data_dirs() -> None:
    """Crea JH_HOME y sus subcarpetas de datos (idempotente)."""
    for d in (JH_HOME, INBOX_DIR, BACKUPS_DIR, LOGS_DIR, CV_DIR, SESSIONS_DIR, APPLICATIONS_DIR, COMPANY_RESEARCH_DIR):
        d.mkdir(parents=True, exist_ok=True)


def resolve_data_path(rel: "str | Path") -> Path:
    """Ruta relativa (p. ej. 'cv/CV_SAP.pdf' de profile.json) → bajo JH_HOME; absoluta → tal cual."""
    p = Path(rel)
    return p if p.is_absolute() else JH_HOME / p


# ── Scraping ──────────────────────────────────────────────────────────────────
DELAY_MIN = 3.0
DELAY_MAX = 8.0
MAX_RETRIES = 3

TECNOEMPLEO_BASE = "https://www.tecnoempleo.com"

LINKEDIN_BASE = "https://www.linkedin.com/jobs/search"

# ── Indeed ────────────────────────────────────────────────────────────────────
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "")

INDEED_BASE = "https://es.indeed.com"

# ── Manfred ───────────────────────────────────────────────────────────────────
MANFRED_API_BASE = "https://www.getmanfred.com/api/v2/public/offers"
MANFRED_MAX_PAGES = 5

# ── Filter Engine ─────────────────────────────────────────────────────────────
# Pesos, keywords, ciudad, salario y umbrales de scoring: `jobhunter.yaml` (`scoring:`), ver search_config.py.

RECONTACT_COOLDOWN_DAYS = 180

# ── Application Engine ────────────────────────────────────────────────────────
MAX_EMAILS_PER_DAY = 30
EMAIL_DELAY_MIN = 30    # seconds between sends
EMAIL_DELAY_MAX = 120

# ── Seguimiento de candidaturas (automation/followup.py) ──────────────────────
FOLLOWUP_MIN_DAYS = 10   # días sin respuesta para proponer un recordatorio
FOLLOWUP_MAX = 2         # recordatorios como máximo por candidatura
STALE_DAYS = 60          # días sin respuesta para proponer cerrarla como 'no_response'

# ── API ───────────────────────────────────────────────────────────────────────
API_PORT = int(os.getenv("API_PORT", "8020"))
def _with_loopback_twins(origins: list[str]) -> list[str]:
    """Añade el gemelo de cada origen de loopback: abrir el dashboard por «localhost» o por
    «127.0.0.1» es lo mismo para el usuario, pero para el navegador son orígenes distintos y,
    sin el gemelo, la página carga vacía (la API rechaza sus peticiones)."""
    result: list[str] = []
    for origin in (o.strip() for o in origins if o.strip()):
        for variant in (origin, origin.replace("//localhost", "//127.0.0.1"), origin.replace("//127.0.0.1", "//localhost")):
            if variant not in result:
                result.append(variant)
    return result


CORS_ORIGINS = _with_loopback_twins(
    os.getenv("CORS_ORIGINS", "http://localhost:3010,http://localhost:3000").split(",")
)

# Seguridad de la API local, sin login (docs/adr/0001-proteccion-de-la-api-local.md):
# solo se atienden peticiones cuyo Host sea el propio equipo, y POST/PUT/PATCH/DELETE
# deben llevar esta cabecera propia (obliga al navegador a hacer preflight).
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
API_CLIENT_HEADER = "X-JH-Client"
API_CLIENT_VALUE = "dashboard"
# Espera mínima (segundos) entre dos ejecuciones de la misma fuente desde POST /api/scraper/run.
# 0 la desactiva (sigue sin permitirse lanzar la misma fuente dos veces a la vez).
SCRAPER_COOLDOWN_SECONDS = int(os.getenv("SCRAPER_COOLDOWN_SECONDS", "300"))
# Tiempo máximo (segundos) de un trabajo lanzado desde la API; pasado ese tiempo se mata el proceso.
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "1800"))

LINKEDIN_SESSION_PATH = SESSIONS_DIR / "linkedin_session.json"

# Vigilante del inbox (Cowork/n8n dejan ficheros en backend/inbox/): cada cuántos segundos se revisa. 0 = desactivado.
INBOX_POLL_SECONDS = int(os.getenv("JH_INBOX_POLL_SECONDS", "60"))
