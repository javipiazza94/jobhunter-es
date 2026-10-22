"""Webs de empleo de empresas configuradas (scraper/company_direct.py). Va siempre en el pipeline de un track y
guarda ella misma ofertas y contactos."""
import logging

from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec

logger = logging.getLogger(__name__)


async def run(ctx: RunContext) -> list[dict]:
    """Recorre `sources.company_direct.companies`; lo encontrado ya queda guardado, devuelve []."""
    from scraper import company_direct

    found, contacts = await company_direct.run_company_direct(ctx.dry_run)
    logger.info("Company direct: %d offers, %d contacts", found, contacts)
    return []


SPEC = SourceSpec(
    id="company_direct",
    label={"es": "Company direct", "en": "Company direct"},
    kind="playwright",
    attribution=Attribution(name="Web de empleo de la empresa", url=""),
    params={
        "keywords": ParamSpec("list[str]", [], "Una oferta cuenta si su título o texto contiene alguna"),
        "companies": ParamSpec("list[{name,careers_url}]", [], "Empresas y la URL de su web de empleo"),
    },
    track_pipeline=True,
    track_always=True,
    standalone=False,
    persists_itself=True,
    order=45,
    run=run,
)
