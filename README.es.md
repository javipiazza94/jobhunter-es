# JobHunter ES

[Read in English](README.md) · **Español**

Automatización de candidaturas tecnológicas y de empleo en España con cola de revisión humana. Scraping de ofertas → clasificación configurable por tracks → borradores de cartas → aprobación manual → envío y seguimiento.

## Flujo

```
Tecnoempleo / seed
      ↓
 classify_track()            id de track | manual_review
      ↓
  create_drafts()            applications con status=pending_approval
      ↓
Dashboard "Pendientes"       editar carta + aprobar o rechazar
      ↓
  send_approved(id)          Gmail SMTP → company_contact_history
```

- **SAP** → CV del módulo de la oferta (`cv_sap_modules`: FI_CO / MM / SD; `sap_module` o título) o, sin módulo, `cv_sap_path` — `automation/cv_selector.py` — + plantilla `cover_letter_sap.j2`
- **IA/Dev** → `cv_ia_path` + plantilla `cover_letter_tech.j2`
- **manual_review** → se salta automáticamente (confianza < 0.2)
- **Cooldown** 180 días por empresa para evitar recontactos

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11 · FastAPI · SQLite |
| Scraping | Playwright (stealth) · BeautifulSoup |
| Frontend | Next.js 16 · Tailwind CSS · TypeScript |
| Email | Gmail SMTP (App Password) · Jinja2 |

## Requisitos previos

