"""
scraper/manfred.py — Fetches job offers from GetManfred.com public API.

Manfred is a popular tech job platform in Spain, especially for startups.
Unlike other portals, Manfred exposes a public JSON API — no scraping needed.

API endpoint: https://www.getmanfred.com/api/v2/public/offers
Response: JSON array with title, company, location, salary, tags, url, etc.
"""
import logging
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

MANFRED_API_BASE = "https://www.getmanfred.com/api/v2/public/offers"
MANFRED_WEB_BASE = "https://www.getmanfred.com"

# Headers that mimic a real browser request
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.getmanfred.com/ofertas-empleo",
}

def _parse_offer(raw: dict) -> dict | None:
    """Convert a Manfred API offer object to our internal format."""
    title = raw.get("position") or raw.get("title") or raw.get("name")
    if not title:
        return None

    # Build canonical URL from slug
    slug = raw.get("slug") or str(raw.get("id", ""))
    url = f"{MANFRED_WEB_BASE}/es/ofertas-empleo/{slug}"

    # Company info
    company = raw.get("company") or {}
    company_name = company.get("name") if isinstance(company, dict) else str(company) if company else None

    # Location — API v2 returns list of strings directly
    locations_raw = raw.get("locations") or []
    if isinstance(locations_raw, list):
        str_locs = [str(loc) for loc in locations_raw if loc]
        location = ", ".join(str_locs[:2]) if str_locs else None
    else:
        location = str(locations_raw) if locations_raw else None

    # Remote — remotePercentage: 100 = full remote, 0 = presencial
    remote_pct = raw.get("remotePercentage", 0)
    if remote_pct == 100:
        location = f"{location} (Remoto)" if location else "Remoto"
    elif remote_pct >= 50:
        location = f"{location} (Híbrido)" if location else "Híbrido"

    # Salary — now flat fields salaryFrom / salaryTo
    salary_min = raw.get("salaryFrom") or None
    salary_max = raw.get("salaryTo") or None
    salary_text = ""
    if salary_min or salary_max:
        parts = []
        if salary_min:
            parts.append(f"{int(salary_min):,}€".replace(",", "."))
        if salary_max:
            parts.append(f"{int(salary_max):,}€".replace(",", "."))
        salary_text = " - ".join(parts)

    # Description
    description = raw.get("description") or raw.get("summary") or raw.get("excerpt")

    # Experience — not in v2 list endpoint; leave as None
    experience = raw.get("experienceMin") or raw.get("seniority")

    return {
        "title": title,
        "url": url,
        "company_name": company_name,
        "location": location,
        "description": description,
        "salary_min": int(salary_min) if salary_min else None,
        "salary_max": int(salary_max) if salary_max else None,
        "salary_text": salary_text,
        "tech_stack": None,
        "source": "manfred",
        "experience_level": _normalise_experience(experience),
    }


def _normalise_experience(exp: str | int | None) -> str | None:
    """Map Manfred seniority to our normalised levels."""
    if exp is None:
        return None
    exp_str = str(exp).lower()
    if any(j in exp_str for j in ("junior", "jr", "0", "1", "2")):
        return "junior"
    if any(m in exp_str for m in ("mid", "middle", "3", "4", "5")):
        return "mid"
    if any(s in exp_str for s in ("senior", "sr", "6", "7", "8")):
        return "senior"
    if any(l in exp_str for l in ("lead", "principal", "staff", "9", "10")):
        return "lead"
    return None


def run_manfred(max_pages: int = 5) -> list[dict]:
    """
    Fetch offers from Manfred's public API.
    Returns list of offer dicts in our standard format.
    """
    all_offers: list[dict] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        params: dict = {"lang": "ES", "page": page, "limit": 50}
        url = f"{MANFRED_API_BASE}?{urlencode(params)}"
        logger.info("Manfred API page %d: %s", page, url)

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code == 404:
                logger.info("Manfred: page %d returned 404, done", page)
                break
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Manfred API error on page %d: %s", page, e)
            break

        try:
            data = resp.json()
        except ValueError:
            logger.error("Manfred: invalid JSON on page %d", page)
            break

        # API might return {"data": [...]} or just [...]
        offers_list = data if isinstance(data, list) else data.get("data", data.get("offers", []))
        if not isinstance(offers_list, list):
            logger.info("Manfred: unexpected response shape on page %d", page)
            break

        if not offers_list:
            logger.info("Manfred: empty page %d, done", page)
            break

        page_count = 0
        for raw in offers_list:
            offer = _parse_offer(raw)
            if offer and offer.get("url") and offer["url"] not in seen_urls:
                seen_urls.add(offer["url"])
                all_offers.append(offer)
                page_count += 1

        logger.info("Manfred page %d: %d new offers (total %d)", page, page_count, len(all_offers))

    logger.info("Manfred total: %d unique offers", len(all_offers))
    return all_offers
