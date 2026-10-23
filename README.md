# JobHunter ES

**English** · [Leer en español](README.es.md)

An open-source platform for job hunting and application preparation, built for the Spanish job market and extensible to other countries. It scrapes postings from several portals, classifies them into configurable search tracks, scores their relevance, prepares tailored CVs and cover letters, and keeps a local review queue: **nothing is sent until you approve it**.

Everything runs on your machine. Your data (profile, CVs, database, applications) lives in a local folder, and AI is optional: without it the app keeps working with forms and templates.

---

## Features

- **Multi-source search:** Tecnoempleo, InfoJobs, Manfred, Computrabajo (per country), LinkedIn, Indeed, Remotive, RemoteOK, Arbeitnow, freehire and the careers pages of specific companies. A self-discovering source registry lets you add more with one file and its test. Details in [docs/sources.md](docs/sources.md).
- **Configurable search tracks and scoring:** each target role is a track with its own keyword groups, weights, and location, experience and salary rules, all defined in `jobhunter.yaml`. Scoring is deterministic and **never uses AI**.
- **Safety and eligibility filters:** detection of hidden text or instructions aimed at an AI inside postings, `robots.txt` compliance, a required-language filter and an eligibility filter (work permit, visa, residency, degree).
- **First-run wizard:** upload your CV (PDF or DOCX) or fill in a form, review what the app understood and choose where to search. It generates your profile and your configuration.
- **Human review queue:** applications are staged as drafts in a local dashboard. You edit the letter and approve or reject; only then is anything sent.
- **CV and cover letter PDFs tailored to each posting:** with AI (a writer and a reviewer, plus a validator that drops any fact not found in your profile) or without AI (from templates). PDFs are verified (page count, ATS readability, contact details) and archived per application.
- **Custom templates:** CV and cover letter in LaTeX or Typst, with a mandatory test compilation before they are activated.
- **SMTP sending with approval:** Gmail preset or your own server, a daily limit and a per-company cooldown so you do not recontact the same employer.
- **Follow-up:** reminders for applications without a reply and a status for each application.
- **Application form filling (ATS):** SuccessFactors, Workday, Greenhouse, Lever and generic forms with Playwright. **It never clicks "Submit".**
- **File inbox:** postings and applications dropped in a folder are loaded into the database automatically, so external workflows can plug in ([docs/inbox.md](docs/inbox.md)).
- **Optional AI, your choice:** Ollama (local), the Anthropic or OpenAI API, or your Claude or ChatGPT subscription through its CLI. Keys go to the system keychain.
- **Spanish and English interface**, and documents in the language of the posting when a template exists for it.
- **Desktop app** (Windows, macOS and Linux) that bundles everything in one installer.

### Known limitations

