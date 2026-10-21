"""
scraper/jobs.py — Trabajos que lanza la API (POST /api/scraper/run), ejecutados en un proceso aparte:
    python -m scraper.jobs <fuente>
Así Playwright y los asyncio.run no viven dentro del proceso de la API: un fallo o un cuelgue no
la arrastra, se puede matar por tiempo límite y la memoria se libera al terminar.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SOURCES = ("seed", "tecnoempleo", "contacts", "indeed", "manfred", "linkedin", "infojobs", "inbox", "inbox-apply")


def _fetch_offers(source: str) -> list[dict]:
    if source == "indeed":
        from scraper.indeed import run_indeed
        from search_config import source_settings
        settings = source_settings("indeed")
        return asyncio.run(run_indeed(settings.get("keywords", []), settings.get("locations", []), max_pages=3))
    if source == "manfred":
        from scraper.manfred import run_manfred
        return run_manfred()
    if source == "tecnoempleo":
        from scraper.tecnoempleo import run_tecnoempleo
        return asyncio.run(run_tecnoempleo(max_pages=3))
    if source == "linkedin":
        from scraper.linkedin_jobs import run_linkedin_jobs
        return asyncio.run(run_linkedin_jobs())
    if source == "infojobs":
        from scraper.infojobs import run_infojobs
        from search_config import source_settings
        return asyncio.run(run_infojobs(keywords=source_settings("infojobs").get("keywords", []), max_pages=3))
    return []


def run(source: str) -> None:
    if source not in SOURCES:
        raise SystemExit(f"Fuente desconocida: {source}. Opciones: {', '.join(SOURCES)}")
    if source in ("inbox", "inbox-apply"):
        from inbox_job import run_inbox
        raise SystemExit(run_inbox(apply=(source == "inbox-apply")))
    if source == "seed":
        from scraper.seed_loader import load_seed
        load_seed()
        return
    if source == "contacts":
        from scraper.runner import run_contacts_source
        asyncio.run(run_contacts_source(dry_run=False))
        return
    from database import get_conn
    from scraper.persist import save_scored_offers
    offers = _fetch_offers(source)
    conn = get_conn()
    try:
        save_scored_offers(conn, offers, source)
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scraper.jobs <fuente>")
    run(sys.argv[1])
