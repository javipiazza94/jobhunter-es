# JobHunter ES

[Read in English](README.md) · **Español**

Plataforma de código abierto para buscar empleo y preparar candidaturas, pensada para el mercado laboral español y ampliable a otros países. Rastrea ofertas en varios portales, las clasifica en perfiles de búsqueda configurables, puntúa su relevancia, prepara CV y cartas a medida y mantiene una cola de revisión local: **nada se envía sin que tú lo apruebes**.

Todo funciona en tu equipo. Tus datos (perfil, CV, base de datos, candidaturas) se guardan en una carpeta local y la inteligencia artificial es opcional: sin ella, la aplicación sigue funcionando con formularios y plantillas.

---

## Funcionalidades

- **Búsqueda en varias fuentes:** Tecnoempleo, InfoJobs, Manfred, Computrabajo (por país), LinkedIn, Indeed, Remotive, RemoteOK, Arbeitnow, freehire y webs de empleo de empresas concretas. Un registro de fuentes autodescubierto permite añadir otras con un fichero y su test. Detalle en [docs/sources.md](docs/sources.md).
- **Perfiles de búsqueda (tracks) y scoring configurables:** cada puesto objetivo es un track con sus grupos de palabras clave, pesos, reglas de ubicación, experiencia y salario, definidos en `jobhunter.yaml`. El scoring es determinista; **nunca usa IA**.
- **Filtros de seguridad y elegibilidad:** detección de texto oculto o instrucciones dirigidas a una IA en las ofertas, respeto de `robots.txt`, filtro de idiomas exigidos y filtro de elegibilidad (permiso de trabajo, visado, residencia, titulación).
- **Asistente de primer arranque:** subes tu CV (PDF o DOCX) o rellenas un formulario, revisas lo que la aplicación ha entendido y eliges dónde buscar. Genera tu perfil y tu configuración.
- **Cola de revisión humana:** las candidaturas quedan como borrador en un panel local. Tú editas la carta, apruebas o rechazas; solo entonces se envía.
- **CV y carta en PDF a medida de cada oferta:** con IA (un redactor y un revisor, con un validador que descarta cualquier dato que no figure en tu perfil) o sin IA (a partir de plantillas). Los PDF se verifican (páginas, legibilidad para sistemas de selección automáticos, datos de contacto) y se archivan por candidatura.
- **Plantillas propias:** CV y carta en LaTeX o Typst, con compilación de prueba obligatoria antes de activarlas.
- **Envío por SMTP con aprobación:** preset de Gmail o servidor propio, límite diario y periodo de espera por empresa para no recontactar.
- **Seguimiento:** recordatorios para candidaturas sin respuesta y estados de cada candidatura.
- **Rellenado de formularios de candidatura (ATS):** SuccessFactors, Workday, Greenhouse, Lever y formularios genéricos con Playwright. **Nunca pulsa «Enviar».**
- **Inbox de ficheros:** ofertas y candidaturas dejadas en una carpeta se cargan solas en la base de datos, para integrar flujos externos ([docs/inbox.md](docs/inbox.md)).
- **IA opcional y a tu elección:** Ollama (local), API de Anthropic u OpenAI, o tu suscripción de Claude o ChatGPT mediante su CLI. Las claves van al llavero del sistema.
- **Interfaz en español e inglés**, y documentos en el idioma de la oferta cuando hay plantilla para él.
- **App de escritorio** (Windows, macOS y Linux) que empaqueta todo en un instalador.

### Limitaciones conocidas