- LinkedIn and InfoJobs require you to explicitly accept their terms of use and are disabled by default.
- Form filling has been tested with SuccessFactors and generic forms; Workday, Greenhouse and Lever follow the same principle but have not been tested against a real form of each.
- The desktop installers are unsigned, and the Windows and macOS ones are experimental (see [Desktop app](#desktop-app)).

---

## How it works

```text
Job portals / companies / inbox files
                  ↓
      Safety filters (guard, robots)
                  ↓
     Scoring and classification into a track
                  ↓
     Application draft and tailored letter
                  ↓
   Local dashboard ("Pending") ──> Approve / Edit / Reject
                  ↓
        Send and archive the application
                  ↓
      Reminders and status tracking
```

---

## Tech stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11 · FastAPI · SQLite · Pydantic |
| **Scraping** | Playwright · BeautifulSoup · ScraperAPI (optional) |
| **Frontend** | Next.js · TypeScript · Tailwind CSS · Bun |
| **Documents** | Jinja2 · LaTeX (Tectonic or XeLaTeX) · Typst (optional) · pypdf · Poppler |
| **AI (optional)** | Ollama · Anthropic API · OpenAI API · Claude and Codex CLIs |
| **Email** | SMTP (app password, STARTTLS) |
| **Desktop** | Tauri 2 · PyInstaller-frozen backend · bundled Tectonic |

---

## Prerequisites

- Python 3.11 or later
- Node.js 18 or later and [Bun](https://bun.sh/)
- Playwright Chromium: `playwright install chromium`
- Optional, to compile PDFs locally: [Tectonic](https://tectonic-typesetting.github.io/) (bundled in the desktop app) or `xelatex` plus Poppler
- Optional, to build the desktop app yourself: Rust (stable) and the Tauri system libraries; see [desktop/README.md](desktop/README.md)

---

## Installation

```bash
git clone https://github.com/<your-username>/jobhunter-es.git
cd jobhunter-es

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # for development and tests: requirements-dev.txt
playwright install chromium

# Frontend
cd ../frontend
bun install
```

If you would rather not use a terminal, install the [desktop app](#desktop-app).

---

## Configuration

Everything personal lives outside the code, in the **data folder `JH_HOME`** (`./data/` by default, ignored by git; in the desktop app, the system data folder). If it does not exist, the API creates it on startup.

| File or folder | Contents |
|---|---|
| `jobhunter.yaml` | Search, scoring, tracks, sources, AI and SMTP |
| `profile.json` | Your profile: personal details, summary, experience, education, languages |
| `cv/` | Your CVs as PDF |
| `job_hunter.db` | SQLite database |
| `applications/` | Archived CV and cover letter of each application |
| `inbox/`, `backups/`, `logs/`, `sessions/` | File intake, backups, logs and sessions |

**Creating the configuration.** The simplest way is to let the [first-run wizard](#first-run) generate `profile.json` and `jobhunter.yaml`. You can also create them by hand:

```bash
mkdir -p data
cp backend/defaults/jobhunter.yaml data/jobhunter.yaml
cp backend/profile.example.json data/profile.json
```

- **`jobhunter.yaml`:** without a file in `JH_HOME`, `backend/defaults/jobhunter.yaml` (generic developer) is used. [`examples/`](examples/README.md) has sample configurations (`developer`, `sap-consultant`, `data-ai`) you can copy and adapt. An invalid YAML (weights that do not sum to 1.0, a duplicated track id…) prevents the API from starting, and the error names the file, field and reason. Changes are picked up without a restart: if the file has an error, the API keeps running on the last valid version and logs it.
- **`profile.json`:** holds personal data (you may include your national ID and date of birth, which some application forms use); do not commit it to any repository. Copy your CVs to `JH_HOME/cv/` using the names the profile specifies.
- **Isolated tracks (bridge jobs):** more detail in [docs/operations.md](docs/operations.md#isolated-tracks-bridge-jobs).

**Environment variables.** They are read from `backend/.env` or from a `.env` at the repository root, and take precedence over the files.

| Variable | Purpose |
|---|---|
| `JH_HOME` | Data folder. `JH_DB_PATH`, `JH_INBOX_DIR` and `JH_PROFILE_PATH` override it |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | Sending through Gmail (alternative to configuring it in the dashboard) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | AI API keys (alternative to the keychain) |
| `SCRAPERAPI_KEY` | ScraperAPI key, only for Indeed |
| `ALLOWED_HOSTS` | Hosts the local API accepts (`localhost,127.0.0.1` by default) |
| `SCRAPER_COOLDOWN_SECONDS` | Minimum wait between runs of the same source (300 s) |

Operating limits and scoring fine-tuning: [docs/operations.md](docs/operations.md).

---

## Desktop app

If you would rather not use a terminal, the [desktop app](desktop/README.md) bundles the dashboard, the backend and Tectonic in one installer and runs like any other program.

- **Installers:** Windows (`.msi`/`.exe`), macOS (`.dmg`, Apple Silicon and Intel) and Linux (`.deb`, `.AppImage`), built by the `Desktop` GitHub Actions workflow.
- **Your data** is in the system data folder (`~/.local/share/jobhunter`, `%APPDATA%\jobhunter`, `~/Library/Application Support/jobhunter`), never in the install folder.
- **Local only:** the bundled backend listens on `127.0.0.1` on a free port and keeps the API protections described in [docs/adr/](docs/adr/).
- **On demand:** Chromium (form filling) is downloaded the first time it is needed. Ollama is not bundled: the app detects it and offers to install it or to choose another AI provider.
- **Unsigned, no auto-update:** the system warns you the first time you open it (the guide explains how to proceed) and the app only tells you when a newer version exists.

The Windows and macOS builds are experimental: they are produced and pass the backend smoke test, but have had little testing on real machines.

---

## Running locally

In two terminals:

```bash
# 1. API (port 8020)
cd backend
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8020

# 2. Dashboard (port 3010)
cd frontend
bun run dev
```

Open `http://127.0.0.1:3010`.

The API has no login: it only listens on `127.0.0.1`, checks the `Host` header and requires the `X-JH-Client: dashboard` header on requests that modify data (add it if you call the API with `curl` or a script). Details and reasoning: [docs/adr/0001-proteccion-de-la-api-local.md](docs/adr/0001-proteccion-de-la-api-local.md) and [docs/operations.md](docs/operations.md).

---

## First run

Without a `profile.json` in the data folder, the dashboard opens a three-step wizard instead of asking you to edit files by hand. If you already have a `profile.json` but no `jobhunter.yaml` of your own (an older install), the app keeps working with the default configuration and only shows a dismissible banner that opens the wizard prefilled.

1. **Your CV.** Upload a PDF or DOCX (up to 10 MB) or fill in the form. The text is extracted **locally** and the file is stored in `JH_HOME/cv/`. If an AI provider is configured it proposes a draft profile from the text; without AI the draft is empty and you fill it in.
2. **Review.** Check and edit what was understood: target roles (each becomes a track), experience, tools (scoring keywords), languages with CEFR level, work modality and city, and eligibility (work permit, visa sponsorship, driving licence).
3. **Where to search.** Pick markets, which suggest sources (those with delicate terms of use start unchecked and need an explicit acknowledgement), and optionally companies to follow. Press "Search offers".

The wizard writes `JH_HOME/profile.json` and `JH_HOME/jobhunter.yaml` (tracks, keyword groups with weights summing to 1.0, and a `scoring.min_relevance` calibrated to the profile). Everything stays editable afterwards in the **Profile** tab, which also lets you re-run the wizard, change sources and configure AI and SMTP. Re-running the wizard never drops what it does not ask about: your summary, cover letters, other CVs and education stay in the profile, and your isolated tracks, own keyword groups, scoring rules and per-source settings stay in `jobhunter.yaml`.

### AI providers

AI is optional and only used to read the CV, adapt cover letters (the template is the fallback) and prepare interview packs. **Scoring never uses AI.** With `none` everything works with manual forms and template letters.

| Provider | How it connects | Credentials |
|----------|-----------------|-------------|
| `none` (default) | no AI | n/a |
| `ollama` | local HTTP (`http://127.0.0.1:11434`), default model `llama3.1` | none, nothing leaves your machine |
| `anthropic` | Anthropic API, default model `claude-sonnet-5-5` | API key |
| `openai` | OpenAI API, default model `gpt-4o-mini` | API key |
| `claude_cli` | your **Claude subscription** through the local `claude -p` CLI | the CLI's own login |
| `codex_cli` | your **ChatGPT subscription** through the local `codex exec` CLI | the CLI's own login |

Choose it in the wizard or in Profile (a "Test" button checks it). The model can be overridden with `ai.model` in `jobhunter.yaml`. With the CLI providers the app never stores subscription credentials: it only checks that the CLI is installed and logged in.

**Secrets.** API keys and the SMTP password go to the operating system keychain (via `keyring`), never to `jobhunter.yaml`, `profile.json`, logs or API responses. Environment variables take precedence and are the fallback when no keychain is available (for example headless Linux without a Secret Service; saving a key then returns a clear error).

**Privacy.** Nothing leaves your machine except the searches on the job portals you enable and, if you pick a cloud provider (`anthropic`, `openai`, or the CLIs, which talk to their vendor), the text sent to it (CV, postings). With `ollama` or `none` there is no AI traffic.

### Email (SMTP)

Sending is always manual and approved by you. In Profile > Email choose the Gmail preset (`smtp.gmail.com:587`, STARTTLS, needs an [app password](https://myaccount.google.com/apppasswords)) or your own SMTP server (host, port, STARTTLS, username, sender name). The password goes to the keychain; "Test" connects and authenticates without sending anything.

### Document and application preparation

The **"Prepare application"** button on the review card (or `POST /api/applications/{id}/prepare`) generates and compiles a CV and a cover letter as PDFs tailored to the posting:

- **Without AI (deterministic):** builds the CV and letter from `profile.json` and the active template, trimming the least relevant bullets if the page limit is exceeded.
- **With AI (writer + reviewer):** a writer adapts the summary, competencies and bullets of your profile to the posting and a reviewer critiques the match. An **honesty validator** drops any employer, degree, date or skill that is not in the profile. If a document overflows its pages the AI is asked to shorten it and, if that fails, deterministic trimming is applied.
- **Limits and verification:** the CV takes at most 2 pages (configurable) and the letter 1. The PDFs are checked for ATS readability, for the literal contact details (email and phone) and for standard date formats.
- **Per-application archive:** PDFs are saved atomically in `JH_HOME/applications/<id>/` (`cv.pdf`, `cover.pdf`, `job_posting.md` and `metadata.json`). **"Approve and send"** attaches them automatically.

#### Compilation engine (Tectonic / LaTeX)

To compile LaTeX templates, **Tectonic** is recommended: a self-contained engine that fetches packages on demand without a full TeX Live install. If no engine is found on the system, preparation returns a 409 with instructions on how to install one. Methods from the [official guide](https://tectonic-typesetting.github.io/book/latest/installation/):

- **Linux / macOS (official installer):** downloads the `tectonic` binary into the current directory; move it to a folder on your `PATH` (for example `~/.local/bin`):
  ```bash
  curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
  ```
- **macOS / Linux with Homebrew:** `brew install tectonic`
- **Arch Linux:** `sudo pacman -S tectonic`
- **Any OS with conda:** `conda install -c conda-forge tectonic`
- **Windows:** the official PowerShell installer or the binary from [GitHub Releases](https://github.com/tectonic-typesetting/tectonic/releases):
  ```powershell
  [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
  iex ((New-Object System.Net.WebClient).DownloadString('https://drop-ps1.fullyjustified.net'))
  ```
- **From source (any OS):** `cargo install tectonic` (needs Rust and the system libraries from the official guide).

Debian and Ubuntu have no `tectonic` apt package: use the installer, Homebrew or conda. `xelatex` and `lualatex` are also detected if they are already on your `PATH`.

#### Custom CV and cover letter templates

By default the CV uses a `moderncv` template (banking style) and the letter uses `cover.cls`. You can register your own templates in LaTeX (`.tex.j2`) or Typst (`.typ.j2`):

- From the dashboard in **Profile > Templates**, with `POST /api/templates`, or with the Claude Code command `/add-template`.
- Every template passes a **mandatory test compilation** against the sample profile (`profile.example.json`) before it is saved to `JH_HOME/templates/<kind>/<name>/`.
- Each template picks a compiler from a closed list (`tectonic`, `xelatex`, `typst`) and may set its own page limit and style rules. There is no free-form compile command.
- **A template can read files on your computer and put them in the PDF you send: install only templates from sources you trust.** Registering one requires an explicit confirmation. The isolation measures (sandboxed Jinja environment, escaping by default, compilers without shell-escape, xelatex with kpathsea in paranoid mode, template lint) are described in [docs/operations.md](docs/operations.md#custom-templates-security).
- If a custom template fails while preparing an application, the dashboard shows the error with a button to retry using the built-in templates.

---

## Languages

- **Interface:** Spanish and English, with a language selector in the app. The first launch follows your profile or browser language, and your choice is remembered.
- **Documents:** cover letters and follow-ups are written in the language of the posting if a template exists for it and otherwise in your default language. The language filter also recognises postings in German, French, Italian and Portuguese.
- **Adding a language** (`de`, `fr`, `it`…) needs no changes to the core code: a dictionary, a few templates and a labels file. See [Adding a Language](CONTRIBUTING.md#adding-a-language).

---

## Job sources

JobHunter ES has an extensible, self-discovering source registry ([docs/sources.md](docs/sources.md)):

| Source | Markets | Type | Requires consent (`ack`) | Attribution required | Notes |
|---|---|---|---|---|---|
| **Tecnoempleo** | Spain, Remote | HTML | No | No | Province filter and remote postings. |
| **InfoJobs** | Spain | HTML | **Yes** | No | Requires explicit acceptance of the terms of use. Disabled by default. |
| **Manfred** | Spain, Remote | JSON API | No | No | Tech job board with transparent salaries. |
| **Computrabajo** | Spain, LATAM | HTML | No | No | Per-country support (`country`: `es`, `mx`, `co`, `ar`, `pe`, `cl`…) and locations. |
| **LinkedIn** | LATAM, Remote, Global | HTML | **Yes** | No | Requires explicit acceptance of the automation terms. Disabled by default. |
| **Remotive** | Remote, Global | JSON API | No | **Yes** | Public remote jobs API. Always links to the original posting. |
| **RemoteOK** | Remote, Global | JSON API | No | **Yes** | Public remote jobs API. Always links to the original posting. |
| **Arbeitnow** | Remote, Global | JSON API | No | No | European and remote postings with visa sponsorship tags. |
| **Freehire** | Remote, Global | JSON API | No | No | Direct remote jobs with no intermediaries. |
| **Indeed** | Global | HTML/API | No | No | Optional, requires `SCRAPERAPI_KEY` in the keychain or the environment. |
| **Direct companies** | Direct track | HTML | No | No | Company careers pages and followed companies, ahead of aggregators. |

### Running the scrapers

From the dashboard (search button) or the command line:

```bash
cd backend
source .venv/bin/activate

# Multi-portal pipeline for one standard track of jobhunter.yaml
python -m scraper.runner --track developer

# A single source: seed, tecnoempleo, indeed, manfred, contacts, generic,
# resolve-websites, linkedin-login, or "all"
python -m scraper.runner --source tecnoempleo --dry-run

# Bridge jobs of the isolated track (portals: infojobs and/or indeed)
python -m scraper.runner --source generic --generic-sources infojobs,indeed
```

---

## Claude Code integration (optional)

The project ships commands and agents for [Claude Code](https://claude.com/claude-code), ported and adapted from [ai-job-search](https://github.com/MadsLorentzen/ai-job-search):

| Command | What it does |
|---|---|
| `/apply <url\|text>` | Two-agent flow (extractor and reviewer) with a posting integrity check, extraction, and CV and letter drafting |
| `/rank` | Batch triage of the postings in the database against your profile |
| `/upskill` | Skill-gap analysis and study plan |
| `/expand` | Skill discovery from local documents and GitHub |
| `/add-template` | Registers and switches custom templates |
| `/add-portal` | Scraper generator for job portals in other markets |

For the full command-line flow (load, scrape, contacts, drafts, forms and sending after approval) there is the `run-pipeline` skill (`.claude/skills/run-pipeline/SKILL.md`).

---

## Tests

The suites run offline with neutral test data:

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

# Desktop packaging scripts
cd ..
python -m pytest -q desktop/scripts
```

The document tests compile real PDFs, so they need a LaTeX engine and Poppler. On Debian/Ubuntu: `sudo apt-get install texlive-xetex texlive-latex-extra texlive-fonts-recommended texlive-fonts-extra poppler-utils` (CI installs the same packages), or install Tectonic.

---

## Project structure

```text
jobhunter-es/
├── backend/
│   ├── main.py                 FastAPI REST API (port 8020)
│   ├── config.py               Paths (JH_HOME) and operating limits
│   ├── search_config.py        Schema and loading of jobhunter.yaml
│   ├── database.py             SQLite schema, migrations and writes
│   ├── repository.py           SQL queries behind the endpoints
│   ├── schemas.py              API models
│   ├── defaults/               Default configuration (jobhunter.yaml)
│   ├── ai/                     AI providers (Ollama, Anthropic, OpenAI, CLIs)
│   ├── scraper/
│   │   ├── runner.py           Scraper CLI
│   │   ├── persist.py          Scores and stores postings
│   │   └── sources/            Source registry: one file per source
│   ├── automation/             Scoring, filters, documents, applications, forms, email
│   ├── templates/              Jinja2 templates (letters and follow-ups per language)
│   ├── scripts/                Inbox loaders and utilities
│   └── tests/                  Test suite with neutral data
├── frontend/                   Review dashboard (Next.js; es/en dictionaries in lib/i18n)
├── desktop/                    Desktop app (Tauri 2): packaging and installers
├── templates/                  LaTeX templates (CV and letter) and per-language labels
├── examples/                   Sample jobhunter.yaml configurations
├── seeds/                      Starter data (companies with public salaries)
├── docs/                       Guides, inbox format, sources and decisions (ADRs)
├── .github/workflows/          Test CI and desktop installers
├── CONTRIBUTING.md             Contributor guide
├── ATTRIBUTION.md              Code and open-source attributions
├── LICENSE                     MIT license
└── NOTICE                      Third-party notices
```

---

## Further documentation

- [docs/sources.md](docs/sources.md): source catalogue, parameters and attributions.
- [docs/inbox.md](docs/inbox.md): format of the inbox files.
- [docs/operations.md](docs/operations.md): API security, jobs, database schema and scoring tuning.
- [docs/adr/](docs/adr/): architecture decisions.
- [desktop/README.md](desktop/README.md): desktop app guide.

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for code style, testing and the submission process.

---

## Attributions and license

This project is distributed under the **MIT License**; see [LICENSE](LICENSE).

Components and concepts adapted from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) and the open fonts (Lato, Raleway) are documented in [ATTRIBUTION.md](ATTRIBUTION.md) and [NOTICE](NOTICE).
