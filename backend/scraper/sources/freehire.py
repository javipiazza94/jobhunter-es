"""Freehire: API JSON pública de ofertas (https://freehire.me/api/v1/jobs)."""
from __future__ import annotations

import requests

from scraper.sources import Attribution, RunContext, SourceError, SourceSpec

HEADERS = {"User-Agent": "jobhunter-es (+https://github.com/javipiazza94/jobhunter-es)"}
BASE_URL = "https://freehire.me/api/v1/jobs"


def _matches_keywords(job: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = f"{job.get('title', '')} {' '.join(job.get('skills') or [])}".lower()
    return any(kw.lower() in text for kw in keywords)


def run(ctx: RunContext) -> list[dict]:
    params: dict[str, str | int] = {"limit": 50}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20, headers=HEADERS)
    except Exception as exc:
        raise SourceError(f"Error de conexión con Freehire: {exc}") from exc
    if resp.status_code != 200:
        raise SourceError(f"Freehire HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as exc:
        raise SourceError(f"Freehire JSON inválido: {exc}") from exc
    if not isinstance(data, dict) or "data" not in data:
        raise SourceError("Respuesta de Freehire inesperada (falta 'data')")

    offers: list[dict] = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        if not _matches_keywords(item, ctx.keywords):
            continue
        offers.append({
            "title": title,
            "company_name": str(item.get("company") or "").strip(),
            "location": str(item.get("location") or "Remote").strip(),
            "url": url,
            "posted_at": str(item.get("posted_at") or item.get("created_at") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "tech_stack": ", ".join(str(s) for s in item.get("skills") or []),
            "salary_text": "",
            "source": "freehire",
        })
    return offers


SPEC = SourceSpec(
    id="freehire",
    label={"es": "Freehire", "en": "Freehire"},
    markets=("remote", "global"),
    default_on=False,
    kind="json",
    start_url=BASE_URL,
    attribution=Attribution(name="Freehire", url="https://freehire.me", required=False),
    order=53,
    run=run,
)
