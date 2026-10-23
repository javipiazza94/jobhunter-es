# Operación y detalles técnicos

Este documento reúne los detalles de operación que no caben en el [README](../README.es.md): seguridad de la API local, trabajos de scraping, inbox, esquema de la base de datos y ajuste del scoring. Para empezar a usar JobHunter ES, lee primero el README.

## Seguridad de la API local

La API no tiene login, así que solo escucha en `127.0.0.1`, solo atiende peticiones cuyo `Host` sea `localhost`/`127.0.0.1` (configurable con `ALLOWED_HOSTS`) y exige la cabecera `X-JH-Client: dashboard` en `POST`/`PUT`/`PATCH`/`DELETE`. Si llamas a la API con `curl` o un script, añade esa cabecera. Cada fuente de `POST /api/scraper/run` espera `SCRAPER_COOLDOWN_SECONDS` (300 por defecto) entre ejecuciones y no puede lanzarse dos veces a la vez. Detalle y motivos: `docs/adr/0001-proteccion-de-la-api-local.md`.

## Trabajos, inbox, esquema y contrato de la API

- `POST /api/scraper/run` lanza cada fuente como un proceso aparte (`python -m scraper.jobs <fuente>`) con tiempo límite (`JOB_TIMEOUT_SECONDS`, 1800 s por defecto). Su estado y las últimas líneas del log se consultan en `GET /api/jobs` y `GET /api/jobs/{id}`. El estado vive en el proceso de la API.
- **Inbox (n8n):** lo que dejan en `data/inbox/` (`candidaturas_*.txt`, `ofertas_*.txt`) lo carga la propia API: al arrancar y cada 60 s (`JH_INBOX_POLL_SECONDS`, 0 = desactivado), con copia previa de la BD (`data/backups/job_hunter.db.bak-auto-<fecha>`, se conservan las 10 últimas). Los cargadores deduplican, nunca bajan un estado y dejan en el fichero las filas dudosas. El dashboard se refresca solo y avisa de lo que queda sin cargar (`GET /api/inbox/status`; `POST /api/inbox/sync` fuerza la carga). Los trabajos `inbox` (simulacro) e `inbox-apply` siguen disponibles por `POST /api/scraper/run`. Para probar sin tocar tus datos: `JH_DB_PATH` y `JH_INBOX_DIR` apuntan a una copia de la BD y a un inbox temporal.
- La BD lleva versión (`PRAGMA user_version`). Para cambiar el esquema añade una función `_migration_00N_…` al final de `MIGRATIONS` en `backend/database.py` y no edites las anteriores; cada una se ejecuta una vez y de forma atómica.
- Los modelos de la API están en `backend/schemas.py`; `backend/tests/test_api_contract.py` comprueba que los tipos de `frontend/lib/types.ts` no se desajusten con ellos.

## Tracks aislados (trabajos puente)

Un track aislado (trabajo puente) lleva sus búsquedas en `search_keywords` y `remote_search_keywords` (estas últimas se buscan como «<palabra> teletrabajo»); las ubicaciones de esa búsqueda están en `sources.generic`.

## Plantillas propias: seguridad

**Una plantilla puede leer ficheros de tu equipo y meterlos en el PDF que envías: instala solo plantillas de fuentes de confianza.** Registrarla exige confirmarlo (`trusted`; casilla en el dashboard, `--trusted` en el CLI). Como red de seguridad, las plantillas propias se renderizan en un entorno Jinja aislado, toda salida `((( valor )))` se escapa por defecto (`|safe_raw` para texto crudo a propósito) y los compiladores van sin shell-escape. Para plantillas LaTeX propias se prefiere xelatex con kpathsea en modo paranoico (`openin_any=p`, `openout_any=p`: sin rutas absolutas ni `..`); lualatex no se usa con ellas (`\directlua` lee ficheros fuera de kpathsea); **Tectonic no confina las lecturas**, así que solo se usa con plantillas propias si no hay xelatex, y «Preparar candidatura» lo avisa. Los ficheros de una plantilla propia se copian en su propia subcarpeta sin seguir enlaces simbólicos y no pueden usar los nombres reservados de las integradas (`cover.cls`, `OpenFonts/`...); el render tiene tope de tamaño y de tiempo. Typst va con `--root` en la carpeta de trabajo. Los `latexmkrc`/`texmf.cnf` se descartan y un lint de mejor esfuerzo sobre todos los ficheros de texto de la plantilla rechaza `\input`/`\include`/`\openin`/`\read`/`\includegraphics`... con rutas absolutas, `~` o `..`, `\@@input`, alias con `\let` y rutas en macros de órdenes de lectura, `\directlua`/`luacode`, `\write18`, cambios de `\catcode` y órdenes de lectura construidas con `\csname` (no es una barrera completa).

## Ajuste del scoring y de los límites

Umbrales, pesos, keywords, tracks y parámetros de los scrapers viven en `jobhunter.yaml` (`min_relevance`, `keyword_groups`, `tracks`, `sources`…). Los límites de operación (`MAX_EMAILS_PER_DAY`, `RECONTACT_COOLDOWN_DAYS`…) siguen en `backend/config.py`. Para lanzar el buscador de un track: `python -m scraper.runner --track <id>`. Guía de ajuste del scoring: `CLAUDE.md`.

## Base de datos

SQLite en `data/job_hunter.db` (dentro de `JH_HOME`, ignorada por git; `JH_DB_PATH` la redirige).

| Tabla | Contenido |
|-------|-----------|
| `companies` | Empresas con URL, ciudad, sector |
| `job_offers` | Ofertas con score, cv_profile, descripción; `job_kind='generic'` = trabajo puente (aislado del scoring normal) |
| `contacts` | Emails y formularios extraídos |
| `applications` | Borradores y enviadas (status, cover_letter_edited, approved_at) |
| `company_contact_history` | Historial de contactos para cooldown |
