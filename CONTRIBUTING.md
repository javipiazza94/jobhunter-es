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

Sources in JobHunter ES use a pluggable, self-describing registry architecture under `backend/scraper/sources/`:

1. **Create the source module:** Add `backend/scraper/sources/<id>.py` defining a `spec() -> SourceSpec` (specifying `id`, `label` in `es` and `en`, `markets`, `requires_ack`, `default_on`, `attribution`, `params`, and `run(ctx)`).
2. **Add a sample fixture:** Place mock JSON or HTML data in `backend/tests/fixtures/sources/<id>.{json,html}` with all personal information redacted.
3. **Add unit tests:** In `backend/tests/test_sources_<category>.py` (or `test_<id>.py`), test offer normalization, keyword filtering, attribution details, and error resilience without network requests.
4. **Document the source:** Add a row to `docs/sources.md` and the sources table in `README.md` and `README.es.md`.
5. The registry automatically discovers the new source module, exposing it in the runner, the CLI, the settings API, and the setup wizard without any hard-coded wiring.

### Adding an AI Provider
AI providers live in `backend/ai/` behind one interface (`Provider` in `backend/ai/base.py`: `generate_text`, `generate_json`, `check`).
1. Implement the provider in `backend/ai/` (subclass `BaseProvider` and implement `_complete` and `check`). HTTP providers use `requests`, CLI providers use `subprocess` with the prompt on stdin; no vendor SDKs. Errors must raise `AIError` and never include keys or response bodies.
2. Register it in `_PROVIDERS` inside `get_provider()` in `backend/ai/__init__.py`.
3. Add its name to the `provider` `Literal` of `AISettings` in `backend/search_config.py` (and to the TypeScript types in `frontend/lib/types.ts` and the provider selector in the frontend; `backend/tests/test_api_contract.py` guards the mirror).
4. If it needs a secret, add it to `ENV_FALLBACK` in `backend/secrets_store.py`; secrets go to the keychain, never to `jobhunter.yaml`.
5. Test it with doubles only: mock `requests` / `subprocess.run` / `shutil.which` as in `backend/tests/test_ai_providers.py`, and add the provider to the parametrized `backend/tests/test_first_run_e2e.py`. Tests must never hit the network or a real CLI.

### Adding a Language

Adding a new language (e.g. `de`, `fr`, `it`) requires **zero core code changes**:

1. **Frontend UI Dictionary:** Add `frontend/lib/i18n/<lang>.json` matching the exact key structure of `es.json` (verified automatically by `backend/tests/test_sp4_finish.py` and `frontend/lib/i18n/i18n.test.ts`).
2. **Cover Letter & Follow-up Templates:** Create Jinja2 templates under `backend/templates/<lang>/` (or in user overrides `JH_HOME/templates/<lang>/`):
   - `cover_letter_base.j2`
   - `cover_letter_tech.j2`
   - `followup.j2`
3. **LaTeX / Typst Document Labels:** Add `templates/latex/i18n/<lang>.yaml` with section headers, closing remarks, and localized date labels.
4. **Offer Language Detection:** Language screening automatically detects common European languages (`es`, `en`, `de`, `fr`, `it`, `pt`) via `backend/automation/language_detect.py` and matches candidate requirements in `language_gate.py`.

### Modifying Tracks or Scoring Rules
- Tracks and scoring criteria live exclusively in `jobhunter.yaml`.
- Core scoring logic is implemented in `backend/automation/filter_engine.py` and `backend/automation/generic_filter.py`.
- Ensure tests verify edge cases with neutral fixtures (`backend/tests/fixtures/config_test.yaml`).

### Adding and Testing Custom Templates
Custom templates for CVs and cover letters live in `JH_HOME/templates/<kind>/<name>/` and are managed via `backend/automation/templates_registry.py`:
- Supported engines: LaTeX (`.tex.j2`, compiled with Tectonic / XeLaTeX) and Typst (`.typ.j2`, compiled with `typst compile`).
- Registering a template (`POST /api/templates` or `python -m automation.templates_registry add ...`) runs a **mandatory test compilation** against `backend/profile.example.json` to verify valid syntax, macros, and page limits before activation.
- Templates must respect page limits (default: CV ≤ 2 pages, cover letter = 1 page) and use ATS-friendly text formatting without custom binary dependencies.
- The compiler comes from a closed list (`tectonic`, `xelatex`, `typst`) and its argv is built in code with safe flags; custom templates render in a sandboxed Jinja environment with escaping by default. Custom LaTeX templates use xelatex with `openin_any=p`/`openout_any=p` (never lualatex: `\directlua`), their files go to their own `custom_<kind>/` subfolder written without following symlinks (Tectonic does not confine file reads and is only a last resort, with a warning), and registration requires `trusted=true`. Keep it that way: never add a free-form compile command, `latexmk`, or shell-escape.
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
