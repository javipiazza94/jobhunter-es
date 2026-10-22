# Contributing to JobHunter ES

Thank you for considering contributing to JobHunter! We welcome community contributions to expand portal scrapers, enhance scoring accuracy, and improve local developer workflows.

---

## Development Setup

### 1. Requirements
- Python 3.11+
- Node.js 18+ and [Bun](https://bun.sh/)
- Playwright Chromium (`playwright install chromium`)
- Optional for PDF compilation: [Tectonic](https://tectonic-typesetting.github.io/)

### 2. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
```

### 3. Frontend Setup
```bash
cd frontend
bun install
```

---

## Testing & Quality Checks

Always verify that all suites pass before submitting changes:

```bash
# Backend tests & linter
cd backend
pytest -q
ruff check --config ../ruff.toml .

# Frontend tests, types & lint
cd ../frontend
bun run test
bunx tsc --noEmit -p .
bun run lint
```

---

## Adding New Features

### Adding a New Scraper Source
1. Inherit from `BaseScraper` in `backend/scraper/base.py`.
2. Implement `scrape_keyword()` respecting rate limits (`delay_min`, `delay_max`) and robots compliance (`automation/robots_check.py`).
3. Add source settings in `backend/defaults/jobhunter.yaml`.
4. Register the scraper in `backend/scraper/runner.py`.
5. Add unit and integration tests under `backend/tests/test_<source>.py`.

### Adding an AI Provider
AI providers live in `backend/ai/` behind one interface (`Provider` in `backend/ai/base.py`: `generate_text`, `generate_json`, `check`).
1. Implement the provider in `backend/ai/` (subclass `BaseProvider` and implement `_complete` and `check`). HTTP providers use `requests`, CLI providers use `subprocess` with the prompt on stdin; no vendor SDKs. Errors must raise `AIError` and never include keys or response bodies.
2. Register it in `_PROVIDERS` inside `get_provider()` in `backend/ai/__init__.py`.
3. Add its name to the `provider` `Literal` of `AISettings` in `backend/search_config.py` (and to the TypeScript types in `frontend/lib/types.ts` and the provider selector in the frontend; `backend/tests/test_api_contract.py` guards the mirror).
4. If it needs a secret, add it to `ENV_FALLBACK` in `backend/secrets_store.py`; secrets go to the keychain, never to `jobhunter.yaml`.
5. Test it with doubles only: mock `requests` / `subprocess.run` / `shutil.which` as in `backend/tests/test_ai_providers.py`, and add the provider to the parametrized `backend/tests/test_first_run_e2e.py`. Tests must never hit the network or a real CLI.

### Adding a Language

JobHunter targets the Spanish job market, but cover letters can be written in other languages:

- **Cover letter templates** live in `backend/templates/` as Jinja2 files named `cover_letter_<name>.j2`
  (`cover_letter_base.j2` is the fallback). A track selects its template with `cover_template: <name>` in
  `jobhunter.yaml`, so a language is added as a new template (e.g. `cover_letter_tech_en.j2`) plus a track
  (or an existing track) that points to it. Follow-up emails use `followup.j2`.
- Reuse the variables the existing templates receive (see `backend/automation/cover_letter.py`), and add a
  test under `backend/tests/` that renders the new template with neutral sample data.
- Offer language requirements are checked in `backend/automation/language_gate.py` against the
  `languages` declared in `profile.json` (an isolated track can also use `isolated.exclude_lang_regex`).
  Supporting a new language there means adding its name variants to that module, with tests.
- **Dashboard (UI) texts** are currently hard-coded in Spanish in the components under `frontend/app/`;
  there is no i18n layer yet. Translating the UI is future work: open a feature request first so the
  approach (library, message files) can be agreed before large changes.

### Modifying Tracks or Scoring Rules
- Tracks and scoring criteria live exclusively in `jobhunter.yaml`.
- Core scoring logic is implemented in `backend/automation/filter_engine.py` and `backend/automation/generic_filter.py`.
- Ensure tests verify edge cases with neutral fixtures (`backend/tests/fixtures/config_test.yaml`).

### Adding and Testing Custom Templates
Custom templates for CVs and cover letters live in `JH_HOME/templates/<kind>/<name>/` and are managed via `backend/automation/templates_registry.py`:
- Supported engines: LaTeX (`.tex.j2`, compiled with Tectonic / XeLaTeX) and Typst (`.typ.j2`, compiled with `typst compile`).
- Registering a template (`POST /api/templates` or `python -m automation.templates_registry add ...`) runs a **mandatory test compilation** against `backend/profile.example.json` to verify valid syntax, macros, and page limits before activation.
- Templates must respect page limits (default: CV ≤ 2 pages, cover letter = 1 page) and use ATS-friendly text formatting without custom binary dependencies.
- Unit and integration tests for template management are in `backend/tests/test_templates_registry.py`.

### Claude Code Commands and Agents
Claude Code integrations reside under `.claude/`:
- **Commands:** `.claude/commands/{apply,rank,add-template,add-portal,expand,upskill}.md`.
- **Agents:** `.claude/agents/{posting-fetcher,posting-scorer,application-reviewer}.md`.
- All commands and agents reference repository modules directly (`python -m automation.<module>`) and write to `JH_HOME`.
- Verify Claude Code contracts using `backend/tests/test_claude_commands.py`, which checks that all command files exist, referenced modules can be imported, and obsolete upstream references are absent.

---

## Pull Request Guidelines
- Keep commits focused and atomic.
- Include corresponding unit tests for new functionality or bug fixes.
- Always write tests against neutral fixtures (`config_test.yaml`), never against personal configurations.
- Ensure all CI checks pass.
- Do not commit personal data, API tokens, credentials, or private resume files.
