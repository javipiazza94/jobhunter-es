"""LinkedIn (global): búsquedas con la sesión propia del usuario en Playwright (scraper/linkedin_jobs.py).
Requiere aceptar su aviso: usarla incumple los términos del sitio."""
from scraper.sources import Attribution, ParamSpec, RunContext, SourceSpec


async def run(ctx: RunContext) -> list[dict]:
    """Suelta: todas las `sources.linkedin.searches`; en un track, las de ese track (y las sin track)."""
    from scraper import linkedin_jobs

    if ctx.track_id is None:
        return await linkedin_jobs.run_linkedin_jobs()
    return await linkedin_jobs.run_linkedin_jobs(track=ctx.track_id)


SPEC = SourceSpec(
    id="linkedin",
    label={"es": "LinkedIn", "en": "LinkedIn"},
    markets=("latam", "remote", "global"),
    requires_ack=True,
    ack_warning={
        "es": "Usar esta fuente incumple las Condiciones de uso de LinkedIn (automatización y scraping).",
        "en": "Using this source violates LinkedIn's User Agreement (automation and scraping).",
    },
    kind="playwright",
    start_url="https://www.linkedin.com/jobs/search",
    attribution=Attribution(name="LinkedIn", url="https://www.linkedin.com/jobs"),
    params={"searches": ParamSpec("list[{keywords,location,track}]", [], "Búsquedas; `track` opcional")},
    track_pipeline=True,
    order=50,
    run=run,
)
