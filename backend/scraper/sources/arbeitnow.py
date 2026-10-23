"""Arbeitnow: API JSON pública de empleo (https://www.arbeitnow.com/api/job-board-api)."""
from __future__ import annotations

import datetime
import requests

from scraper.sources import Attribution, RunContext, SourceError, SourceSpec

HEADERS = {"User-Agent": "jobhunter-es (+https://github.com/javipiazza94/jobhunter-es)"}
BASE_URL = "https://www.arbeitnow.com/api/job-board-api"


def _format_date(val: int | str | None) -> str:
    if not val:
        return ""
    if isinstance(val, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc).isoformat()
        except Exception:
            return str(val)
    return str(val)


def _matches_keywords(job: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = f"{job.get('title', '')} {' '.join(job.get('tags') or [])}".lower()
    return any(kw.lower() in text for kw in keywords)


def run(ctx: RunContext) -> list[dict]:
    params = {}
    if ctx.keywords and len(ctx.keywords) == 1:
        params["search"] = ctx.keywords[0]
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20, headers=HEADERS)
    except Exception as exc:
        raise SourceError(f"Error de conexión con Arbeitnow: {exc}") from exc
    if resp.status_code != 200:
        raise SourceError(f"Arbeitnow HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as exc:
        raise SourceError(f"Arbeitnow JSON inválido: {exc}") from exc
    if not isinstance(data, dict) or "data" not in data:
        raise SourceError("Respuesta de Arbeitnow inesperada (falta 'data')")

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
        location = str(item.get("location") or ("Remote" if item.get("remote") else "")).strip()
        offers.append({
            "title": title,
            "company_name": str(item.get("company_name") or "").strip(),
            "location": location,
            "url": url,
            "posted_at": _format_date(item.get("created_at")),
            "description": str(item.get("description") or "").strip(),
            "tech_stack": ", ".join(str(t) for t in item.get("tags") or []),
            "salary_text": "",
            "source": "arbeitnow",
        })
    return offers


SPEC = SourceSpec(
    id="arbeitnow",
    label={"es": "Arbeitnow", "en": "Arbeitnow"},
    markets=("remote", "global"),
    default_on=False,
    kind="json",
    start_url=BASE_URL,
    attribution=Attribution(name="Arbeitnow", url="https://www.arbeitnow.com", required=False),
    order=52,
    run=run,
)
