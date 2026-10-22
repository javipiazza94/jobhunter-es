"""Remotive: API JSON pública de empleo remoto (https://remotive.com/api/remote-jobs)."""
from __future__ import annotations

import requests

from scraper.sources import Attribution, RunContext, SourceError, SourceSpec

HEADERS = {"User-Agent": "jobhunter-es (+https://github.com/javipiazza94/jobhunter-es)"}
BASE_URL = "https://remotive.com/api/remote-jobs"


def _matches_keywords(job: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = f"{job.get('title', '')} {' '.join(job.get('tags') or [])}".lower()
    return any(kw.lower() in text for kw in keywords)


def run(ctx: RunContext) -> list[dict]:
    params = {}
    if ctx.keywords:
        params["search"] = " ".join(ctx.keywords)
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20, headers=HEADERS)
    except Exception as exc:
        raise SourceError(f"Error de conexión con Remotive: {exc}") from exc
    if resp.status_code != 200:
        raise SourceError(f"Remotive HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as exc:
        raise SourceError(f"Remotive JSON inválido: {exc}") from exc
    if not isinstance(data, dict) or "jobs" not in data:
        raise SourceError("Respuesta de Remotive inesperada (falta 'jobs')")

    offers: list[dict] = []
    for item in data.get("jobs") or []:
        if not isinstance(item, dict):
            continue
        if not _matches_keywords(item, ctx.keywords):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        offers.append({
            "title": str(item.get("title") or "").strip(),
            "company_name": str(item.get("company_name") or "").strip(),
            "location": str(item.get("candidate_required_location") or "Remote").strip(),
            "url": url,
            "posted_at": str(item.get("publication_date") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "tech_stack": ", ".join(str(t) for t in item.get("tags") or []),
            "salary_text": str(item.get("salary") or "").strip(),
            "source": "remotive",
        })
    return offers


SPEC = SourceSpec(
    id="remotive",
    label={"es": "Remotive", "en": "Remotive"},
    markets=("remote", "global"),
    default_on=False,
    kind="json",
    start_url=BASE_URL,
    attribution=Attribution(name="Remotive", url="https://remotive.com", required=True),
    order=50,
    run=run,
)
