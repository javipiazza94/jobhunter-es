"""Computrabajo (hoy solo el portal de España): scraping con Playwright (scraper/computrabajo.py). Solo dentro del
pipeline de un track (no se lanza suelta)."""
from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec

_BASE = "https://www.computrabajo.es"


async def run(ctx: RunContext) -> list[dict]:
    """Keywords del track; la ubicación sale de `sources.computrabajo.location` (dentro del scraper)."""
    from scraper import computrabajo

    return await computrabajo.run_computrabajo(ctx.keywords, ctx.max_pages)


SPEC = SourceSpec(
    id="computrabajo",
    label={"es": "Computrabajo", "en": "Computrabajo"},
    markets=("spain",),
    default_on=True,
    kind="playwright",
    start_url=_BASE,
    attribution=Attribution(name="Computrabajo", url=_BASE),
    params={"location": ParamSpec("str", None, "Ciudad o provincia (vacío = búsqueda nacional)")},
    track_pipeline=True,
    standalone=False,
    order=40,
    run=run,
)
