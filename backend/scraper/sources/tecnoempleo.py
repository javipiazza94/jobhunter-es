"""Tecnoempleo (España): portal de empleo tecnológico, scraping con Playwright (scraper/tecnoempleo.py)."""
from config import TECNOEMPLEO_BASE
from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec


async def run(ctx: RunContext) -> list[dict]:
    """Suelta: keywords × locations de `sources.tecnoempleo` con ficha completa. En un track: keywords del track ×
    `sources.tecnoempleo.locations`, sin repetir URL."""
    from scraper import tecnoempleo

    if ctx.track_id is None:
        return await tecnoempleo.run_tecnoempleo(max_pages=ctx.max_pages)
    scraper = tecnoempleo.TecnoempleoScraper()
    seen: set[str] = set()
    offers: list[dict] = []
    for kw in ctx.keywords:
        for loc in ctx.settings.get("locations", []):
            for o in await scraper.scrape_keyword(kw, loc, ctx.max_pages):
                if o.get("url") and o["url"] not in seen:
                    seen.add(o["url"])
                    offers.append(o)
    return offers


SPEC = SourceSpec(
    id="tecnoempleo",
    label={"es": "Tecnoempleo", "en": "Tecnoempleo"},
    market_labels={"remote": {"es": "Tecnoempleo (remoto)", "en": "Tecnoempleo (remote)"}},
    markets=("spain", "remote"),
    default_on=True,
    kind="playwright",
    start_url=f"{TECNOEMPLEO_BASE}/ofertas-trabajo/",
    attribution=Attribution(name="Tecnoempleo", url=TECNOEMPLEO_BASE),
    params={
        "keywords": ParamSpec("list[str]", [], "Palabras clave (fuente suelta)"),
        "locations": ParamSpec("list[str]", [], "Ubicaciones; «remoto» busca teletrabajo"),
        "province_ids": ParamSpec("dict[str,str]", {}, "Ubicación → id de provincia de Tecnoempleo"),
    },
    track_pipeline=True,
    company_query=True,
    order=10,
    run=run,
)
