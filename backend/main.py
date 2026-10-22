"""
main.py — FastAPI application for Job Hunter Spain.
Exposes REST endpoints for the Next.js dashboard.

Run: uvicorn main:app --reload --port 8020
"""
import csv
import io
import os
import re
import sqlite3
import unicodedata
import uuid
from contextlib import asynccontextmanager
# pyrefly: ignore [missing-import]
from fastapi import Body, FastAPI, HTTPException, BackgroundTasks, Depends, Request
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
# pyrefly: ignore [missing-import]
from starlette.middleware.trustedhost import TrustedHostMiddleware
# pyrefly: ignore [missing-import]
from starlette.concurrency import run_in_threadpool
# pyrefly: ignore [missing-import]
from starlette.datastructures import UploadFile
import logging
from pathlib import Path

import ai
import config
import profile_store
import secrets_store
import setup_builder

from config import (
    ALLOWED_HOSTS, API_CLIENT_HEADER, API_CLIENT_VALUE, API_PORT, CORS_ORIGINS, DB_PATH, INBOX_DIR, INBOX_POLL_SECONDS,
    JOB_TIMEOUT_SECONDS, SCRAPER_COOLDOWN_SECONDS, ensure_data_dirs,
)
from inbox_watcher import InboxWatcher
from job_manager import JobManager
from rate_gate import GateRejected, RunGate
from pydantic import ValidationError
from search_config import AISettings, ConfigError, EmailSettings, get_config, save_config, user_config_path
from schemas import (
    ApplicationOut, CompanyOut, ContactOut, CoverLetterIn, DashboardStatsOut, HistoryEntryOut, JobDetailOut,
    InboxReportOut, InboxStatusOut, JobOut, JobStartedOut, OfferOut, OutcomeIn, PendingApplicationOut,
    QuietApplicationOut, ResolveStaleIn, StatsOut, TrackOut,
    AISettingsIn, AISettingsOut, CheckOut, EmailSettingsIn, EmailSettingsOut, MarketSourceOut, SetupApplyOut,
    DocumentFileOut, InterviewPackOut, PrepareIn, ProfileIn, SetupProposalOut, SetupStatusOut, SetupTextIn,
    AIKeyIn, AIKeyOut, SourceSettingOut, SourcesIn, EvaluateBatchIn,
)
from scraper.jobs import SOURCES as SCRAPER_SOURCES, TRACK_JOB_PREFIX, TRACK_PIPELINE_SOURCES
from automation import application_documents, cv_reader, email_sender, followup, offer_evaluation, profile_proposal
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
    evaluations = offer_evaluation.summaries(conn)
    result = []
    for r in rows:
        offer = dict(r)
        offer["evaluation"] = evaluations.get(offer["id"])
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


# ── Evaluación detallada con IA (/rank en la app, automation/offer_evaluation.py) ──
# Nunca cambia relevance_score: se guarda aparte, en offer_evaluations.

_NO_AI = "IA no disponible: {}. Configura un proveedor en Perfil."


@app.post("/api/offers/evaluate-batch", response_model=offer_evaluation.BatchResult)
def evaluate_offers_batch(body: EvaluateBatchIn):
    """Evalúa varias ofertas una tras otra; lo que no quepa en el presupuesto de IA vuelve como `skipped`."""
    try:
        return offer_evaluation.evaluate_batch(body.ids)
    except ai.AIUnavailable as exc:
        raise HTTPException(409, _NO_AI.format(exc)) from None


@app.post("/api/offers/{offer_id}/evaluate", response_model=offer_evaluation.Evaluation)
def evaluate_offer_endpoint(offer_id: str):
    try:
        return offer_evaluation.evaluate_offer(offer_id)
    except offer_evaluation.OfferNotFound:
        raise HTTPException(404, "Oferta no encontrada") from None
    except ai.AIUnavailable as exc:
        raise HTTPException(409, _NO_AI.format(exc)) from None
    except ai.AIError as exc:
        raise HTTPException(502, f"La IA no pudo evaluar la oferta ({type(exc).__name__})") from None


