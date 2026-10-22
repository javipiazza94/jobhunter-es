"""Computrabajo: scraping con Playwright por país (España y Latinoamérica)."""
from scraper.computrabajo import COMPUTRABAJO_BASE, country_base_url
from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec


async def run(ctx: RunContext) -> list[dict]:
    """Keywords del track; la ubicación y país salen de `sources.computrabajo`."""
    from scraper import computrabajo

    country = (ctx.settings.get("country") or "es").strip().lower()
    return await computrabajo.run_computrabajo(ctx.keywords, ctx.max_pages, country=country)


def start_url_for(settings: dict | None) -> str:
    country = (settings.get("country") if settings else None) or "es"
    return country_base_url(country)


SPEC = SourceSpec(
    id="computrabajo",
    label={"es": "Computrabajo", "en": "Computrabajo"},
    markets=("spain", "latam"),
    default_on=True,
    kind="playwright",
    start_url=COMPUTRABAJO_BASE,
    start_url_fn=start_url_for,
    attribution=Attribution(name="Computrabajo", url=COMPUTRABAJO_BASE),
    params={
        "location": ParamSpec("str", None, "Ciudad o provincia (vacío = búsqueda nacional)"),
        "country": ParamSpec("str", "es", "País (es, mx, co, ar, pe, cl...)"),
    },
    track_pipeline=True,
    standalone=False,
    order=40,
    run=run,
)
