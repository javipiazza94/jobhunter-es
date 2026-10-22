"""RemoteOK: API JSON pública de empleo remoto (https://remoteok.com/api)."""
from __future__ import annotations

import requests

from scraper.sources import Attribution, RunContext, SourceError, SourceSpec

HEADERS = {"User-Agent": "jobhunter-es (+https://github.com/javipiazza94/jobhunter-es)"}
BASE_URL = "https://remoteok.com/api"


def _format_salary(item: dict) -> str:
    s_min = item.get("salary_min")
    s_max = item.get("salary_max")
    if s_min and s_max:
        return f"${s_min} - ${s_max}"
    if s_min:
        return f"From ${s_min}"
    if s_max:
        return f"Up to ${s_max}"
    return ""


def _matches_keywords(job: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = f"{job.get('position', '')} {' '.join(job.get('tags') or [])}".lower()
    return any(kw.lower() in text for kw in keywords)


def run(ctx: RunContext) -> list[dict]:
    params = {}
    if ctx.keywords and len(ctx.keywords) == 1:
        params["tag"] = ctx.keywords[0].lower()
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20, headers=HEADERS)
    except Exception as exc:
        raise SourceError(f"Error de conexión con RemoteOK: {exc}") from exc
    if resp.status_code != 200:
        raise SourceError(f"RemoteOK HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as exc:
        raise SourceError(f"RemoteOK JSON inválido: {exc}") from exc
    if not isinstance(data, list):
        raise SourceError("Respuesta de RemoteOK inesperada (debe ser una lista)")

    offers: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        position = str(item.get("position") or "").strip()
        url = str(item.get("url") or "").strip()
        if not position or not url:
            continue
        if not _matches_keywords(item, ctx.keywords):
            continue
        offers.append({
            "title": position,
            "company_name": str(item.get("company") or "").strip(),
            "location": str(item.get("location") or "Remote").strip(),
            "url": url,
            "posted_at": str(item.get("date") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "tech_stack": ", ".join(str(t) for t in item.get("tags") or []),
            "salary_text": _format_salary(item),
            "source": "remoteok",
        })
    return offers


SPEC = SourceSpec(
    id="remoteok",
    label={"es": "RemoteOK", "en": "RemoteOK"},
    markets=("remote", "global"),
    default_on=False,
    kind="json",
    start_url=BASE_URL,
    attribution=Attribution(name="RemoteOK", url="https://remoteok.com", required=True),
    order=51,
    run=run,
)
