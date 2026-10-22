"""InfoJobs (España): scraping con Playwright (scraper/infojobs.py). Requiere aceptar su aviso de términos."""
from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec

_BASE = "https://www.infojobs.net"


async def run(ctx: RunContext) -> list[dict]:
    """Suelta: `sources.infojobs.keywords`; en un track, sus keywords. La ubicación la resuelve el scraper."""
    from scraper import infojobs

    if ctx.track_id is None:
        return await infojobs.run_infojobs(keywords=ctx.settings.get("keywords", []), max_pages=ctx.max_pages)
    return await infojobs.run_infojobs(ctx.keywords, ctx.max_pages)


SPEC = SourceSpec(
    id="infojobs",
    label={"es": "InfoJobs", "en": "InfoJobs"},
    markets=("spain",),
    requires_ack=True,
    kind="playwright",
    start_url=f"{_BASE}/jobsearch/search-results/list.xhtml",
    attribution=Attribution(name="InfoJobs", url=_BASE),
    params={
        "keywords": ParamSpec("list[str]", [], "Palabras clave (fuente suelta)"),
        "province_id": ParamSpec("str", None, "Id de provincia de InfoJobs (filtra de verdad)"),
        "normalized_location": ParamSpec("str", None, "Ubicación normalizada (si no hay province_id)"),
    },
    track_pipeline=True,
    company_query=True,
    order=20,
    run=run,
)
