"""Indeed (España): HTML vía ScraperAPI con la clave propia del usuario (scraper/indeed.py)."""
from config import INDEED_BASE
from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec


async def run(ctx: RunContext) -> list[dict]:
    """keywords × locations de `sources.indeed`; sin SCRAPERAPI_KEY el scraper no busca nada."""
    from scraper import indeed

    return await indeed.run_indeed(ctx.settings.get("keywords", []), ctx.settings.get("locations", []),
                                   ctx.max_pages)


SPEC = SourceSpec(
    id="indeed",
    label={"es": "Indeed (requiere SCRAPERAPI_KEY)", "en": "Indeed (requires SCRAPERAPI_KEY)"},
    markets=("global",),
    kind="html",
    start_url=f"{INDEED_BASE}/jobs",
    attribution=Attribution(name="Indeed", url=INDEED_BASE),
    params={
        "keywords": ParamSpec("list[str]", [], "Palabras clave"),
        "locations": ParamSpec("list[str]", [], "Ubicaciones"),
    },
    requires_secret="scraperapi_key",
    company_query=True,
    order=60,
    run=run,
)
