# /add-portal — Añadir un portal de empleo (fuente de ofertas)

Guía para añadir una fuente nueva de ofertas de **cualquier mercado e idioma**, siguiendo el patrón de este repo: parser puro + test con datos de muestra + registro en el runner + scoring. Las fuentes específicas de un país suelen vivir en tu fork.

`$ARGUMENTS`: la URL del portal, `--list`, o nada.

Referencias que debes leer antes de escribir código: `.claude/rules/scrapers.md`, `.claude/skills/new-scraper/SKILL.md` y la fuente de referencia `backend/scraper/infojobs.py` con su test `backend/tests/test_infojobs.py`. Si existe `backend/scraper/sources/`, usa su contrato de fuentes (registro de fuentes del proyecto) en lugar del registro manual en `backend/scraper/runner.py`.

## Paso 0 — `--list`

Muestra las fuentes instaladas: lee `backend/scraper/jobs.py` (`SOURCES`) y la sección `sources:` de `JH_HOME/jobhunter.yaml`.

## Paso 1 — Entrevista

Pregunta (salta lo ya dicho): URL pública del portal, nombre en minúsculas (`<portal>`), mercado e idioma, una búsqueda de prueba realista y si el portal ofrece API pública o solo HTML.

## Paso 2 — Investigar el portal con respeto

1. Comprueba `robots.txt` con `backend/automation/robots_check.py` y los términos de uso. Si el portal prohíbe el acceso automatizado, **para**: documenta la fuente como «solo manual» (inbox) y no escribas el scraper.
2. Prefiere una API pública o un feed antes que HTML. Si exige login, captcha o antibot, para y pregunta: nunca se guardan sesiones ni cookies en el repo.
3. Mira una ficha real (`backend/automation/fetch_page.py`, solo GET, límites de tamaño y tiempo) para identificar los selectores o campos.

## Paso 3 — Generar la fuente

1. `backend/scraper/<portal>.py`: parser puro (HTML/JSON → ofertas, **sin red**) separado de la capa de red; devuelve `title, url, company_name, location, description, salary_min, salary_max, tech_stack, source`; `None` si falta título o URL. Respeta `backend/rate_gate.py` y la paginación con `max_pages`.
2. `backend/tests/test_<portal>.py` con una **muestra real anonimizada** (guardada en `backend/tests/fixtures/`) y el caso vacío → `None`. Sin red en los tests.
3. Registro en `backend/scraper/runner.py` y en `SOURCES` de `backend/scraper/jobs.py`; ajustes en `sources:` de `jobhunter.yaml`.
4. Verifica: `cd backend && .venv/bin/python -m pytest -q`, y una pasada real en seco: `.venv/bin/python -m scraper.runner --source <portal> --dry-run`.
5. Añade el portal a la lista de fuentes del `README.md` y, si requiere aviso legal, márcalo con `requires_ack` en `backend/defaults/markets.yaml` (mercados del asistente).

No hagas commit ni lances scraping real sin que el usuario lo confirme.