- Python 3.11+, Node.js 18+, [Bun](https://bun.sh/)
- Gmail con [App Password](https://myaccount.google.com/apppasswords) activada
- Playwright: `playwright install chromium`

## Instalación

```bash
git clone https://github.com/<tu-usuario>/jobhunter-es.git
cd jobhunter-es

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # solo ejecución; para los tests: requirements-dev.txt
playwright install chromium

# Frontend
cd ../frontend
bun install
```

## Configuración

Crea `backend/.env` (o `.env` en la raíz):

```env
GMAIL_USER=tu@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

**Carpeta de datos (`JH_HOME`).** Todo lo personal vive fuera del código, en `JH_HOME` (por defecto `./data/`, ignorada por git): `jobhunter.yaml` (búsqueda, scoring y tracks), `profile.json`, `cv/`, `job_hunter.db`, `inbox/`, `backups/`, `logs/` y `sessions/`. `JH_DB_PATH`, `JH_INBOX_DIR` y `JH_PROFILE_PATH` siguen mandando sobre `JH_HOME`. Si la carpeta no existe, la API la crea al arrancar.

**Búsqueda y scoring (`jobhunter.yaml`).** Sin fichero en `JH_HOME` se usa `backend/defaults/jobhunter.yaml` (desarrollador genérico). Para tu perfil, copia uno de `examples/` (`developer`, `sap-consultant`, `data-ai`; ver `examples/README.md`) a `JH_HOME/jobhunter.yaml` y adáptalo. Un YAML inválido (pesos que no suman 1.0, id de track repetido…) impide arrancar la API y el error indica fichero, campo y motivo. **Los cambios en `jobhunter.yaml` se aplican solos** (la API detecta que el fichero cambió; no hace falta reiniciar): si el fichero tiene un error, la API sigue con la última versión válida y lo registra en el log. Un track aislado (trabajo puente) lleva sus búsquedas en `search_keywords` y `remote_search_keywords` (estas últimas se buscan como «<palabra> teletrabajo»); las ubicaciones de esa búsqueda están en `sources.generic`.

`profile.json` (en `JH_HOME`, ignorado por git; contiene datos personales como DNI y fecha de nacimiento). Cópialo desde la plantilla y edítalo con tus datos:
```bash
mkdir -p data && cp backend/profile.example.json data/profile.json
```
Esquema completo: personal (incluye `dni_nie`, `birth_date` — usados por el handler de SuccessFactors), `availability`, `salary_expectation`, `summary`, `stack`, `languages`, `certifications`, `education`, `experience`.

Copia tus CVs a `data/cv/` con los nombres que indica `profile.json` (por ejemplo `cv_ia_path`, `cv_sap_path`, `cv_sap_modules`, según las claves de `cv:` de cada track).

## Arranque

```bash
# Terminal 1 — API
cd backend && .venv/bin/uvicorn main:app --reload --port 8020

# Terminal 2 — Dashboard
cd frontend && bun run dev
```

Dashboard en `http://localhost:3010`

**Seguridad:** la API no tiene login, así que solo escucha en `127.0.0.1`, solo atiende peticiones cuyo `Host` sea `localhost`/`127.0.0.1` (configurable con `ALLOWED_HOSTS`) y exige la cabecera `X-JH-Client: dashboard` en `POST`/`PUT`/`PATCH`/`DELETE`. Si llamas a la API con `curl` o un script, añade esa cabecera. Cada fuente de `POST /api/scraper/run` espera `SCRAPER_COOLDOWN_SECONDS` (300 por defecto) entre ejecuciones y no puede lanzarse dos veces a la vez. Detalle y motivos: `docs/adr/0001-proteccion-de-la-api-local.md`.

**Trabajos, esquema y contrato:**
- `POST /api/scraper/run` lanza cada fuente como un proceso aparte (`python -m scraper.jobs <fuente>`) con tiempo límite (`JOB_TIMEOUT_SECONDS`, 1800 s por defecto). Su estado y las últimas líneas del log se consultan en `GET /api/jobs` y `GET /api/jobs/{id}`. El estado vive en el proceso de la API.
- **Inbox (n8n):** lo que dejan en `data/inbox/` (`candidaturas_*.txt`, `ofertas_*.txt`) lo carga la propia API: al arrancar y cada 60 s (`JH_INBOX_POLL_SECONDS`, 0 = desactivado), con copia previa de la BD (`data/backups/job_hunter.db.bak-auto-<fecha>`, se conservan las 10 últimas). Los cargadores deduplican, nunca bajan un estado y dejan en el fichero las filas dudosas. El dashboard se refresca solo y avisa de lo que queda sin cargar (`GET /api/inbox/status`; `POST /api/inbox/sync` fuerza la carga). Los trabajos `inbox` (simulacro) e `inbox-apply` siguen disponibles por `POST /api/scraper/run`. Para probar sin tocar tus datos: `JH_DB_PATH` y `JH_INBOX_DIR` apuntan a una copia de la BD y a un inbox temporal.
- La BD lleva versión (`PRAGMA user_version`). Para cambiar el esquema añade una función `_migration_00N_…` al final de `MIGRATIONS` en `backend/database.py` y no edites las anteriores; cada una se ejecuta una vez y de forma atómica.
- Los modelos de la API están en `backend/schemas.py`; `backend/tests/test_api_contract.py` comprueba que los tipos de `frontend/lib/types.ts` no se desajusten con ellos.

## Primer arranque

Sin `profile.json` en la carpeta de datos (`JH_HOME`, `./data/` por defecto), el dashboard abre un asistente de tres pasos en lugar de pedirte editar ficheros a mano. Si ya tienes `profile.json` pero no un `jobhunter.yaml` propio (instalación anterior), la app sigue funcionando con la configuración por defecto y solo muestra un aviso descartable, «Configura tu búsqueda con el asistente», que lo abre precargado y cancelable:

1. **Tu CV.** Sube un PDF o DOCX (hasta 10 MB) o rellena el formulario. El texto se extrae **en local** y el archivo se guarda en `JH_HOME/cv/`. Si hay un proveedor de IA configurado, propone un borrador de perfil a partir del texto; sin IA el borrador sale vacío y lo rellenas tú.
2. **Revisión.** Comprueba y edita lo entendido: puestos objetivo (cada uno será un track), experiencia, herramientas (palabras clave del scoring), idiomas con nivel CEFR, modalidad y ciudad, y elegibilidad (permiso de trabajo, patrocinio de visado, carnet de conducir).
3. **Dónde buscar.** Elige mercados, que sugieren fuentes (las de condiciones de uso delicadas empiezan sin marcar y exigen aceptación expresa), y opcionalmente empresas a seguir. Pulsa «Buscar ofertas».

El asistente escribe `JH_HOME/profile.json` y `JH_HOME/jobhunter.yaml` (tracks, grupos de palabras con pesos que suman 1.0 y `scoring.min_relevance` calibrado al perfil). Todo sigue siendo editable después en la pestaña **Perfil**, que también permite repetir el asistente, cambiar fuentes y configurar la IA y el SMTP. Repetir el asistente no borra nada que no pregunte: en el perfil se conservan el resumen, las cartas, los otros CV, la formación, etc.; en `jobhunter.yaml`, los tracks aislados, los grupos de palabras propios, las reglas de scoring y los ajustes propios de cada fuente (solo se regeneran los tracks estándar y sus grupos).

### Proveedores de IA

La IA es opcional y solo se usa para leer el CV, adaptar cartas de presentación (la plantilla es la alternativa) y preparar entrevistas. **El scoring nunca usa IA.** Con `none` todo funciona con formularios manuales y cartas de plantilla.

| Proveedor | Cómo se conecta | Credenciales |
|-----------|-----------------|--------------|
| `none` (por defecto) | sin IA | no aplica |
| `ollama` | HTTP local (`http://127.0.0.1:11434`), modelo por defecto `llama3.1` | ninguna, nada sale de tu equipo |
| `anthropic` | API de Anthropic, modelo por defecto `claude-sonnet-5-5` | clave de API |
| `openai` | API de OpenAI, modelo por defecto `gpt-4o-mini` | clave de API |
| `claude_cli` | tu **suscripción de Claude** mediante el CLI local `claude -p` | la sesión del propio CLI |
| `codex_cli` | tu **suscripción de ChatGPT** mediante el CLI local `codex exec` | la sesión del propio CLI |

Se elige en el asistente o en Perfil (un botón «Probar» lo comprueba). El modelo se puede cambiar con `ai.model` en `jobhunter.yaml`. Con los proveedores por CLI la app no guarda credenciales de suscripción: solo comprueba que el CLI está instalado y con sesión.

**Secretos.** Las claves de API y la contraseña SMTP van al llavero del sistema operativo (vía `keyring`), nunca a `jobhunter.yaml`, `profile.json`, logs ni respuestas de la API. Las variables de entorno tienen prioridad y son la alternativa si no hay llavero (por ejemplo, Linux sin Secret Service; guardar una clave devuelve entonces un error claro): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GMAIL_APP_PASSWORD` (y `GMAIL_USER`).

**Privacidad.** Nada sale de tu equipo salvo las búsquedas en los portales que actives y, si eliges un proveedor en la nube (`anthropic`, `openai` o los CLI, que hablan con su fabricante), el texto que se le envía (CV, ofertas). Con `ollama` o `none` no hay tráfico de IA.

### Email (SMTP)

El envío es siempre manual y aprobado por ti. En Perfil > Email elige el preset de Gmail (`smtp.gmail.com:587`, STARTTLS, requiere contraseña de aplicación) o un servidor SMTP propio (host, puerto, STARTTLS, usuario, nombre del remitente). La contraseña va al llavero; «Probar» se conecta y autentica sin enviar nada. Una instalación sin sección `email:` sigue funcionando como antes con `GMAIL_USER` y `GMAIL_APP_PASSWORD`.

---

## Uso

Flujo completo (seed → scraping → contactos → borradores → formularios → envío tras aprobación en el dashboard) y comandos: skill `run-pipeline` (`.claude/skills/run-pipeline/SKILL.md`). Ofertas y candidaturas dejadas en el inbox: `docs/inbox.md`.

El botón **"Generar borradores"** del dashboard lanza la generación de borradores y navega directo al tab Pendientes.

## Arquitectura

```
backend/
├── main.py                      FastAPI API REST (:8020)
├── config.py                    Rutas (JH_HOME) y límites de operación
├── search_config.py             Esquema y carga de jobhunter.yaml (scoring, tracks, fuentes)
├── database.py                  SQLite schema + migraciones + upserts (scrapers y motor de candidaturas)
├── repository.py                Consultas SQL de los endpoints (main.py no contiene SQL)
├── defaults/jobhunter.yaml      Configuración genérica por defecto
├── scraper/
│   ├── runner.py                CLI (--source seed|tecnoempleo|indeed|manfred|contacts|generic|… · --track <id>)
│   ├── persist.py               Puntúa y guarda ofertas scrapeadas (punto único)
│   ├── tecnoempleo.py · infojobs.py · computrabajo.py · linkedin_jobs.py · manfred.py · company_direct.py
│   ├── generic.py               Trabajos puente (InfoJobs/Indeed)
│   ├── seed_loader.py           50 empresas con salario público
│   └── contact_extractor.py     Extrae emails y detecta formularios
├── automation/
│   ├── filter_engine.py         Scoring de relevancia + classify_track()
│   ├── generic_filter.py        Scoring de trabajos puente
│   ├── salary.py                Pretensión salarial según ubicación
│   ├── cv_selector.py           Elige el CV de cada candidatura según su track
│   ├── application_engine.py    create_drafts() + fill_forms() + send_approved()
│   ├── form_filler.py · ats_handlers/   Playwright por ATS; nunca pulsa Enviar
│   ├── language_gate.py         Idiomas exigidos vs perfil (exige uno que no tienes → score 0)
│   ├── posting_guard.py         Texto oculto / instrucciones a una IA en ofertas (de ai-job-search, MIT)
│   ├── offer_review.py          Guard + idiomas → job_offers.review_flags (scrapers e inbox)
│   ├── followup.py              Recordatorios a candidaturas sin respuesta y cierre como no_response
│   ├── cover_letter.py          Generación Jinja2 con variación
│   └── email_sender.py          Gmail SMTP con rate limiting
└── scripts/                     load_inbox_offers.py (inbox), watch_sap_ps.py, tagging puntuales

examples/                        jobhunter.yaml de ejemplo (developer, sap-consultant, data-ai)
data/                            JH_HOME por defecto: config, perfil, CVs, BD, inbox (gitignored)

frontend/
├── app/page.tsx                 Dashboard: estado, carga de datos, acciones y modales de detalle
├── app/components/tabs/         Una pestaña por fichero (Ofertas, Candidaturas, Empresas, Contactos, Revisión)
├── app/components/OfferBucketTab.tsx  Una pestaña por track (generadas desde `GET /api/tracks`)
├── app/hooks/                   Filtros de Ofertas y de Candidaturas
├── app/components/PendingCard.tsx  Tarjeta de revisión con textarea editable
└── lib/api.ts                   Cliente API tipado
```

## Tuning

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

## Roadmap

- [x] Scrapers InfoJobs, Computrabajo, LinkedIn (public search) e Indeed
- [x] Form filler con Playwright — SuccessFactors + genérico, probados contra formularios reales (`fill-forms`, nunca auto-envía)
- [x] Form filler: cobertura Workday / Greenhouse / Lever — mismo principio de no auto-enviar, pero sin probar aún contra un formulario real de cada uno (a diferencia de SuccessFactors/genérico). Si sale un falso negativo, hay que ajustar los selectores.
- [x] Integración de herramientas upstream `ai-job-search` (posting guard, robots.txt, compilação LaTeX, verificación PDF/layout, caché de investigación y triage)
- [ ] Hunter.io API para más emails
- [ ] Notificaciones cuando responden (Gmail polling)

## Automatización avanzada y Claude Code

El proyecto incluye comandos interactivos y agentes para Claude Code portados y adaptados de [ai-job-search](https://github.com/MadsLorentzen/ai-job-search):

- **`/apply <url|texto>`**: Flujo orquestado de dos agentes (fetcher + reviewer) con verificación de integridad (`posting_guard`), extracción y redacción de CV y carta.
- **`/rank`**: Triage por lotes de ofertas almacenadas en la base de datos `data/job_hunter.db` contra el perfil del candidato.
- **`/upskill`**: Análisis de brechas de habilidades técnicas y plan de estudio personalizado.
- **`/expand`**: Descubrimiento y enriquecimiento de competencias a partir de documentos locales y GitHub.
- **`/add-template`**: Registro y conmutación de plantillas personalizadas (LaTeX, Typst, etc.).
- **`/add-portal`**: Generador de habilidades de búsqueda para portales de empleo de mercados locales.

### Herramientas de soporte

- **Generador de documentos determinista**: `backend/automation/document_generator.py` (Jinja2 → LaTeX con compilación automática vía Tectonic, LuaLaTeX o XeLaTeX).
- **Verificación ATS y maquetación**: `backend/automation/verify_pdf.py` y `backend/automation/verify_layout.py`.
- **Archivo de candidaturas**: `backend/automation/application_archive.py` (`data/applications/<id>/`).
- **Gate de elegibilidad**: `backend/automation/eligibility_gate.py` (permiso laboral, visado, residencia, titulación).

Para detalles de licencia y derechos de autor de las herramientas portadas y tipografías, consulta [ATTRIBUTION.md](ATTRIBUTION.md).

