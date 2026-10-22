"""
scraper/jobs.py — Trabajos que lanza la API (POST /api/scraper/run), ejecutados en un proceso aparte:
    python -m scraper.jobs <fuente>
Así Playwright y los asyncio.run no viven dentro del proceso de la API: un fallo o un cuelgue no
la arrastra, se puede matar por tiempo límite y la memoria se libera al terminar.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import sources as source_registry  # noqa: E402

# Trabajos que no son portales; los portales salen del registro (scraper/sources, los que se lanzan sueltos).
_NON_SOURCE_JOBS = ("seed", "contacts", "inbox", "inbox-apply")
SOURCES = (*_NON_SOURCE_JOBS, *source_registry.standalone_ids())
# `track:<id>[,<id>…]`: pipeline multi-portal de uno o varios tracks (uno detrás de otro, en el mismo proceso),
# limitado a las fuentes activadas en jobhunter.yaml.
TRACK_JOB_PREFIX = "track:"
# Portales que recorre el pipeline de un track y que dependen de estar activados: el trabajo los reserva.
TRACK_PIPELINE_SOURCES = tuple(s.id for s in source_registry.track_pipeline() if not s.track_always)


def _fetch_offers(source: str) -> list[dict]:
    """Ofertas de una fuente suelta del registro, con sus ajustes de jobhunter.yaml (3 páginas)."""
    from search_config import source_settings

    spec = source_registry.get(source)
    settings = source_settings(source)
    ctx = source_registry.RunContext(settings=settings, keywords=list(settings.get("keywords", [])), max_pages=3)
    return asyncio.run(source_registry.execute(spec, ctx))


def run(source: str) -> None:
    if source.startswith(TRACK_JOB_PREFIX):
        from database import get_conn, init_db
        from scraper.runner import run_track_source
        from search_config import get_config
        conn = get_conn()
        init_db(conn)
        conn.close()
        only_sources = set(get_config().sources)

        async def run_tracks() -> list[str]:
            failed = []
            for track_id in source.removeprefix(TRACK_JOB_PREFIX).split(","):
                try:
                    await run_track_source(track_id, dry_run=False, max_pages=3, only_sources=only_sources)
                except Exception:  # noqa: BLE001 — un track roto no impide buscar los demás
                    logging.getLogger(__name__).exception("Falló el track %s", track_id)
                    failed.append(track_id)
            return failed

        failed = asyncio.run(run_tracks())
        if failed:
            raise SystemExit(f"Tracks con error: {', '.join(failed)}")
        return
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
