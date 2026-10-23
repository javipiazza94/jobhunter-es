"""Manfred (España): API JSON pública de ofertas (scraper/manfred.py)."""
from config import MANFRED_API_BASE
from scraper.sources import Attribution, RunContext, SourceSpec


def run(ctx: RunContext) -> list[dict]:
    """Recorre la API con su número de páginas propio (no usa `max_pages` ni keywords)."""
    from scraper import manfred

    return manfred.run_manfred()


SPEC = SourceSpec(
    id="manfred",
    label={"es": "Manfred", "en": "Manfred"},
    markets=("spain", "remote"),
    default_on=True,
    kind="json",
    start_url=MANFRED_API_BASE,
    attribution=Attribution(name="Manfred", url="https://www.getmanfred.com"),
    order=30,
    run=run,
)
