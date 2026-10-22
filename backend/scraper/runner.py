"""
scraper/runner.py — CLI orchestrator for all scrapers.
Usage:
  python -m scraper.runner --source seed
  python -m scraper.runner --source tecnoempleo --dry-run
  python -m scraper.runner --source contacts
  python -m scraper.runner --source all
  python -m scraper.runner --track sap        # pipeline multi-portal del track "sap" (jobhunter.yaml)
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_conn, init_db, stats
from scraper import sources as source_registry
from scraper.persist import save_scored_offers
from scraper.seed_loader import load_seed
from search_config import get_config, source_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _log_dry_run(name: str, offers: list[dict]) -> None:
    logger.info("[DRY-RUN] %s: would save %d offers", name, len(offers))
    for o in offers[:10]:
        logger.info("  %s | %s | %s", o.get("title"), o.get("company_name"), o.get("location"))


def _save_source(name: str, offers: list[dict], source: str, dry_run: bool) -> None:
    if dry_run:
        _log_dry_run(name, offers)
        return
    conn = get_conn()
    saved = save_scored_offers(conn, offers, source)
    conn.close()
    logger.info("%s: %d offers saved to DB", name, saved)


async def run_source(source_id: str, dry_run: bool, max_pages: int) -> None:
    """Una fuente suelta del registro (scraper/sources) con sus ajustes de jobhunter.yaml; guarda con su id."""
    spec = source_registry.get(source_id)
    settings = source_settings(source_id)
    ctx = source_registry.RunContext(settings=settings, keywords=list(settings.get("keywords", [])),
                                     max_pages=max_pages, dry_run=dry_run)
    try:
        offers = await source_registry.execute(spec, ctx)
    except source_registry.SourceError as err:
        logger.error("%s failed: %s", spec.label_for("es"), err)
        return
    _save_source(spec.label_for("es"), offers, spec.id, dry_run)


# Nombres históricos del CLI (y de sus tests): delegan en el registro.
async def run_tecnoempleo_source(dry_run: bool, max_pages: int):
    await run_source("tecnoempleo", dry_run, max_pages)


async def run_indeed_source(dry_run: bool, max_pages: int):
    await run_source("indeed", dry_run, max_pages)


def run_manfred_source(dry_run: bool):
    asyncio.run(run_source("manfred", dry_run, 3))  # Manfred usa su propio número de páginas


def run_resolve_websites_source(dry_run: bool, limit: int | None):
    from scraper.website_resolver import resolve_missing_websites
    result = resolve_missing_websites(limit=limit, dry_run=dry_run)
    logger.info("Website resolver: %s", result)


async def run_contacts_source(dry_run: bool):
    from scraper.contact_extractor import run_contact_extraction
    conn = get_conn()
    companies = [
        dict(row) for row in conn.execute(
            "SELECT id, name, website, careers_url FROM companies WHERE website IS NOT NULL"
        ).fetchall()
    ]
    conn.close()
    logger.info("Extracting contacts for %d companies...", len(companies))
    if dry_run:
        logger.info("[DRY-RUN] Would process %d companies", len(companies))
        return
    found = await run_contact_extraction(companies)
    logger.info("Contacts extraction complete: %d contacts found", found)


async def _isolated(label: str, step) -> None:
    """Ejecuta una fuente; si falla se registra y las demás siguen."""
    logger.info("── %s ──", label)
    try:
        await step()
    except Exception as e:
        logger.error("%s failed: %s", label, e)


async def run_track_source(track_id: str, dry_run: bool, max_pages: int, only_sources: set[str] | None = None):
    """Pipeline multi-portal de un track: las fuentes del registro con `track_pipeline`, en orden, con las
    `search_keywords` del track (LinkedIn: las búsquedas de ese track). Lo encontrado se guarda con source = id del
    track.

    `only_sources` (lanzado desde la API): solo los portales activados en `sources:` de jobhunter.yaml; así una
    fuente con aviso (InfoJobs, LinkedIn) no se usa sin haberla aceptado. Las fuentes `track_always` (web de
    empresas seguidas) van siempre. Sin él (CLI `--track`), todos los portales como hasta ahora."""
    track = get_config().track(track_id)
    if track is None:
        raise ValueError(f"track desconocido: {track_id}")
    keywords = track.search_keywords
    locations = source_settings("tecnoempleo").get("locations", [])
    if not keywords:
        logger.warning("Track '%s': search_keywords vacío en jobhunter.yaml; Tecnoempleo, InfoJobs y "
                       "Computrabajo no buscarán nada", track_id)
    if not locations:
        logger.warning("Track '%s': sources.tecnoempleo.locations vacío en jobhunter.yaml; "
                       "Tecnoempleo no buscará nada", track_id)

    for spec in source_registry.track_pipeline():
        label = spec.label_for("es")
        if only_sources is not None and not spec.track_always and spec.id not in only_sources:
            logger.info("%s: fuente no activada en jobhunter.yaml; se omite", label)
            continue

        async def step(spec=spec, label=label):
            ctx = source_registry.RunContext(settings=source_settings(spec.id), keywords=list(keywords),
                                             track_id=track_id, max_pages=max_pages, dry_run=dry_run)
            offers = await source_registry.execute(spec, ctx)
            if not spec.persists_itself:
                _save_source(label, offers, track_id, dry_run)

        await _isolated(label, step)


def print_stats():
    conn = get_conn()
    s = stats(conn)
    conn.close()
    logger.info("── Database stats ──────────────────")
    for k, v in s.items():
        logger.info("  %-25s %d", k, v)


# Cada paso lee el nombre de la función en el momento de la llamada (así se puede sustituir en tests).
def _step_seed(args):
    if args.dry_run:
        logger.info("[DRY-RUN] Would load seed companies")
    else:
        load_seed()


def _step_tecnoempleo(args):
    asyncio.run(run_tecnoempleo_source(args.dry_run, args.max_pages))


def _step_indeed(args):
    asyncio.run(run_indeed_source(args.dry_run, args.max_pages))


def _step_manfred(args):
    run_manfred_source(args.dry_run)


def _step_contacts(args):
    asyncio.run(run_contacts_source(args.dry_run))


def _step_generic(args):
    from scraper.generic import run_generic_source
    asyncio.run(run_generic_source(
        args.dry_run, args.max_pages,
        [x.strip() for x in args.generic_sources.split(",") if x.strip()],
        args.max_indeed_credits,
    ))


def _step_resolve_websites(args):
    run_resolve_websites_source(args.dry_run, args.limit)


def _step_linkedin_login(args):
    from scraper.linkedin_jobs import run_linkedin_login
    asyncio.run(run_linkedin_login())


def _source_step(source_id: str):
    """Paso del CLI para una fuente suelta del registro sin paso propio."""
    def step(args):
        asyncio.run(run_source(source_id, args.dry_run, args.max_pages))
    return step


# fuente → (título en el log, paso)
_STEPS = {
    "seed": ("Seed loader", _step_seed),
    "tecnoempleo": ("Tecnoempleo scraper", _step_tecnoempleo),
    "indeed": ("Indeed scraper", _step_indeed),
    "manfred": ("Manfred API", _step_manfred),
    "contacts": ("Contact extractor", _step_contacts),
    "generic": ("Trabajos puente genéricos", _step_generic),
    "resolve-websites": ("Website resolver (DDG search)", _step_resolve_websites),
    "linkedin-login": ("LinkedIn login (headful)", _step_linkedin_login),
}
# Cualquier otra fuente suelta del registro se puede lanzar con --source <id>.
for _spec in source_registry.registry().values():
    if _spec.standalone and _spec.id not in _STEPS:
        _STEPS[_spec.id] = (_spec.label_for("es"), _source_step(_spec.id))
_ALL_SOURCES = ("seed", "tecnoempleo", "indeed", "manfred", "contacts")  # lo que ejecuta --source all
_NO_STATS = {"linkedin-login"}  # abre un navegador para iniciar sesión; no scrapea nada


def main():
    parser = argparse.ArgumentParser(description="Job Hunter Spain — Scraper Runner")
    parser.add_argument(
        "--source",
        choices=[*_STEPS, "all", "sap"],  # "sap" ya no existe: se acepta solo para dar un error útil
        default=None,
        help="Data source to run (default: seed)",
    )
    parser.add_argument(
        "--track",
        default=None,
        metavar="ID",
        help="Pipeline multi-portal de un track de jobhunter.yaml",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print results without saving")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages per keyword")
    parser.add_argument("--limit", type=int, default=None, help="Max companies (resolve-websites)")
    parser.add_argument("--generic-sources", default="infojobs",
                        help="generic: portales a usar, separados por coma (infojobs,indeed)")
    parser.add_argument("--max-indeed-credits", type=int, default=200,
                        help="generic: tope de créditos ScraperAPI para Indeed (5 por página)")
    args = parser.parse_args()

    if args.source == "sap":
        parser.error("--source sap ya no existe: usa --track sap (los tracks se definen en jobhunter.yaml)")
    if args.track and args.source:
        parser.error("--track y --source son excluyentes")
    if args.track:
        track = get_config().track(args.track)
        valid = [t.id for t in get_config().standard_tracks()]
        if track is None or track.kind != "standard":
            parser.error(f"track '{args.track}' no disponible para --track (tracks: {', '.join(valid)})")
    args.source = args.source or "seed"

    conn = get_conn()
    init_db(conn)
    conn.close()

    if args.track:
        logger.info("── Track %s (multi-portal) ──", args.track)
        asyncio.run(run_track_source(args.track, args.dry_run, args.max_pages))
        print_stats()
        return

    for source in (_ALL_SOURCES if args.source == "all" else (args.source,)):
        title, step = _STEPS[source]
        logger.info("── %s ──", title)
        step(args)

    if args.source not in _NO_STATS:
        print_stats()


if __name__ == "__main__":
    main()
