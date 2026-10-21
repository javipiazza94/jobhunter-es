---
name: new-scraper
description: Añade un portal de empleo nuevo al proyecto siguiendo el patrón de scraper/infojobs.py (parser puro + test con HTML de muestra + registro en runner + scoring). Úsalo cuando se pida scrapear un portal nuevo o arreglar uno roto.
argument-hint: "<portal> <url-listado>"
---

Patrón de este repo (modelo: `backend/scraper/infojobs.py` y `backend/tests/test_infojobs.py`):

1. **Parser puro** `_parse_card_html(html, base_url) -> dict | None` en `backend/scraper/<portal>.py`, con BeautifulSoup. Devuelve `title, url, company_name, location, description, salary_min, salary_max, tech_stack, source`. `None` si falta título o URL. Docstring de módulo con URL de búsqueda y el selector principal, más cómo inspeccionarlo si se rompe.
2. **Clase/función de scraping** heredando de `scraper.base.BaseScraper`, con Playwright; respeta `rate_gate.py` (no machacar el sitio) y paginación con `max_pages`.
3. **Test** `backend/tests/test_<portal>.py`: HTML de muestra real (copiado de la web, anonimizado) → comprobar campos, y caso `<div></div>` → `None`. Sin red en los tests.
4. **Registro** en `backend/scraper/runner.py` (función `run_<portal>_source(dry_run, max_pages)` + opción `--source`), guardando con `_save_source` → `save_scored_offers`, que puntúa con `filter_engine`.
5. **Verificar**: `/test backend`, luego `python -m scraper.runner --source <portal> --dry-run` y contrastar con la web real (datos reales, no solo tests verdes).
6. Actualizar la lista de fuentes en `README.md`.

No hagas commit ni envíes candidaturas. Si el portal exige login/captcha, para y pregunta.