@app.get("/api/offers/{offer_id}/evaluation", response_model=offer_evaluation.Evaluation | None)
def get_offer_evaluation(offer_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """Última evaluación con IA de la oferta, o null si aún no se ha evaluado."""
    if not repository.offer_exists(conn, offer_id):
        raise HTTPException(404, "Oferta no encontrada")
    return offer_evaluation.get_evaluation(conn, offer_id)


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
def trigger_scraper(source: str = "seed", track: str | None = None, tracks: str | None = None):
    """Lanza una fuente (`source`), el pipeline multi-portal de un track estándar (`track`, que respeta las
    fuentes activadas en jobhunter.yaml) o el de varios tracks uno detrás de otro en un solo trabajo (`tracks`,
    ids separados por comas). Un trabajo de tracks reserva además los portales que recorre: ni otro track ni esa
    fuente suelta corren a la vez (409), así nunca hay dos navegadores/sesiones del mismo portal."""
    also: tuple[str, ...] = ()
    if track is not None or tracks is not None:
        cfg = get_config()
        ids = list(dict.fromkeys(i.strip() for i in (tracks if tracks is not None else track).split(",") if i.strip()))
        if not ids:
            raise HTTPException(400, "Indica al menos un track")
        for track_id in ids:
            cfg_track = cfg.track(track_id)
            if cfg_track is None or cfg_track.kind != "standard":
                raise HTTPException(404, f"Track desconocido: {track_id}")
        source = f"{TRACK_JOB_PREFIX}{','.join(ids)}"
        also = tuple(s for s in TRACK_PIPELINE_SOURCES if s in cfg.sources)
    elif source not in SCRAPER_SOURCES:
        raise HTTPException(400, f"Unknown source: {source}")
    try:
        job = _jobs.start(source, also)
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


@app.post("/api/applications/{app_id}/interview-pack", response_model=InterviewPackOut)
def interview_pack(app_id: str):
    """Genera con IA el pack de entrevista (Markdown en la carpeta de la candidatura)."""
    from automation import ai_writing

    try:
        path = ai_writing.generate_interview_pack(app_id)
        return {"path": str(path), "markdown": path.read_text(encoding="utf-8")}
    except LookupError:
        raise HTTPException(404, "Candidatura no encontrada") from None
    except ai.AIUnavailable as exc:
        raise HTTPException(409, f"IA no disponible: {exc}. Configura un proveedor en Perfil.") from None
    except OSError:
        raise HTTPException(500, "No se pudo guardar el pack de entrevista en disco; revisa permisos y espacio libre") from None
    except ai.AIError as exc:
        raise HTTPException(502, f"La IA no pudo generar el pack ({type(exc).__name__})") from None


# ── Preparar candidatura: CV y carta en PDF archivados (automation/application_documents.py) ──

_DOCUMENT_MEDIA_TYPES = {".pdf": "application/pdf", ".md": "text/markdown; charset=utf-8"}


def _require_application(conn: sqlite3.Connection, app_id: str) -> None:
    if conn.execute("SELECT 1 FROM applications WHERE id = ?", (app_id,)).fetchone() is None:
        raise HTTPException(404, "Candidatura no encontrada")


@app.post("/api/applications/{app_id}/prepare", response_model=application_documents.PreparedDocs)
def prepare_application_endpoint(app_id: str, body: PrepareIn | None = None):
    """Genera y archiva el CV y la carta en PDF de la candidatura (puede tardar: compila LaTeX)."""
    use_ai = body.use_ai if body else None
    try:
        return application_documents.prepare_application(app_id, use_ai=use_ai)
    except application_documents.ApplicationNotFound:
        raise HTTPException(404, "Candidatura no encontrada") from None
    except application_documents.NoTexEngine as exc:
        raise HTTPException(409, str(exc)) from None
    except application_documents.VerificationFailed as exc:
        raise HTTPException(422, {"message": "Los PDFs no superan la verificación", "reasons": exc.reasons}) from None
    except OSError:
        raise HTTPException(500, "No se pudieron guardar los documentos en disco; revisa permisos y espacio libre") from None


@app.get("/api/applications/{app_id}/documents", response_model=list[DocumentFileOut])
def list_application_documents(app_id: str, conn: sqlite3.Connection = Depends(get_db)):
    _require_application(conn, app_id)
    return application_documents.list_documents(app_id)


@app.get("/api/applications/{app_id}/documents/{name}")
def get_application_document(app_id: str, name: str, inline: bool = False,
                             conn: sqlite3.Connection = Depends(get_db)):
    """Descarga un documento archivado; solo los de la lista blanca (cv.pdf, cover.pdf, job_posting.md,
    interview.md). `?inline=1` muestra los PDFs en el navegador en vez de descargarlos."""
    _require_application(conn, app_id)
    try:
        path = application_documents.document_path(app_id, name)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Documento no encontrado") from None
    disposition = "inline" if inline and path.suffix == ".pdf" else "attachment"
    return FileResponse(path, media_type=_DOCUMENT_MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
                        filename=path.name, content_disposition_type=disposition,
                        headers={"X-Content-Type-Options": "nosniff"})


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

# ── Asistente de primer arranque, perfil y ajustes de IA / email ──────────────────────────────
# Las rutas (JH_HOME, cv/, profile.json) se leen de `config` en cada llamada. Los secretos van al
# llavero y nunca vuelven en una respuesta: solo `has_*` y de dónde salen (`env` / `keychain`).

CV_EXTENSIONS = (".pdf", ".docx")
_UPLOAD_CHUNK = 1024 * 1024
_MULTIPART_OVERHEAD = 64 * 1024  # cabeceras multipart sobre el tamaño del propio archivo
_CV_TOO_BIG = "El archivo supera el tamaño máximo de 10 MB"
_API_KEY_SECRETS = {"anthropic": "anthropic_api_key", "openai": "openai_api_key"}
_SMTP_SECRET = "smtp_password"
_BASE_URL_PROVIDERS = ("ollama", "openai")
MAX_PROFILE_BYTES = 1024 * 1024


def _require_user_config() -> None:
    """Los ajustes se guardan sobre el jobhunter.yaml del usuario: sin él, primero el asistente."""
    if not user_config_path().is_file():
        raise HTTPException(409, "Completa primero el asistente")


def _secret_source(name: str) -> str | None:
    """'env' si manda la variable de entorno, 'keychain' si solo la tiene el llavero, None si no hay."""
    if os.environ.get(secrets_store.ENV_FALLBACK[name]):
        return "env"
    return "keychain" if secrets_store.has_secret(name) else None


def _keychain_unavailable(name: str) -> HTTPException:
    env = secrets_store.ENV_FALLBACK[name]
    return HTTPException(503, f"El llavero del sistema no está disponible: usa la variable de entorno {env}")


def _store_secret(name: str, value: str) -> None:
    try:
        secrets_store.set_secret(name, value)
    except secrets_store.SecretStoreUnavailable:
        raise _keychain_unavailable(name) from None


@app.exception_handler(secrets_store.SecretStoreUnavailable)
async def _secret_store_unavailable(request, exc):
    return JSONResponse(
        {"detail": "El llavero del sistema no está disponible: usa la variable de entorno correspondiente"},
        status_code=503,
    )


def _safe_cv_filename(filename: str | None) -> str:
    """Nombre seguro para guardar en cv/: sin rutas, ASCII `[A-Za-z0-9_-]` y extensión .pdf/.docx (si no, 400)."""
    name = re.split(r"[\\/]", filename or "")[-1]
    stem, dot, ext = name.rpartition(".")
    ext = "." + ext.lower() if dot else ""
    if ext not in CV_EXTENSIONS:
        raise HTTPException(400, "Tipo de archivo no soportado: sube el CV en PDF o DOCX")
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_stem).strip("_-")[:80] or "cv"
    return safe + ext


