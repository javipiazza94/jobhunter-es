"""
scraper/generic.py — Búsqueda de trabajos "puente" genéricos (poca experiencia, afines a
cv_general: atención al cliente, aeropuerto/handling, administrativo, hostelería/retail y
baja cualificación) en InfoJobs e Indeed. Alcance: provincia objetivo + remoto.

Se ejecuta una vez por cada track aislado de jobhunter.yaml: sus `search_keywords` (presencial) y
`remote_search_keywords` (se buscan como «kw teletrabajo»); ubicaciones en `sources.generic`.
Se guardan con job_kind = id del track y puntuación propia (generic_score), sin tocar
is_relevant/relevance_score (ver database.upsert_generic_offer).
"""
import logging

import requests

from automation.generic_filter import isolated_min_score, score_isolated
from database import get_conn, upsert_company, upsert_generic_offer
from search_config import Track, get_config, source_settings

logger = logging.getLogger(__name__)

INDEED_CREDITS_PER_PAGE = 5  # render=true


def scraperapi_credits(api_key: str) -> dict | None:
    try:
        r = requests.get("http://api.scraperapi.com/account", params={"api_key": api_key}, timeout=20)
        d = r.json()
        return {"used": d.get("requestCount"), "limit": d.get("requestLimit")}
    except Exception as e:  # noqa: BLE001
        logger.warning("ScraperAPI: no se pudo leer el saldo de créditos: %s", e)
        return None


def indeed_credit_estimate(max_pages: int, n_locations: int, n_keywords: int) -> int:
    return n_keywords * n_locations * max_pages * INDEED_CREDITS_PER_PAGE


def _filter_and_score(offers: list[dict], track: Track) -> list[dict]:
    min_score = isolated_min_score(track)
    kept = []
    for o in offers:
        if not o.get("url"):
            continue
        s = score_isolated(o, track)
        if s is None or s < min_score:
            continue
        kept.append({**o, "generic_score": s})
    return kept


def _save(conn, offers: list[dict], source_name: str, dry_run: bool, track_id: str) -> tuple[int, int]:
    """Devuelve (guardadas_nuevas_o_actualizadas, omitidas_por_url_de_otra_categoria)."""
    saved = skipped = 0
    for o in offers:
        if dry_run:
            saved += 1
            if saved <= 8:
                logger.info("  [DRY-RUN] %.2f | %s | %s | %s", o["generic_score"], o.get("title"),
                            o.get("company_name"), o.get("location"))
            continue
        company_name = o.get("company_name") or "Desconocida"
        row = conn.execute("SELECT id FROM companies WHERE name=?", (company_name,)).fetchone()
        cid = row["id"] if row else upsert_company(conn, {"name": company_name, "source": "generic"})
        if upsert_generic_offer(conn, {**o, "company_id": cid}, track_id) is None:
            skipped += 1
        else:
            saved += 1
    logger.info("%s: %d guardadas, %d omitidas (URL de otra categoría)",
                source_name, saved, skipped)
    return saved, skipped


async def run_generic_source(dry_run: bool, max_pages: int, sources: list[str],
                             max_indeed_credits: int) -> None:
    """Búsqueda puente de cada track aislado de la configuración."""
    tracks = get_config().isolated_tracks()
    if not tracks:
        logger.warning("No hay ningún track aislado (kind: isolated) en jobhunter.yaml; no hay búsqueda puente que hacer")
        return
    for track in tracks:
        await _run_track(track, dry_run, max_pages, sources, max_indeed_credits)


async def _run_track(track: Track, dry_run: bool, max_pages: int, sources: list[str],
                     max_indeed_credits: int) -> None:
    keywords = track.search_keywords
    remote_keywords = track.remote_search_keywords
    if not keywords:
        logger.warning("Track aislado '%s': no tiene search_keywords en jobhunter.yaml; se omite su búsqueda",
                       track.id)
        return
    settings = source_settings("generic")
    province_ids = settings.get("infojobs_province_ids", [])
    indeed_locations = settings.get("indeed_locations", [])
    conn = get_conn()
    try:
        if "infojobs" in sources:
            from scraper.infojobs import run_infojobs
            raw: list[dict] = []
            if not province_ids:
                logger.warning("InfoJobs: sources.generic.infojobs_province_ids no está en jobhunter.yaml; "
                               "se omite la búsqueda por provincia")
            for province_id in province_ids:
                raw += await run_infojobs(keywords, max_pages, None, province_id, scroll=True)
            # Remoto: búsqueda nacional por keyword + "teletrabajo"; el filtro exige que el
            # texto de la oferta mencione teletrabajo/remoto (o ubicación objetivo).
            if remote_keywords:
                raw += await run_infojobs([f"{k} teletrabajo" for k in remote_keywords],
                                          max_pages, None, None, scroll=True)
            seen: set[str] = set()
            raw = [o for o in raw if o.get("url") and not (o["url"] in seen or seen.add(o["url"]))]
            kept = _filter_and_score(raw, track)
            logger.info("InfoJobs: %d recogidas, %d pasan el filtro puente", len(raw), len(kept))
            if not raw:
                logger.error("InfoJobs: 0 ofertas recogidas — posible bloqueo o cambio de HTML, "
                             "NO es 'sin resultados'")
            _save(conn, kept, f"InfoJobs-{track.id}", dry_run, track.id)

        if "indeed" in sources and not indeed_locations:
            logger.warning("Indeed: sources.generic.indeed_locations no está en jobhunter.yaml; se omite Indeed")
        elif "indeed" in sources:
            from config import SCRAPERAPI_KEY
            from scraper.indeed import run_indeed
            estimate = indeed_credit_estimate(max_pages, len(indeed_locations), len(keywords))
            credits = scraperapi_credits(SCRAPERAPI_KEY) if SCRAPERAPI_KEY else None
            logger.info("Indeed: estimación %d créditos ScraperAPI (tope %d). Saldo: %s",
                        estimate, max_indeed_credits, credits)
            if estimate > max_indeed_credits:
                logger.error("Indeed: la estimación (%d) supera el tope (%d). Baja --max-pages o "
                             "sube --max-indeed-credits. Se omite Indeed.", estimate, max_indeed_credits)
            elif credits and credits["limit"] is not None and credits["used"] is not None \
                    and credits["limit"] - credits["used"] < estimate:
                logger.error("Indeed: créditos insuficientes (%s). Se omite Indeed.", credits)
            elif dry_run:
                logger.info("[DRY-RUN] Indeed no se ejecuta en dry-run (gastaría créditos).")
            else:
                raw = await run_indeed(keywords, indeed_locations, max_pages)
                kept = _filter_and_score(raw, track)
                logger.info("Indeed: %d recogidas, %d pasan el filtro puente", len(raw), len(kept))
                if not raw:
                    logger.error("Indeed: 0 ofertas recogidas — posible bloqueo/créditos agotados "
                                 "(saldo: %s), NO es 'sin resultados'", scraperapi_credits(SCRAPERAPI_KEY))
                _save(conn, kept, f"Indeed-{track.id}", dry_run, track.id)
                logger.info("Saldo ScraperAPI tras la pasada: %s", scraperapi_credits(SCRAPERAPI_KEY))
    finally:
        conn.close()
