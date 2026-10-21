"""
main.py — FastAPI application for Job Hunter Spain.
Exposes REST endpoints for the Next.js dashboard.

Run: uvicorn main:app --reload --port 8020
"""
import csv
import io
import re
import sqlite3
from contextlib import asynccontextmanager
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse, StreamingResponse
# pyrefly: ignore [missing-import]
from starlette.middleware.trustedhost import TrustedHostMiddleware
import logging

from config import (
    ALLOWED_HOSTS, API_CLIENT_HEADER, API_CLIENT_VALUE, API_PORT, CORS_ORIGINS, DB_PATH, INBOX_DIR, INBOX_POLL_SECONDS,
    JOB_TIMEOUT_SECONDS, SCRAPER_COOLDOWN_SECONDS, ensure_data_dirs,
)
from inbox_watcher import InboxWatcher
from job_manager import JobManager
from rate_gate import GateRejected, RunGate
from search_config import get_config
from schemas import (
    ApplicationOut, CompanyOut, ContactOut, CoverLetterIn, DashboardStatsOut, HistoryEntryOut, JobDetailOut,
    InboxReportOut, InboxStatusOut, JobOut, JobStartedOut, OfferOut, OutcomeIn, PendingApplicationOut,
    QuietApplicationOut, ResolveStaleIn, StatsOut, TrackOut,
)
from scraper.jobs import SOURCES as SCRAPER_SOURCES
from automation import followup
from automation.filter_engine import classify_track
from automation.location import parse_modality
from automation.experience_classifier import classify_experience, classify_contract
import repository
from database import (
    get_conn, get_db, init_db, get_all_companies, stats as db_stats,
    get_pending_applications, get_history, get_dashboard_stats,
    discard_offer_for_application, discard_offer,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# Recoge solo lo que Cowork y n8n dejan en backend/inbox/ (ver inbox_watcher.py).
inbox_watcher = InboxWatcher(INBOX_DIR, DB_PATH, interval=INBOX_POLL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()
    get_config()  # una configuración rota debe fallar al arrancar, no a mitad de un scraping
    conn = get_conn()
    try:
        init_db(conn)
    finally:
        conn.close()
    inbox_watcher.start()
    try:
        yield
    finally:
        inbox_watcher.stop()


app = FastAPI(title="Job Hunter Spain API", version="1.0.0", lifespan=lifespan)

# Defensa en capas de una API local sin login (ADR-001). El último middleware añadido es el
# más externo: CORS va el último para que también los 400/403 lleven sus cabeceras y el
# dashboard pueda leer el error.
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def require_client_header(request, call_next):
    """POST/PUT/PATCH/DELETE exigen una cabecera propia. Al no ser una cabecera «simple», el
    navegador hace preflight y CORS lo rechaza para webs ajenas (evita el CSRF)."""
    if request.method in _MUTATING_METHODS and request.headers.get(API_CLIENT_HEADER) != API_CLIENT_VALUE:
        return JSONResponse({"detail": f"Falta la cabecera {API_CLIENT_HEADER}"}, status_code=403)
    return await call_next(request)


# Solo atiende peticiones cuyo Host sea el propio equipo (evita el DNS rebinding).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/stats", response_model=StatsOut)
def get_stats(conn: sqlite3.Connection = Depends(get_db)):
    result = db_stats(conn)
    return result


@app.get("/api/companies", response_model=list[CompanyOut])
def get_companies(sector: str | None = None, country: str | None = None, conn: sqlite3.Connection = Depends(get_db)):
    rows = get_all_companies(conn)
    data = [dict(r) for r in rows if r["source"] != "generic"]
    if sector:
        data = [c for c in data if c.get("sector") == sector]
    if country:
        data = [c for c in data if c.get("country") == country]
    return data


@app.get("/api/tracks", response_model=list[TrackOut])
def get_tracks():
    """Los tracks de la configuración, en su orden: una pestaña del dashboard por cada uno."""
    return [{"id": t.id, "label": t.label, "kind": t.kind} for t in get_config().tracks]


@app.get("/api/offers", response_model=list[OfferOut])
def get_offers(
    relevant_only: bool = False,
    source: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    posted_after: str | None = None,
    min_score: float | None = None,
    experience_level: str | None = None,
    contract_type: str | None = None,
    stack: str | None = None,
    track: str | None = None,
    modality: str | None = None,
    location: str | None = None,
    include_discarded: bool = False,
    sort_by: str = "relevance_score",
    sort_dir: str = "desc",
    limit: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    # Un track aislado se lee por job_kind (en SQL); uno estándar, por clasificación (en Python).
    cfg_track = None
    if track and track != "all":
        cfg_track = get_config().track(track)
        if cfg_track is None:
            raise HTTPException(404, f"Track desconocido: {track}")
    isolated = cfg_track is not None and cfg_track.kind == "isolated"
    standard_id = cfg_track.id if cfg_track is not None and not isolated else None
    if isolated:
        sort_by, sort_dir = "generic_score", "desc"
    # modality / track estándar / location se calculan en Python: con alguno activo, el LIMIT
    # debe aplicarse DESPUÉS de filtrar (en SQL recortaría antes de filtrar).
    computed_filters = bool(
        standard_id or (modality and modality != "all") or location
    )
    rows = repository.list_offers(
        conn,
        relevant_only=relevant_only, source=source, salary_min=salary_min, salary_max=salary_max,
        posted_after=posted_after, min_score=min_score, experience_level=experience_level,
        contract_type=contract_type, stack=stack,
        job_kind=cfg_track.id if isolated else None, tier_first=standard_id is not None,
        include_discarded=include_discarded, sort_by=sort_by, sort_dir=sort_dir,
        limit=None if computed_filters else limit,
    )
    result = []
    for r in rows:
        offer = dict(r)
        cv_profile, _ = classify_track(offer)
        offer["cv_profile"] = cv_profile
        offer["modality"] = parse_modality(offer.get("location"), offer.get("title")) or "presencial"
        # Enrich experience/contract if not already set
        if not offer.get("experience_level"):
            offer["experience_level"] = classify_experience(
                offer.get("title", ""), offer.get("description")
            )
        if not offer.get("contract_type"):
            offer["contract_type"] = classify_contract(
                offer.get("title", ""), offer.get("description")
            )
        # Apply client-side filters for dynamically computed fields
        if standard_id and offer["cv_profile"] != standard_id:
            continue
        if modality and modality != "all" and offer["modality"] != modality:
            continue
        if location and location.lower() not in (offer.get("location") or "").lower():
            continue
        result.append(offer)
    if limit is not None and computed_filters:
        result = result[:int(limit)]
    return result


@app.post("/api/offers/{offer_id}/mark-sent")
def mark_offer_sent(offer_id: str, conn: sqlite3.Connection = Depends(get_db)):
    existing_id = repository.find_application_id_for_offer(conn, offer_id)
    if existing_id:
        return {"id": existing_id, "already_sent": True}
    offer = repository.get_offer(conn, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    # job_offers.cv_profile es una columna heredada que ya no se escribe: el perfil se calcula.
    app_id = repository.create_manual_application(
        conn, offer, offer["cv_profile"] or classify_track(dict(offer))[0]
    )
    return {"id": app_id, "created": True}


@app.delete("/api/offers/{offer_id}/mark-sent")
def unmark_offer_sent(offer_id: str, conn: sqlite3.Connection = Depends(get_db)):
    repository.delete_manual_application(conn, offer_id)
    return {"removed": True}


@app.post("/api/offers/{offer_id}/discard")
def discard_offer_endpoint(offer_id: str, reason: str = "expired", conn: sqlite3.Connection = Depends(get_db)):
    if not repository.offer_exists(conn, offer_id):
        raise HTTPException(404, "Offer not found")
    discard_offer(conn, offer_id, reason)
    return {"id": offer_id, "discard_status": reason}


@app.delete("/api/offers/{offer_id}/discard")
def restore_offer_endpoint(offer_id: str, conn: sqlite3.Connection = Depends(get_db)):
    repository.restore_offer(conn, offer_id)
    return {"id": offer_id, "discard_status": None}


@app.get("/api/applications", response_model=list[ApplicationOut])
def get_applications(status: str | None = None, conn: sqlite3.Connection = Depends(get_db)):
    rows = repository.list_applications(conn, status)
    return [dict(r) for r in rows]


@app.get("/api/contacts", response_model=list[ContactOut])
def get_contacts(conn: sqlite3.Connection = Depends(get_db)):
    contacts = repository.list_contacts(conn)
    offers_rows = repository.list_relevant_offers_for_contacts(conn)
    offers_by_company: dict = {}
    for o in offers_rows:
        cid = o["company_id"]
        if cid not in offers_by_company:
            offers_by_company[cid] = []
        offers_by_company[cid].append({
            "id": o["id"], "title": o["title"],
            "url": o["url"], "relevance_score": o["relevance_score"],
            "location": o["location"],
        })
    result = []
    for ct in contacts:
        d = dict(ct)
        d["offers"] = offers_by_company.get(ct["company_id"], [])
        result.append(d)
    return result


@app.patch("/api/applications/{app_id}/status")
def update_application_status(app_id: str, status: str, conn: sqlite3.Connection = Depends(get_db)):
    valid = {"sent", "replied", "interview", "offer", "rejected", "withdrawn", "expired", "no_response"}
    if status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid}")
    repository.set_application_status(conn, app_id, status)
    if status in ("rejected", "expired"):
        discard_offer_for_application(conn, app_id, status)
    return {"id": app_id, "status": status}


def _run_applications():
    from automation.application_engine import create_drafts
    create_drafts()


# El simulacro y la carga del inbox son locales y baratos: sin espera entre ejecuciones (sí sin solaparse).
_scraper_gate = RunGate(SCRAPER_COOLDOWN_SECONDS, overrides={"inbox": 0, "inbox-apply": 0})
# Los scrapers corren en un proceso aparte (python -m scraper.jobs <fuente>), no dentro de la API.
_jobs = JobManager(_scraper_gate, timeout=JOB_TIMEOUT_SECONDS)


@app.post("/api/scraper/run", response_model=JobStartedOut)
def trigger_scraper(source: str = "seed"):
    if source not in SCRAPER_SOURCES:
        raise HTTPException(400, f"Unknown source: {source}")
    try:
        job = _jobs.start(source)
    except GateRejected as e:
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        raise HTTPException(e.status, e.detail, headers=headers)
    return {"status": "started", "source": source, "job_id": job.id}


@app.get("/api/jobs", response_model=list[JobOut])
def list_jobs():
    """Últimos trabajos lanzados desde la API (el más reciente primero)."""
    return [j.as_dict() for j in _jobs.list()]


@app.get("/api/jobs/{job_id}", response_model=JobDetailOut)
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {**job.as_dict(), "log_tail": _jobs.tail(job)}


@app.post("/api/applications/run")
def trigger_applications(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_applications)
    return {"status": "started", "note": "Generating drafts (pending_approval). Approve from dashboard to send."}


# ── Review Queue endpoints ─────────────────────────────────────────────────────

@app.post("/api/applications/create-drafts")
def create_drafts_endpoint(limit: int | None = None):
    from automation.application_engine import create_drafts
    result = create_drafts(limit=limit)
    return result


@app.get("/api/applications/pending", response_model=list[PendingApplicationOut])
def get_pending_applications_endpoint(conn: sqlite3.Connection = Depends(get_db)):
    from automation.cv_selector import default_track_id, load_profile, select_cv

    profile = load_profile()
    out = []
    for r in get_pending_applications(conn):
        d = dict(r)
        cv = select_cv(d.get("cv_profile") or default_track_id(), profile, d.get("track_tag"), d.get("job_title"))
        d["cv_file"] = cv.name if cv else None
        out.append(d)
    return out


@app.post("/api/applications/{app_id}/approve")
def approve_application(app_id: str):
    from automation.application_engine import send_approved
    try:
        success = send_approved(app_id)
        return {"id": app_id, "success": success, "status": "sent" if success else "failed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/applications/{app_id}/mark-sent-manual")
def mark_application_sent_manual(app_id: str):
    from automation.application_engine import mark_sent_manual
    try:
        success = mark_sent_manual(app_id)
        return {"id": app_id, "success": success, "status": "sent"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/applications/{app_id}/cover-letter")
def update_cover_letter(app_id: str, body: CoverLetterIn, conn: sqlite3.Connection = Depends(get_db)):
    text = body.cover_letter_edited
    repository.set_cover_letter(conn, app_id, text)
    return {"id": app_id, "updated": True}


@app.post("/api/applications/{app_id}/reject")
def reject_application(app_id: str, conn: sqlite3.Connection = Depends(get_db)):
    repository.set_application_status(conn, app_id, "rejected_manual")
    discard_offer_for_application(conn, app_id, "rejected")
    return {"id": app_id, "status": "rejected_manual"}


# ── Seguimiento de candidaturas silenciosas (automation/followup.py) ───────────
# Solo propone: los borradores nunca se envían desde aquí.

@app.get("/api/followups", response_model=list[QuietApplicationOut])
def list_followups_endpoint(days: int = followup.FOLLOWUP_MIN_DAYS, conn: sqlite3.Connection = Depends(get_db)):
    return followup.list_followups(conn, days)


@app.post("/api/applications/{app_id}/followup")
def mark_followup_sent_endpoint(app_id: str, conn: sqlite3.Connection = Depends(get_db)):
    if not followup.mark_followup_sent(conn, app_id):
        raise HTTPException(400, f"No se puede registrar: la candidatura no está en 'sent' o ya lleva "
                                 f"{followup.FOLLOWUP_MAX} recordatorios")
    return {"id": app_id, "followup": True}


@app.get("/api/followups/stale", response_model=list[QuietApplicationOut])
def list_stale_endpoint(days: int = followup.STALE_DAYS, conn: sqlite3.Connection = Depends(get_db)):
    return followup.list_stale(conn, days)


@app.post("/api/followups/stale/resolve")
def resolve_stale_endpoint(body: ResolveStaleIn, conn: sqlite3.Connection = Depends(get_db)):
    return {"resolved": followup.resolve_stale(conn, body.ids)}


# ── Inbox de Cowork / n8n ──────────────────────────────────────────────────────

@app.get("/api/inbox/status", response_model=InboxStatusOut)
def get_inbox_status():
    return inbox_watcher.status()


@app.post("/api/inbox/sync", response_model=InboxReportOut | None)
def sync_inbox():
    """Carga ya lo que haya en el inbox, sin esperar al vigilante. None si no había nada."""
    return inbox_watcher.run_once(force=True)


# ── Dashboard stats ────────────────────────────────────────────────────────────

@app.get("/api/stats/dashboard", response_model=DashboardStatsOut)
def get_dashboard_stats_endpoint(conn: sqlite3.Connection = Depends(get_db)):
    result = get_dashboard_stats(conn)
    return result


# ── Persistent history ─────────────────────────────────────────────────────────

@app.get("/api/history", response_model=list[HistoryEntryOut])
def get_history_endpoint(
    company: str | None = None,
    profile: str | None = None,
    outcome: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = get_history(conn, company=company, profile=profile, outcome=outcome)
    return [dict(r) for r in rows]


@app.patch("/api/history/{history_id}/outcome")
def update_history_outcome(history_id: str, body: OutcomeIn, conn: sqlite3.Connection = Depends(get_db)):
    valid = {"sin_respuesta", "respuesta_recibida", "entrevista", "rechazado"}
    outcome = body.outcome
    if outcome not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome. Must be one of: {sorted(valid)}",
        )
    repository.set_history_outcome(conn, history_id, outcome)
    return {"id": history_id, "outcome": outcome}


# CSV injection: Excel/LibreOffice ejecutan como fórmula una celda que empieza por = + - @ (o tab/CR).
# Los textos del historial salen de portales y correos externos, así que se les antepone una comilla
# simple. Los teléfonos y números sueltos (+34 600 123 456, -5) no pueden ser fórmulas y se dejan.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"^[+-][\d\s().-]+$")


def _csv_safe(value):
    if isinstance(value, str) and value.startswith(_FORMULA_START) and not _PLAIN_NUMBER.match(value):
        return "'" + value
    return value


@app.get("/api/history/export")
def export_history(format: str = "json", conn: sqlite3.Connection = Depends(get_db)):
    rows = [dict(r) for r in repository.list_history_for_export(conn)]

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows({k: _csv_safe(v) for k, v in row.items()} for row in rows)
        from datetime import date
        filename = f"job_hunter_history_{date.today().isoformat()}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return rows


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=API_PORT, reload=True)