- LinkedIn e InfoJobs exigen que aceptes de forma expresa sus condiciones de uso y vienen desactivadas por defecto.
- El rellenado de formularios está probado con SuccessFactors y formularios genéricos; Workday, Greenhouse y Lever siguen el mismo principio, pero no se han probado con un formulario real de cada uno.
- Los instaladores de escritorio no están firmados y los de Windows y macOS son experimentales (ver [App de escritorio](#app-de-escritorio)).

---

## Cómo funciona

```text
Portales de empleo / empresas / ficheros del inbox
                      ↓
           Filtros de seguridad (guard, robots)
                      ↓
        Scoring y clasificación en un track
                      ↓
       Borrador de candidatura y carta a medida
                      ↓
   Panel local («Pendientes») ──> Aprobar / Editar / Rechazar
                      ↓
           Envío y archivo de la candidatura
                      ↓
      Recordatorios y seguimiento de estados
```

---

## Stack

| Capa | Tecnologías |
|---|---|
| **Backend** | Python 3.11 · FastAPI · SQLite · Pydantic |
| **Scraping** | Playwright · BeautifulSoup · ScraperAPI (opcional) |
| **Frontend** | Next.js · TypeScript · Tailwind CSS · Bun |
| **Documentos** | Jinja2 · LaTeX (Tectonic o XeLaTeX) · Typst (opcional) · pypdf · Poppler |
| **IA (opcional)** | Ollama · API de Anthropic · API de OpenAI · CLI de Claude y de Codex |
| **Email** | SMTP (contraseña de aplicación, STARTTLS) |
| **Escritorio** | Tauri 2 · backend congelado con PyInstaller · Tectonic incluido |

---

## Requisitos previos

- Python 3.11 o superior
- Node.js 18 o superior y [Bun](https://bun.sh/)
- Chromium de Playwright: `playwright install chromium`
- Opcional, para compilar PDF en local: [Tectonic](https://tectonic-typesetting.github.io/) (incluido en la app de escritorio) o `xelatex` más Poppler
- Opcional, para compilar la app de escritorio tú mismo: Rust (estable) y las librerías de sistema de Tauri; ver [desktop/README.md](desktop/README.md)

---

## Instalación

```bash
git clone https://github.com/<tu-usuario>/jobhunter-es.git
cd jobhunter-es

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # para desarrollo y tests: requirements-dev.txt
playwright install chromium

# Frontend
cd ../frontend
bun install
```

Si prefieres no usar el terminal, instala la [app de escritorio](#app-de-escritorio).

---

## Configuración

Todo lo personal vive fuera del código, en la **carpeta de datos `JH_HOME`** (por defecto `./data/`, ignorada por git; en la app de escritorio, la carpeta de datos del sistema). Si no existe, la API la crea al arrancar.

| Fichero o carpeta | Contenido |
|---|---|
| `jobhunter.yaml` | Búsqueda, scoring, tracks, fuentes, IA y SMTP |
| `profile.json` | Tu perfil: datos personales, resumen, experiencia, formación, idiomas |
| `cv/` | Tus CV en PDF |
| `job_hunter.db` | Base de datos SQLite |
| `applications/` | CV y carta archivados de cada candidatura |
| `inbox/`, `backups/`, `logs/`, `sessions/` | Entrada de ficheros, copias, registros y sesiones |

**Crear la configuración.** La forma más sencilla es dejar que el [asistente de primer arranque](#primer-arranque) genere `profile.json` y `jobhunter.yaml`. También puedes crearlos a mano:

```bash
mkdir -p data
cp backend/defaults/jobhunter.yaml data/jobhunter.yaml
cp backend/profile.example.json data/profile.json
```

- **`jobhunter.yaml`:** sin fichero en `JH_HOME` se usa `backend/defaults/jobhunter.yaml` (desarrollador genérico). En [`examples/`](examples/README.md) hay configuraciones de ejemplo (`developer`, `sap-consultant`, `data-ai`) que puedes copiar y adaptar. Un YAML inválido (pesos que no suman 1.0, id de track repetido…) impide arrancar la API y el error indica fichero, campo y motivo. Los cambios se aplican solos, sin reiniciar: si el fichero tiene un error, la API sigue con la última versión válida y lo registra en el log.
- **`profile.json`:** contiene datos personales (puedes incluir DNI/NIE y fecha de nacimiento, que usan algunos formularios de candidatura); no lo subas a ningún repositorio. Copia tus CV a `JH_HOME/cv/` con los nombres que indica el perfil.
- **Tracks aislados (trabajos puente):** más detalle en [docs/operacion.md](docs/operacion.md#tracks-aislados-trabajos-puente).

**Variables de entorno.** Se leen de `backend/.env` o de un `.env` en la raíz. Tienen prioridad sobre los ficheros.

| Variable | Para qué |
|---|---|
| `JH_HOME` | Carpeta de datos. `JH_DB_PATH`, `JH_INBOX_DIR` y `JH_PROFILE_PATH` mandan sobre ella |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | Envío por Gmail (alternativa a configurarlo en el panel) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Claves de API de IA (alternativa al llavero) |
| `SCRAPERAPI_KEY` | Clave de ScraperAPI, solo para Indeed |
| `ALLOWED_HOSTS` | Hosts que acepta la API local (por defecto `localhost,127.0.0.1`) |
| `SCRAPER_COOLDOWN_SECONDS` | Espera mínima entre ejecuciones de una misma fuente (300 s) |

Límites de operación y ajuste fino del scoring: [docs/operacion.md](docs/operacion.md).

---

## App de escritorio

Si prefieres no usar el terminal, la [app de escritorio](desktop/README.md) trae el panel, el backend y Tectonic en un instalador, y se usa como cualquier otro programa.

- **Instaladores:** Windows (`.msi`/`.exe`), macOS (`.dmg`, Apple Silicon e Intel) y Linux (`.deb`, `.AppImage`), generados por el workflow `Desktop` de GitHub Actions.
- **Tus datos** están en la carpeta de datos del sistema (`~/.local/share/jobhunter`, `%APPDATA%\jobhunter`, `~/Library/Application Support/jobhunter`), nunca en la carpeta de instalación.
- **Solo en local:** el backend incluido escucha en `127.0.0.1` en un puerto libre y mantiene las protecciones de la API descritas en [docs/adr/](docs/adr/).
- **Bajo demanda:** Chromium (relleno de formularios) se descarga la primera vez que hace falta. Ollama no va incluido: la app lo detecta y ofrece instalarlo o elegir otro proveedor de IA.
- **Sin firmar y sin actualización automática:** el sistema avisa la primera vez que la abres (la guía explica cómo continuar) y la app solo te dice cuándo hay una versión nueva.

Las compilaciones de Windows y macOS son experimentales: se generan y pasan la prueba de humo del backend, pero se han probado poco en equipos reales.

---

## Ejecución en local

En dos terminales:

```bash
# 1. API (puerto 8020)
cd backend
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8020

# 2. Panel (puerto 3010)
cd frontend
bun run dev
```

Abre `http://127.0.0.1:3010`.

La API no tiene login: solo escucha en `127.0.0.1`, comprueba el `Host` y exige la cabecera `X-JH-Client: dashboard` en las peticiones que modifican datos (si llamas con `curl` o un script, añádela). Detalle y motivos: [docs/adr/0001-proteccion-de-la-api-local.md](docs/adr/0001-proteccion-de-la-api-local.md) y [docs/operacion.md](docs/operacion.md).

---

## Primer arranque

Sin `profile.json` en la carpeta de datos, el panel abre un asistente de tres pasos en lugar de pedirte editar ficheros a mano. Si ya tienes `profile.json` pero no un `jobhunter.yaml` propio (instalación anterior), la aplicación sigue funcionando con la configuración por defecto y solo muestra un aviso descartable que abre el asistente precargado.

1. **Tu CV.** Sube un PDF o DOCX (hasta 10 MB) o rellena el formulario. El texto se extrae **en local** y el archivo se guarda en `JH_HOME/cv/`. Si hay un proveedor de IA configurado, propone un borrador de perfil a partir del texto; sin IA el borrador sale vacío y lo rellenas tú.
2. **Revisión.** Comprueba y edita lo entendido: puestos objetivo (cada uno será un track), experiencia, herramientas (palabras clave del scoring), idiomas con nivel CEFR, modalidad y ciudad, y elegibilidad (permiso de trabajo, patrocinio de visado, carnet de conducir).
3. **Dónde buscar.** Elige mercados, que sugieren fuentes (las de condiciones de uso delicadas empiezan sin marcar y exigen aceptación expresa), y opcionalmente empresas a seguir. Pulsa «Buscar ofertas».

El asistente escribe `JH_HOME/profile.json` y `JH_HOME/jobhunter.yaml` (tracks, grupos de palabras con pesos que suman 1.0 y `scoring.min_relevance` calibrado al perfil). Todo sigue siendo editable después en la pestaña **Perfil**, que también permite repetir el asistente, cambiar fuentes y configurar la IA y el SMTP. Repetir el asistente no borra nada que no pregunte: se conservan el resumen, las cartas, los otros CV y la formación del perfil, y los tracks aislados, los grupos de palabras propios, las reglas de scoring y los ajustes de cada fuente.

### Proveedores de IA

La IA es opcional y solo se usa para leer el CV, adaptar cartas (la plantilla es la alternativa) y preparar entrevistas. **El scoring nunca usa IA.** Con `none` todo funciona con formularios manuales y cartas de plantilla.

| Proveedor | Cómo se conecta | Credenciales |
|-----------|-----------------|--------------|
| `none` (por defecto) | sin IA | no aplica |
| `ollama` | HTTP local (`http://127.0.0.1:11434`), modelo por defecto `llama3.1` | ninguna, nada sale de tu equipo |
| `anthropic` | API de Anthropic, modelo por defecto `claude-sonnet-5-5` | clave de API |
| `openai` | API de OpenAI, modelo por defecto `gpt-4o-mini` | clave de API |
| `claude_cli` | tu **suscripción de Claude** mediante el CLI local `claude -p` | la sesión del propio CLI |
| `codex_cli` | tu **suscripción de ChatGPT** mediante el CLI local `codex exec` | la sesión del propio CLI |

Se elige en el asistente o en Perfil (un botón «Probar» lo comprueba). El modelo se puede cambiar con `ai.model` en `jobhunter.yaml`. Con los proveedores por CLI la aplicación no guarda credenciales de suscripción: solo comprueba que el CLI está instalado y con sesión.

**Secretos.** Las claves de API y la contraseña SMTP van al llavero del sistema operativo (vía `keyring`), nunca a `jobhunter.yaml`, `profile.json`, logs ni respuestas de la API. Las variables de entorno tienen prioridad y son la alternativa si no hay llavero (por ejemplo, Linux sin Secret Service; guardar una clave devuelve entonces un error claro).

**Privacidad.** Nada sale de tu equipo salvo las búsquedas en los portales que actives y, si eliges un proveedor en la nube (`anthropic`, `openai` o los CLI, que hablan con su fabricante), el texto que se le envía (CV, ofertas). Con `ollama` o `none` no hay tráfico de IA.

### Email (SMTP)

El envío es siempre manual y aprobado por ti. En Perfil > Email elige el preset de Gmail (`smtp.gmail.com:587`, STARTTLS, requiere [contraseña de aplicación](https://myaccount.google.com/apppasswords)) o un servidor SMTP propio (host, puerto, STARTTLS, usuario, nombre del remitente). La contraseña va al llavero; «Probar» se conecta y autentica sin enviar nada.

### Preparación de documentos y candidaturas

El botón **«Preparar candidatura»** de la tarjeta de revisión (o `POST /api/applications/{id}/prepare`) genera y compila un CV y una carta de presentación en PDF a medida de la oferta:

- **Sin IA (determinista):** genera el CV y la carta a partir de `profile.json` y la plantilla activa, recortando las viñetas menos relevantes si se desborda el límite de páginas.
- **Con IA (redactor + revisor):** un redactor adapta el resumen, las competencias y las viñetas del perfil a la oferta y un revisor critica el encaje. Un **validador de honestidad** descarta cualquier empresa, titulación, fecha o habilidad que no figure en el perfil. Si el documento desborda las páginas, se pide un recorte a la IA y, si persiste, se aplica el recorte determinista.
- **Límites y verificación:** el CV ocupa como máximo 2 páginas (configurable) y la carta 1. Se comprueba que los PDF son legibles por sistemas de selección automáticos, que contienen los datos de contacto literales (email y teléfono) y que las fechas tienen formato estándar.
- **Archivo por candidatura:** los PDF se guardan de forma atómica en `JH_HOME/applications/<id>/` (`cv.pdf`, `cover.pdf`, `job_posting.md` y `metadata.json`). Al pulsar **«Aprobar y enviar»** se adjuntan automáticamente.

#### Motor de compilación (Tectonic / LaTeX)

Para compilar las plantillas LaTeX se recomienda **Tectonic**, un motor autónomo que descarga los paquetes bajo demanda sin instalar TeX Live completo. Si no hay ningún motor en el sistema, la preparación responde con un aviso 409 que indica cómo instalarlo. Métodos de la [guía oficial](https://tectonic-typesetting.github.io/book/latest/installation/):

- **Linux / macOS (instalador oficial):** descarga el binario `tectonic` en la carpeta actual; muévelo a una carpeta del `PATH` (por ejemplo `~/.local/bin`):
  ```bash
  curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
  ```
- **macOS / Linux con Homebrew:** `brew install tectonic`
- **Arch Linux:** `sudo pacman -S tectonic`
- **Cualquier sistema con conda:** `conda install -c conda-forge tectonic`
- **Windows:** el instalador oficial de PowerShell o el binario de [GitHub Releases](https://github.com/tectonic-typesetting/tectonic/releases):
  ```powershell
  [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
  iex ((New-Object System.Net.WebClient).DownloadString('https://drop-ps1.fullyjustified.net'))
  ```
- **Desde el código (cualquier sistema):** `cargo install tectonic` (requiere Rust y las librerías de sistema de la guía oficial).

Debian y Ubuntu no tienen paquete apt `tectonic`: usa el instalador, Homebrew o conda. También se detectan `xelatex` y `lualatex` si ya están en el `PATH`.

#### Plantillas propias de CV y carta

Por defecto se usan plantillas basadas en `moderncv` (estilo banking) para el CV y `cover.cls` para la carta. Puedes registrar plantillas propias en LaTeX (`.tex.j2`) o Typst (`.typ.j2`):

- Desde el panel, en **Perfil > Plantillas**, con `POST /api/templates` o con el comando de Claude Code `/add-template`.
- Cada plantilla pasa una **compilación de prueba obligatoria** con el perfil de ejemplo (`profile.example.json`) antes de guardarse en `JH_HOME/templates/<tipo>/<nombre>/`.
- Cada plantilla elige compilador de una lista cerrada (`tectonic`, `xelatex`, `typst`) y puede fijar su límite de páginas y reglas de estilo. No hay comando de compilación libre.
- **Una plantilla puede leer ficheros de tu equipo y meterlos en el PDF que envías: instala solo plantillas de fuentes de confianza.** Registrarla exige confirmarlo expresamente. Las medidas de aislamiento (entorno Jinja aislado, escapado por defecto, compiladores sin shell-escape, xelatex con kpathsea en modo paranoico, lint de las plantillas) están en [docs/operacion.md](docs/operacion.md#plantillas-propias-seguridad).
- Si una plantilla propia falla al preparar una candidatura, el panel muestra el error con un botón para reintentar con las plantillas integradas.

---

## Idiomas

- **Interfaz:** español e inglés, con selector de idioma en la aplicación. El primer arranque sigue el idioma de tu perfil o del navegador y tu elección se recuerda.
- **Documentos:** las cartas y los seguimientos se escriben en el idioma de la oferta si hay plantilla para él y, si no, en tu idioma por defecto. El filtro de idiomas también reconoce ofertas en alemán, francés, italiano y portugués.
- **Añadir un idioma** (`de`, `fr`, `it`…) no requiere cambios en el código del núcleo: un diccionario, unas plantillas y un fichero de etiquetas. Ver [Adding a Language](CONTRIBUTING.md#adding-a-language).

---

## Fuentes de empleo

JobHunter ES cuenta con un registro extensible y autodescubierto de fuentes ([docs/sources.md](docs/sources.md)):

| Fuente | Mercados | Tipo | Requiere consentimiento (`ack`) | Atribución obligatoria | Notas |
|---|---|---|---|---|---|
| **Tecnoempleo** | España, Remoto | HTML | No | No | Filtro de provincias y ofertas en remoto. |
| **InfoJobs** | España | HTML | **Sí** | No | Requiere aceptación expresa de condiciones. Desactivada por defecto. |
| **Manfred** | España, Remoto | JSON API | No | No | Portal de empleo tech con salarios transparentes. |
| **Computrabajo** | España, LATAM | HTML | No | No | Soporte por país (`country`: `es`, `mx`, `co`, `ar`, `pe`, `cl`…) y localidades. |
| **LinkedIn** | LATAM, Remoto, Global | HTML | **Sí** | No | Requiere aceptación expresa de las condiciones de automatización. Desactivada por defecto. |
| **Remotive** | Remoto, Global | JSON API | No | **Sí** | API pública de empleo remoto. Enlaza siempre a la oferta original. |
| **RemoteOK** | Remoto, Global | JSON API | No | **Sí** | API pública de empleo remoto. Enlaza siempre a la oferta original. |
| **Arbeitnow** | Remoto, Global | JSON API | No | No | Ofertas europeas y remotas con etiquetas de visado patrocinado. |
| **Freehire** | Remoto, Global | JSON API | No | No | Puestos remotos directos y sin intermediarios. |
| **Indeed** | Global | HTML/API | No | No | Opcional, requiere `SCRAPERAPI_KEY` en el llavero o el entorno. |
| **Empresas directas** | Track directo | HTML | No | No | Webs de empleo de empresas y empresas seguidas sobre agregadores. |

### Ejecutar los scrapers

Desde el panel (botón de búsqueda) o por línea de comandos:

```bash
cd backend
source .venv/bin/activate

# Pipeline multiportal para un track estándar de jobhunter.yaml
python -m scraper.runner --track developer

# Una sola fuente: seed, tecnoempleo, indeed, manfred, contacts, generic,
# resolve-websites, linkedin-login, o "all"
python -m scraper.runner --source tecnoempleo --dry-run

# Trabajos puente del track aislado (portales: infojobs y/o indeed)
python -m scraper.runner --source generic --generic-sources infojobs,indeed
```

---

## Integración con Claude Code (opcional)

El proyecto incluye comandos y agentes para [Claude Code](https://claude.com/claude-code), portados y adaptados de [ai-job-search](https://github.com/MadsLorentzen/ai-job-search):

| Comando | Qué hace |
|---|---|
| `/apply <url\|texto>` | Flujo de dos agentes (extractor y revisor) con verificación de integridad de la oferta, extracción y redacción de CV y carta |
| `/rank` | Triage por lotes de las ofertas de la base de datos contra tu perfil |
| `/upskill` | Análisis de brechas de habilidades y plan de estudio |
| `/expand` | Descubrimiento de competencias a partir de documentos locales y GitHub |
| `/add-template` | Registro y cambio de plantillas propias |
| `/add-portal` | Generador de scrapers para portales de empleo de otros mercados |

Para el flujo completo por línea de comandos (carga, scraping, contactos, borradores, formularios y envío tras aprobación) está la skill `run-pipeline` (`.claude/skills/run-pipeline/SKILL.md`).

---

## Tests

Las suites se ejecutan sin conexión con datos de prueba neutros:

```bash
# Backend
cd backend
pytest -q
ruff check --config ../ruff.toml .

# Frontend
cd ../frontend
bun run test
bunx tsc --noEmit -p .
bun run lint

# Scripts de empaquetado de escritorio
cd ..
python -m pytest -q desktop/scripts
```

Los tests de documentos compilan PDF reales, así que necesitan un motor LaTeX y Poppler. En Debian/Ubuntu: `sudo apt-get install texlive-xetex texlive-latex-extra texlive-fonts-recommended texlive-fonts-extra poppler-utils` (la CI instala los mismos paquetes), o instala Tectonic.

---

## Estructura del proyecto

```text
jobhunter-es/
├── backend/
│   ├── main.py                 API REST con FastAPI (puerto 8020)
│   ├── config.py               Rutas (JH_HOME) y límites de operación
│   ├── search_config.py        Esquema y carga de jobhunter.yaml
│   ├── database.py             Esquema SQLite, migraciones y escrituras
│   ├── repository.py           Consultas SQL de los endpoints
│   ├── schemas.py              Modelos de la API
│   ├── defaults/               Configuración por defecto (jobhunter.yaml)
│   ├── ai/                     Proveedores de IA (Ollama, Anthropic, OpenAI, CLI)
│   ├── scraper/
│   │   ├── runner.py           CLI de los scrapers
│   │   ├── persist.py          Puntúa y guarda las ofertas
│   │   └── sources/            Registro de fuentes: un fichero por fuente
│   ├── automation/             Scoring, filtros, documentos, candidaturas, formularios, email
│   ├── templates/              Plantillas Jinja2 (cartas y seguimientos por idioma)
│   ├── scripts/                Cargadores del inbox y utilidades
│   └── tests/                  Suite de tests con datos neutros
├── frontend/                   Panel de revisión (Next.js; diccionarios es/en en lib/i18n)
├── desktop/                    App de escritorio (Tauri 2): empaquetado e instaladores
├── templates/                  Plantillas LaTeX (CV y carta) y etiquetas por idioma
├── examples/                   Configuraciones de ejemplo de jobhunter.yaml
├── seeds/                      Datos de partida (empresas con salario público)
├── docs/                       Guías, formato del inbox, fuentes y decisiones (ADR)
├── .github/workflows/          CI de tests e instaladores de escritorio
├── CONTRIBUTING.md             Guía para contribuir
├── ATTRIBUTION.md              Atribuciones de código y fuentes abiertas
├── LICENSE                     Licencia MIT
└── NOTICE                      Avisos de terceros
```

---

## Documentación adicional

- [docs/sources.md](docs/sources.md): catálogo de fuentes, parámetros y atribuciones.
- [docs/inbox.md](docs/inbox.md): formato de los ficheros del inbox.
- [docs/operacion.md](docs/operacion.md): seguridad de la API, trabajos, esquema de la base de datos y ajuste del scoring.
- [docs/adr/](docs/adr/): decisiones de arquitectura.
- [desktop/README.md](desktop/README.md): guía de la app de escritorio.

---

## Contribuir

¡Las contribuciones son bienvenidas! Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para el estilo de código, los tests y el proceso de envío.

---

## Atribuciones y licencia

Este proyecto se distribuye bajo la **licencia MIT**; ver [LICENSE](LICENSE).

Los componentes y conceptos adaptados de [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) y las fuentes abiertas (Lato, Raleway) están documentados en [ATTRIBUTION.md](ATTRIBUTION.md) y [NOTICE](NOTICE).
