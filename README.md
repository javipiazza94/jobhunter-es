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
Customize `data/jobhunter.yaml` to define your target city, keyword groups, and tracks. Customize `data/profile.json` with your experience, contact information, and resume paths.

---

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
