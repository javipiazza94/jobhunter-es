# JobHunter ES

**English** · [Leer en Español](README.es.md)

An open-source job application automation and review platform tailored for the Spanish job market. Scrapes job postings across multiple portals, classifies offers into configurable tracks, scores relevance, prepares customized resumes and cover letters, and maintains a local human-in-the-loop approval workflow.

---

## Architecture & Workflow

```text
Job Portals / Direct Companies / Inbox Files
                     ↓
             Posting Guard & Robots
                     ↓
       Score Offer & Classify Track
                     ↓
      Draft Application & Cover Letter
                     ↓
    Local Dashboard ("Pending Review")  ──>  Approve / Edit / Reject
                     ↓
          Send & Archive Application
                     ↓
       Follow-up Reminders & Status Tracking
```

1. **Scraping & Ingestion:** Multi-source scrapers (InfoJobs, Indeed, Tecnoempleo, LinkedIn, direct company portals) plus flat-file inbox intake (`docs/inbox.md`).
2. **Safety & Screening:** Automated prompt injection protection (`posting_guard.py`), `robots.txt` compliance, eligibility gate (visas, work permits), and language screening.
3. **Scoring & Tracks:** Fully configurable scoring engine (`jobhunter.yaml`) with weighted keyword groups, location rules, experience levels, and salary expectations.
4. **Human Review Queue:** Applications are staged in a local web dashboard (`status=pending_approval`). Nothing is sent automatically without explicit user review.
5. **Deterministic Document Generation:** Tailored LaTeX/Jinja2 cover letters compiled via Tectonic/LaTeX, PDF layout verification, and permanent local application archiving (`data/applications/<id>/`).

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11 · FastAPI · SQLite · Pydantic |
| **Scraping** | Playwright (stealth) · BeautifulSoup · ScraperAPI (optional) |
| **Frontend** | Next.js · TypeScript · Tailwind CSS · Bun |
| **Documents** | Jinja2 · LaTeX / Tectonic · PyMuPDF (`fitz`) |
| **Email** | SMTP (App Password / TLS) |

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** and **[Bun](https://bun.sh/)**
- **Playwright Chromium:** `playwright install chromium`
- Optional for local PDF compilation: **[Tectonic](https://tectonic-typesetting.github.io/)**

---

## Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/jobhunter-es.git
cd jobhunter-es
```

### 2. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # For development/tests: pip install -r requirements-dev.txt
playwright install chromium
```

### 3. Frontend Setup
```bash
cd ../frontend
bun install
```

### 4. Configuration
Create your personal configuration file from the default template:
```bash
mkdir -p data
cp backend/defaults/jobhunter.yaml data/jobhunter.yaml
cp backend/profile.example.json data/profile.json
```
(Optional: skip this step and let the first-run wizard create both files; see [First run](#first-run).) Customize `data/jobhunter.yaml` to define your target city, keyword groups, and tracks. Customize `data/profile.json` with your experience, contact information, and resume paths.

---

## Desktop app

If you'd rather not use a terminal, the [desktop app](desktop/README.md) bundles the dashboard, the backend and Tectonic in one installer (Windows, macOS, Linux). Your data lives in the system data folder. Installers are unsigned; the guide explains the first-launch warnings.

## Running Locally

In separate terminal tabs:

```bash
# 1. Start the Backend API (port 8020)
cd backend
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8020

# 2. Start the Frontend Dashboard (port 3010)
cd frontend
bun run dev
```

Visit the dashboard at `http://127.0.0.1:3010`.

---

## First run

Without a `profile.json` in the data folder (`JH_HOME`, `./data/` by default) the dashboard opens a three-step wizard instead of asking you to edit files by hand. If you already have `profile.json` but no `jobhunter.yaml` of your own (an older install), the app keeps working with the default configuration and only shows a dismissible banner, "Configura tu búsqueda con el asistente", that opens the wizard prefilled and cancellable:

1. **Your CV.** Upload a PDF or DOCX (up to 10 MB) or fill the form manually. The text is extracted **locally**; the file is stored in `JH_HOME/cv/`. If an AI provider is configured it proposes a draft profile from that text; without AI the draft is empty and you fill it in.
2. **Review.** Check and edit what was understood: target roles (each becomes a track), experience, tools (scoring keywords), languages with CEFR level, modality and city, and eligibility (work permit, visa sponsorship, driving licence).
3. **Where to search.** Pick markets, which suggest sources (sources with delicate terms of use start unchecked and need an explicit acknowledgement), and optionally followed companies. Then press "Search offers".

The wizard writes `JH_HOME/profile.json` and `JH_HOME/jobhunter.yaml` (tracks, keyword groups with weights summing to 1.0, `scoring.min_relevance` calibrated to the profile). Everything stays editable later in the **Perfil** tab, which also lets you re-run the wizard, change sources, and set the AI provider and SMTP. Re-running the wizard never drops what it does not ask about: the profile keeps your summary, cover letters, other CVs, education, etc.; `jobhunter.yaml` keeps isolated tracks, your own keyword groups, scoring rules and per-source settings (only standard tracks and their keyword groups are regenerated).

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

Choose it in the wizard or in Perfil (a "Test" button checks it). The model can be overridden with `ai.model` in `jobhunter.yaml`. For the CLI providers the app never stores subscription credentials: it only checks the CLI is installed and logged in.

**Secrets.** API keys and the SMTP password are stored in the operating system keychain (via `keyring`), never in `jobhunter.yaml`, `profile.json`, logs or API responses. Environment variables take precedence and are the fallback when no keychain is available (for example headless Linux without a Secret Service; saving a key then returns a clear error): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GMAIL_APP_PASSWORD` (plus `GMAIL_USER`).

**Privacy.** Nothing leaves your machine except the searches on the job portals you enable and, if you pick a cloud provider (`anthropic`, `openai`, or the CLIs, which talk to their vendor), the text sent to it (CV, offers). With `ollama` or `none` there is no AI traffic at all.

### Email (SMTP)

Sending is always manual and approved by you. In Perfil > Email choose the Gmail preset (`smtp.gmail.com:587`, STARTTLS, needs an app password) or a custom SMTP server (host, port, STARTTLS, username, sender name). The password goes to the keychain; "Test" connects and authenticates without sending anything. An install without an `email:` section keeps working as before with `GMAIL_USER` and `GMAIL_APP_PASSWORD`.

### Document & Application Preparation

The **"Preparar candidatura"** button in the dashboard (or `POST /api/applications/{id}/prepare`) generates and compiles a customized CV and cover letter in PDF tailored to the job offer:

- **Without AI (Deterministic):** Generates the CV and cover letter from `profile.json` and the active template, trimming the least relevant experience bullets if content overflows the page limits.
- **With AI (Writer + Reviewer):** When an AI provider is configured, a writer adapts the profile summary, competencies, and achievements to align with the offer, while a reviewer critiques the match. A strict **honesty validator** strips any unbacked employers, degrees, dates, or skills not found in the profile. If documents overflow page limits, the AI is asked to shorten them, falling back to deterministic trimming if necessary.
- **Limits & Verification:** The CV fits within 2 pages (configurable) and the cover letter is strictly 1 page. All generated PDFs pass `verify_pdf` ensuring ATS-readability, exact literal contact details (email and phone), and standard ASCII dates.
- **Per-Application Archive:** Output PDFs are atomically archived in `JH_HOME/applications/<id>/` (`cv.pdf`, `cover.pdf`, `job_posting.md`, and `metadata.json`). Approving an application automatically attaches these archived PDFs to the email.

#### PDF Compilation Engine (Tectonic / LaTeX)

To compile LaTeX templates to PDF, **Tectonic** is recommended (a modern, self-contained engine that fetches necessary packages on demand without requiring a full TeX Live install). If no engine is found on the system, preparation returns a 409 status with installation instructions:

Installation methods from the [official guide](https://tectonic-typesetting.github.io/book/latest/installation/):

- **Linux / macOS (official installer):** downloads the prebuilt `tectonic` binary into the current directory; move it to a folder on your `PATH` (e.g. `~/.local/bin`):
  ```bash
  curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
  ```
- **macOS / Linux with Homebrew:** `brew install tectonic`
- **Arch Linux:** `sudo pacman -S tectonic`
- **Any OS with conda:** `conda install -c conda-forge tectonic`
- **Windows:** the official PowerShell installer or the prebuilt binary from [GitHub Releases](https://github.com/tectonic-typesetting/tectonic/releases):
  ```powershell
  [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
  iex ((New-Object System.Net.WebClient).DownloadString('https://drop-ps1.fullyjustified.net'))
  ```
- **From source (any OS):** `cargo install tectonic` (needs a Rust toolchain plus the system libraries listed in the official guide).

Debian/Ubuntu have no `tectonic` apt package: use the installer, Homebrew or conda.

*Note:* Standard system engines like `xelatex` or `lualatex` are also detected and supported if present on your `PATH`.

#### Custom CV & Cover Letter Templates

JobHunter provides built-in templates based on `moderncv` (banking) for CVs and `cover.cls` for cover letters. You can register custom templates in LaTeX (`.tex.j2`) or Typst (`.typ.j2`):
- From the dashboard in **Perfil > Plantillas**.
- Via the API with `POST /api/templates` or the Claude Code command `/add-template`.
- Every registered template undergoes a **mandatory test compilation** against `profile.example.json` to verify correctness before being saved to `JH_HOME/templates/<kind>/<name>/`.
- Each template picks a compiler from a fixed list (`tectonic`, `xelatex`, `typst`) and may set its own page limit and style rules (passed to the AI writer as formatting guidance). There is no free-form compile command.
- **A template can read files on your computer and put them in the PDF you send: install only templates from sources you trust.** Registering one requires an explicit confirmation (`trusted`; a checkbox in the dashboard, `--trusted` in the CLI). As a safety net, custom templates render in a sandboxed Jinja environment, every `((( value )))` is escaped by default (`|safe_raw` opts out), and compilers run without shell-escape. For custom LaTeX templates xelatex is preferred and runs with kpathsea in paranoid mode (`openin_any=p`, `openout_any=p`: no absolute or `..` paths); lualatex is not used for them (`\directlua` reads files outside kpathsea); **Tectonic does not confine file reads**, so it is used for custom templates only when xelatex is not installed, and "Prepare application" then warns about it. A custom template's files are copied into their own subfolder without following symlinks and cannot use the built-ins' reserved names (`cover.cls`, `OpenFonts/`...); rendering is capped in size and time. Typst runs with `--root` on the work folder. `latexmkrc`/`texmf.cnf` files are dropped, and a best-effort lint over every text file of the template rejects `\input`/`\include`/`\openin`/`\read`/`\includegraphics`... with absolute, `~` or `..` paths, `\@@input`, `\let` aliases and macro-built paths of read commands, `\directlua`/`luacode`, `\write18`, `\catcode` changes and `\csname`-built read commands (it is not a complete barrier).
- If a custom template fails while preparing an application, the error is shown with a one-click retry using the built-in templates.

---

## Running Scrapers

Search across portals using your configured tracks:

```bash
cd backend
source .venv/bin/activate

# Multi-portal pipeline for one standard track of jobhunter.yaml
# (Tecnoempleo, InfoJobs, Computrabajo, direct company portals, LinkedIn)
python -m scraper.runner --track developer

# A single source: seed, tecnoempleo, indeed, manfred, contacts, generic,
# resolve-websites, linkedin-login, or "all" (seed + tecnoempleo + indeed + manfred + contacts)
python -m scraper.runner --source tecnoempleo --dry-run

# Bridge jobs for the isolated track (portals: infojobs and/or indeed)
python -m scraper.runner --source generic --generic-sources infojobs,indeed
```

---

## Running Tests

All test suites can be executed completely offline using mock fixtures:

```bash
# Backend pytest suite
cd backend
pytest -q

# Backend code formatting & linter
ruff check --config ../ruff.toml .

# Frontend tests (Bun test runner)
cd ../frontend
bun run test
bunx tsc --noEmit -p .
bun run lint
```

---

## Project Structure

```text
jobhunter-es/
├── backend/
│   ├── automation/         # Scoring, document generator, gates, guard
│   ├── defaults/           # Default jobhunter.yaml configuration
│   ├── scraper/            # Portal scrapers (InfoJobs, Indeed, Tecnoempleo...)
│   ├── templates/          # Jinja2 and LaTeX templates
│   ├── tests/              # Comprehensive test suite with neutral fixtures
│   └── main.py             # FastAPI backend application
├── frontend/               # Next.js review and management dashboard
├── docs/                   # Guides, inbox sync format, and ADRs
├── seeds/                  # Seed datasets (e.g. companies with public salaries)
├── scripts/                # Helper utilities and data loaders
├── CONTRIBUTING.md         # Guidelines for contributors
├── ATTRIBUTION.md          # Upstream open-source attribution details
├── LICENSE                 # MIT License
└── NOTICE                  # Third-party notices and licenses
```

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on code style, testing requirements, and submission processes.

---

## Attributions & License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

Components and concepts adapted from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) and open fonts (Lato, Raleway) are documented in [ATTRIBUTION.md](ATTRIBUTION.md) and [NOTICE](NOTICE).