def _free_cv_name(cv_dir: Path, name: str) -> str:
    """`name` si está libre en cv/; si no, `<base>-2.<ext>`, `<base>-3.<ext>`… (nunca sobrescribe un CV)."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = name, 1
    while (cv_dir / candidate).exists():
        n += 1
        candidate = f"{stem}-{n}{suffix}"
    return candidate


def _check_base_url(settings: AISettings | None) -> None:
    """`base_url` solo vale para ollama/openai (422): con otro proveedor, su clave de API iría a una URL arbitraria."""
    if settings is not None and settings.base_url and settings.provider not in _BASE_URL_PROVIDERS:
        raise HTTPException(422, f"base_url solo vale para {' u '.join(_BASE_URL_PROVIDERS)}")


def _proposal(text: str, cv_path: str | None, ai_settings: AISettings | None = None) -> dict:
    """`ai_settings`: proveedor elegido en el asistente, solo para esta llamada (no se guarda)."""
    _check_base_url(ai_settings)
    provider = ai.get_provider(ai_settings) if ai_settings is not None else None
    draft, source = profile_proposal.propose_profile(text, provider=provider)
    return {"draft": draft, "source": source, "text_chars": len(text), "cv_path": cv_path}


def _form_ai_settings(raw) -> AISettings | None:
    """Campo multipart `ai` (JSON de AISettings) o None; 422 si no es válido."""
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise HTTPException(422, "El campo 'ai' debe ser JSON")
    try:
        settings = AISettings.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False, include_input=False)) from None
    _check_base_url(settings)
    return settings


@app.get("/api/setup/status", response_model=SetupStatusOut)
def setup_status():
    """`needs_setup` (asistente obligatorio) solo si falta el perfil. Una instalación antigua con profile.json
    pero sin jobhunter.yaml propio sigue con los valores por defecto: el dashboard le sugiere el asistente
    (`has_config` false) sin forzarlo."""
    has_config = user_config_path().is_file()
    has_profile = profile_store.profile_exists()
    return {"needs_setup": not has_profile, "has_profile": has_profile, "has_config": has_config}


@app.get("/api/setup/markets", response_model=dict[str, list[MarketSourceOut]])
def setup_markets():
    return setup_builder.load_markets()


@app.post("/api/setup/cv", response_model=SetupProposalOut)
async def setup_upload_cv(request: Request):
    """Sube el CV (multipart, campo `file`), lo guarda en JH_HOME/cv con nombre saneado y propone un borrador.

    Exige Content-Length (411) y rechaza más de 10 MB (413) antes de leer el cuerpo; además se lee por trozos y se corta al pasar de 10 MB (413) sin dejar nada en disco; un archivo que no se
    puede leer (cifrado, vacío, corrupto) da 400 con el motivo y tampoco se guarda."""
    length = request.headers.get("content-length", "")
    if not length.isdigit():
        raise HTTPException(411, "Falta la cabecera Content-Length")
    if int(length) > cv_reader.MAX_FILE_BYTES + _MULTIPART_OVERHEAD:
        raise HTTPException(413, _CV_TOO_BIG)
    form = await request.form(max_files=1, max_fields=5)
    try:
        ai_settings = _form_ai_settings(form.get("ai"))
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(400, "Falta el archivo del CV (campo 'file')")
        name = _safe_cv_filename(upload.filename)
        cv_dir = Path(config.CV_DIR)
        cv_dir.mkdir(parents=True, exist_ok=True)
        tmp = cv_dir / f".upload-{uuid.uuid4().hex}{Path(name).suffix}"
        try:
            size = 0
            with tmp.open("wb") as fh:
                while chunk := await upload.read(_UPLOAD_CHUNK):
                    size += len(chunk)
                    if size > cv_reader.MAX_FILE_BYTES:
                        raise HTTPException(413, _CV_TOO_BIG)
                    fh.write(chunk)
            try:
                text = await run_in_threadpool(cv_reader.extract_text, tmp)
            except cv_reader.CVReadError as exc:
                raise HTTPException(400, str(exc)) from None
            except Exception as exc:  # noqa: BLE001 — un archivo raro nunca debe dar 500
                logging.getLogger(__name__).info("CV ilegible: %s", type(exc).__name__)
                raise HTTPException(400, "No se pudo leer el CV; prueba con otro archivo o rellena el perfil a mano")
            name = _free_cv_name(cv_dir, name)
            os.replace(tmp, cv_dir / name)
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        await form.close()
    return await run_in_threadpool(_proposal, text, f"cv/{name}", ai_settings)


@app.post("/api/setup/propose", response_model=SetupProposalOut)
def setup_propose(body: SetupTextIn):
    """Igual que subir el CV pero con el texto pegado a mano."""
    return _proposal(body.text, None, body.ai)


@app.post("/api/setup/apply", response_model=SetupApplyOut)
def setup_apply(answers: setup_builder.SetupAnswers):
    """Escribe profile.json y jobhunter.yaml a partir de las respuestas del asistente."""
    _check_base_url(answers.ai)
    try:
        return setup_builder.apply_setup(answers)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/api/setup/current", response_model=setup_builder.SetupAnswers)
def setup_current():
    """Respuestas equivalentes a la configuración actual, para volver a ejecutar el asistente sin empezar de cero."""
    return setup_builder.current_answers()


@app.get("/api/profile")
def get_profile():
    return profile_store.load_profile()


async def _limit_profile_size(request: Request) -> None:
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_PROFILE_BYTES:
        raise HTTPException(413, "El perfil supera el tamaño máximo de 1 MB")


@app.put("/api/profile", dependencies=[Depends(_limit_profile_size)])
def put_profile(profile: ProfileIn = Body(...)):
    """Sustituye el perfil completo y devuelve lo guardado. Validación laxa (`ProfileIn`): las secciones
    conocidas deben tener su forma (si no, 422); las claves desconocidas se guardan tal cual. Los campos
    derivados (código de país, permiso de trabajo, nombre canónico de idioma) se recalculan como en el asistente."""
    profile_store.save_profile(setup_builder.normalize_profile(profile.model_dump(exclude_unset=True)))
    return profile_store.load_profile()


def _merge_settings(model, current, updates: dict):
    """Sección actual + campos enviados, revalidada (422 si el resultado no vale)."""
    try:
        return model.model_validate({**current.model_dump(), **updates})
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from None


def _save_section(current, section: str, settings) -> None:
    try:
        save_config(current.model_copy(update={section: settings}), user_config_path())
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from None


def _ai_settings_out() -> dict:
    sources = {provider: _secret_source(name) for provider, name in _API_KEY_SECRETS.items()}
    return {
        **get_config().ai.model_dump(),
        "has_key": {provider: src is not None for provider, src in sources.items()},
        "key_source": sources,
    }


@app.get("/api/settings/ai", response_model=AISettingsOut)
def get_ai_settings():
    return _ai_settings_out()


@app.put("/api/settings/ai", response_model=AISettingsOut)
def put_ai_settings(body: AISettingsIn):
    """Actualiza la sección `ai:` de jobhunter.yaml: solo cambian los campos enviados. La clave de API
    (anthropic/openai) va al llavero. `base_url` solo vale para ollama/openai: con openai, la clave de API se
    envía a esa URL, así que debe ser un servidor de confianza."""
    _require_user_config()
    current = get_config()
    settings = _merge_settings(AISettings, current.ai, body.model_dump(exclude_unset=True, exclude={"api_key"}))
    _check_base_url(settings)
    api_key = (body.api_key or "").strip()
    if api_key:
        name = _API_KEY_SECRETS.get(settings.provider)
        if name is None:
            raise HTTPException(400, f"El proveedor {settings.provider} no usa clave de API")
        _store_secret(name, api_key)
    _save_section(current, "ai", settings)
    return _ai_settings_out()


@app.post("/api/settings/ai/key", response_model=AIKeyOut)
def put_ai_key(body: AIKeyIn):
    """Guarda la clave de API en el llavero (vale antes de completar el asistente). Nunca la devuelve."""
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(422, "La clave de API está vacía")
    name = _API_KEY_SECRETS[body.provider]
    _store_secret(name, api_key)
    source = _secret_source(name)
    return {"provider": body.provider, "has_key": source is not None, "key_source": source}


@app.post("/api/settings/ai/test", response_model=CheckOut)
def check_ai_settings():
    """Comprueba el proveedor configurado (clave válida, CLI instalada y con sesión...)."""
    try:
        ok, message = ai.get_provider().check()
    except Exception as exc:  # noqa: BLE001 — se informa solo el tipo, nunca el detalle
        ok, message = False, f"No se pudo comprobar la IA ({type(exc).__name__})."
    return {"ok": ok, "message": message}


def _email_settings_out() -> dict:
    source = _secret_source(_SMTP_SECRET)
    return {**get_config().email.model_dump(), "has_password": source is not None, "password_source": source}


@app.get("/api/settings/email", response_model=EmailSettingsOut)
def get_email_settings():
    return _email_settings_out()


@app.put("/api/settings/email", response_model=EmailSettingsOut)
def put_email_settings(body: EmailSettingsIn):
    """Actualiza la sección `email:` de jobhunter.yaml (solo los campos enviados); la contraseña SMTP va al llavero."""
    _require_user_config()
    current = get_config()
    settings = _merge_settings(EmailSettings, current.email, body.model_dump(exclude_unset=True, exclude={"password"}))
    password = body.password or ""
    if password:
        _store_secret(_SMTP_SECRET, password)
    _save_section(current, "email", settings)
    return _email_settings_out()


@app.post("/api/settings/email/test", response_model=CheckOut)
def check_email_settings():
    """Conecta y se autentica con el servidor SMTP, sin enviar nada."""
    ok, message = email_sender.check_smtp_connection()
    return {"ok": ok, "message": message}


@app.get("/api/settings/sources", response_model=list[SourceSettingOut])
def get_sources_settings():
    return setup_builder.sources_view()


@app.put("/api/settings/sources", response_model=list[SourceSettingOut])
def put_sources_settings(body: SourcesIn):
    """Reescribe la sección `sources:` de jobhunter.yaml. Una fuente `requires_ack` solo se activa si viene en
    `acknowledged` (si no, 422); las que siguen activas conservan sus ajustes."""
    _require_user_config()
    try:
        cfg = setup_builder.update_sources(body.enabled, body.acknowledged, get_config())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        save_config(cfg, user_config_path())
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from None
    return setup_builder.sources_view()


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=API_PORT, reload=True)
