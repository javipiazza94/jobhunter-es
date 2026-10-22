# SP4 — International · Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The whole UI switches es↔en with no stray strings; cover letters/follow-ups/LaTeX documents come in the offer's language when a template exists; sources are self-describing plugins (registry) with new remote sources, Computrabajo per country, followed companies over aggregators and robots.txt respected; adding a language or a source needs no core changes.

**Architecture:** Backend: `backend/scraper/sources/` package with one module per source declaring a `SourceSpec` (auto-discovered registry) that wraps the existing scraper code; runner, job API, wizard markets and settings read the registry. Language: a small offer-language detector, per-language templates under `backend/templates/<lang>/` and `templates/latex/i18n/<lang>.yaml`. Frontend: JSON dictionaries `frontend/lib/i18n/<lang>.json`, a tiny `t()`/`useT()` layer (no new deps), language selector persisted per viewer and in the profile.

**Tech Stack:** FastAPI, Playwright scrapers, `requests` JSON APIs, Jinja2, Next.js 16 / React 19, bun test (happy-dom).

**Spec (summary of the private design doc, binding):** UI: dictionaries `frontend/lib/i18n/{es,en}.json`, no new dependencies; language selector in the app; texts out of the code. Letter and follow-up templates per language (`templates/{es,en}/`); the letter comes out in the offer's language if there is a template for it, otherwise the user's default language. Adding a language (de, fr, it…) = translating the JSON and templates, no code; explained in CONTRIBUTING. `language_gate` and `posting_guard` understand es and en; their language lists cover de/fr/it. Sources: each source is a module in `backend/scraper/sources/` declaring `id`, markets, whether it requires accepting terms (`requires_ack`), whether it is on by default, its parameters (keywords, locations, country) and how to attribute the offer (source name and link). The registry is discovered automatically; runner, API and wizard read from it. Adding a source = one file + its test with sample data + one line of docs. v1 sources — Spain: Tecnoempleo, InfoJobs (`requires_ack`, off by default), Manfred. Latin America: Computrabajo per country (`mx`, `co`, `ar`, `pe`, `cl` and those its site supports). Remote: Remotive, RemoteOK, Arbeitnow and freehire via JSON API; Remotive and RemoteOK require showing the source name and linking to the offer: the UI always shows source and link. Global: LinkedIn (`requires_ack`, off by default) and Indeed (optional with the user's own ScraperAPI key, off without it). Followed companies (Adecco, Manpower or user-added): filter by company over the aggregators, without scraping their sites. Current sources not in the list: `company_direct` (configurable company list), EY careers, Computrabajo Spain and company seeds are published generalised; the runner's `generic` step feeds the isolated track. Common robots.txt helper (`robots_check`/`fetch_page`) for HTML sources; single exception: a `requires_ack` source whose robots forbids it (LinkedIn) runs only if the user enables it and accepts an explicit warning naming that it breaks the site's terms; the acceptance is stored in their config. `posting_guard` and `language_gate` apply to all via `offer_review`. Finish line: whole UI switches es↔en without stray texts; every source has its test with sample data; adding a test language requires no code.

## Global Constraints

- Work in `jobhunter-es`; invented data in tests; sample data files for sources live in `backend/tests/fixtures/sources/<id>.{json,html}` (hand-written or trimmed real responses with personal data removed).
- **Existing installs unchanged:** source ids `tecnoempleo`, `infojobs`, `computrabajo`, `manfred`, `linkedin`, `indeed`, `company_direct`, `generic`, `seed`, `contacts`, `inbox`, `inbox-apply` keep working from CLI (`python -m scraper.runner --track/--source`, `python -m scraper.jobs <id>`) and API with the same `sources:` config keys; Computrabajo without `country` = Spain; scoring results unchanged; DB `source` values for existing sources unchanged.
- New sources default **off** for existing configs (only the wizard enables them by market).
- No network in tests. JSON sources use `requests` with timeout and a descriptive User-Agent; respect documented rate limits; HTML/Playwright sources check `robots_check.gate(start_url)` first (LinkedIn exempt only when acknowledged).
- Frontend: no new runtime deps; every visible string through `t()`; es and en dictionaries with identical key sets (test); dates via `Intl` with the active locale.
- Backend user-facing errors: keep Spanish `detail` but add a stable `code` to HTTPExceptions the UI shows; the UI translates known codes and falls back to `detail`.
- Suites green each commit: backend `pytest -q` + `ruff check --config ../ruff.toml .`; frontend `bun test`, `bun run lint`, `bun node_modules/typescript/bin/tsc --noEmit -p .`; contract test green.
- Spanish docstrings, English identifiers, Spanish commits; MIT attribution kept.

## Review Focus

1. A Javi-like existing config (tracks with tecnoempleo/infojobs/computrabajo/linkedin/company_direct settings, no `country`) produces the same scraper calls (URLs/params) before and after the registry refactor.
2. A remote JSON API returning unexpected shapes, HTTP 429/5xx or HTML error pages must not crash the run; partial results kept, error logged per source.
3. Switching to English leaves no Spanish text visible in any tab, panel, wizard step, empty state or error toast (except user data and offer text).
4. An offer in German with only es/en templates → letter in the user's default language, never a broken/empty template.
5. robots.txt disallowing a source → the source is skipped with a visible reason, never silently scraped.

---

### Task 1: Source registry (refactor, no behaviour change)

**Files:** Create `backend/scraper/sources/__init__.py` (registry), `backend/scraper/sources/{tecnoempleo,infojobs,computrabajo,manfred,linkedin,indeed,company_direct}.py` (thin adapters over existing scrapers); Modify `backend/scraper/jobs.py`, `backend/scraper/runner.py`, `backend/setup_builder.py`, `backend/defaults/markets.yaml` (generated view or removed in favour of specs), `backend/main.py` (`/api/setup/markets`, `/api/settings/sources`, `/api/scraper/run` validation); Tests `backend/tests/test_source_registry.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) SourceSpec`: `id: str`, `label: dict[str, str]` (es/en), `markets: tuple[str, ...]` (subset of `spain|latam|remote|global`), `requires_ack: bool`, `default_on: bool`, `kind: Literal["json","html","playwright"]`, `start_url: str | None` (robots check), `attribution: Attribution(name: str, url: str, required: bool)`, `params: dict[str, ParamSpec]` (name → type/default/help), `track_pipeline: bool` (runs inside `--track`), `requires_secret: str | None` (e.g. `SCRAPERAPI_KEY`), `run: Callable[[RunContext], Awaitable[list[dict]] | list[dict]]` where `RunContext(settings: dict, keywords: list[str], track_id: str | None, max_pages: int, dry_run: bool)`.
- `registry() -> dict[str, SourceSpec]` (discovers modules in the package, validates ids unique/regex), `get(id) -> SourceSpec`, `market_catalog(lang) -> dict[market, list[{id,label,requires_ack,default_on,attribution}]]` replacing markets.yaml reads.
- Runner/jobs dispatch use the registry for source steps; non-source steps (`seed`, `contacts`, `generic`, `resolve-websites`, `linkedin-login`, inbox) stay as they are.
- Offers produced by a source carry `source` = the value saved today for that source (keep a `db_source_name` per spec for legacy names like "InfoJobs", "Tecnoempleo-<track>").

- [x] Characterisation tests FIRST: for each existing source, record the scraper function called and its arguments for a Javi-like config (fixture `tests/fixtures/config_legacy_like.yaml`, invented values) before refactoring; same assertions must pass after.
- [x] Registry tests: discovery, unique ids, every spec has label es/en, markets valid, attribution present; adding a dummy module in a temp package path is discovered.
- [x] Commit `refactor(scrapers): registro de fuentes autodescubiertas sin cambiar el comportamiento`.

### Task 2: Remote JSON sources (Remotive, RemoteOK, Arbeitnow, freehire)

**Files:** Create `backend/scraper/sources/{remotive,remoteok,arbeitnow,freehire}.py`, fixtures `backend/tests/fixtures/sources/{remotive,remoteok,arbeitnow,freehire}.json`; Tests `backend/tests/test_sources_remote.py`.

**Interfaces:** each `run(ctx)` → normalized offers `{title, company_name, location, url, posted_at, description, tech_stack, salary_text, source}`; keyword filter (the APIs' own search param when available, else client-side match on title/tags); markets `("remote",)` (+ `global` where sensible); `attribution.required=True` for remotive and remoteok; HTTP: `requests.get(url, params, timeout=20, headers={"User-Agent": "jobhunter-es (+https://github.com/javipiazza94/jobhunter-es)"})`; non-200/invalid JSON → `SourceError` caught by runner (logged, other sources continue). Endpoints: verify each API's current public documentation before coding (Remotive `https://remotive.com/api/remote-jobs?search=`, RemoteOK `https://remoteok.com/api` (first element is legal notice), Arbeitnow `https://www.arbeitnow.com/api/job-board-api`); for freehire verify a public JSON API exists — if none is documented, implement it as a disabled spec with a clear `unavailable_reason` and say so in the report (do not scrape HTML in its place).

- [x] Tests from fixtures: parsing, keyword filtering, attribution fields, error shapes (429, HTML body, missing keys) → SourceError; persistence of one parsed offer through the normal save path keeps `source` and URL.
- [x] Commit `feat(sources): Remotive, RemoteOK, Arbeitnow y freehire por API`.

### Task 3: Computrabajo per country + robots for HTML sources

**Files:** Modify `backend/scraper/computrabajo.py`, `backend/scraper/sources/computrabajo.py`; Create `backend/scraper/robots_gate.py` (or extend `automation/robots_check`) ; Tests.

**Interfaces:** `COUNTRY_DOMAINS = {"es": "https://www.computrabajo.es", "mx": "https://mx.computrabajo.com", "co": "https://co.computrabajo.com", "ar": "https://ar.computrabajo.com", "pe": "https://pe.computrabajo.com", "cl": "https://cl.computrabajo.com", …}` — verify the URL pattern and search path per country against the live site docs/robots before coding (do not guess: if a country uses a different search path, encode it per country); param `country` (default `es`), market `latam` for non-es and `spain` for es. Robots: before a Playwright/HTML source run, `robots_check.gate(start_url_for(settings))`; refused → source skipped with reason `robots.txt no permite …` recorded in the job log/result; LinkedIn exempt only when acknowledged (Task 5 wires ack); `--ignore-robots` NOT offered.

- [x] Tests: URL building per country with fixture HTML per country (at least es + mx + co), robots refusal skips (mock), Spain default unchanged (characterisation from Task 1).
- [x] Commit `feat(sources): Computrabajo por país y robots.txt en fuentes HTML`.

### Task 4: Followed companies over aggregators

**Files:** Modify `backend/search_config.py` (top-level `followed_companies: list[FollowedCompany(name, tier=1, aliases: list[str] = [])]` in addition to per-track ones), sources supporting company queries (`company_query: bool` in spec), runner; frontend Offers filter "Solo empresas seguidas"; Profile → Búsqueda: manage followed companies; `examples/*.yaml` add Adecco/Manpower examples; Tests.

**Interfaces:** for each enabled source with `company_query`, the runner adds one query per followed company (name or alias) limited to `max_company_queries` (default 10); offers whose normalized company matches a followed company/alias get `followed_tier` (existing mechanism) even when found via keyword queries; API `GET /api/offers?followed=1`. No scraping of the companies' own sites.

- [x] Tests: alias matching (e.g. "Adecco Group", "The Adecco Group España" ↔ "Adecco"), query cap, filter endpoint, existing per-track followed companies unchanged.
- [x] Commit `feat(sources): empresas a seguir sobre los agregadores`.

### Task 5: Ack, secrets and clean-ups

**Files:** `backend/scraper/sources/linkedin.py` (requires_ack + exact warning text es/en naming that it breaks LinkedIn's terms), `indeed.py` (off without `SCRAPERAPI_KEY` via keychain/env — add `scraperapi_key` to `secrets_store` names), `setup_builder`/settings API enforce ack from spec; delete `backend/scraper/ey_careers.py` or turn it into a `company_direct` example in `examples/` (ruling: delete — dead code with hard-coded locations; document how to add a careers page via company_direct); rename SAP-specific names in `company_direct.py` to generic (`_is_relevant_offer`, keywords from config); `generic` step reads isolated tracks and its sources from the registry; seeds documented as generic Spain list (`seeds/README.md`). Tests.

- [x] Commit `feat(sources): aceptación explícita, clave de ScraperAPI en el llavero y fuentes generalizadas`.

### Task 6: Language detection, language_gate/posting_guard coverage

**Files:** Create `backend/automation/language_detect.py`; Modify `language_gate.py`, `posting_guard.py`; Tests.

**Interfaces:** `detect_language(text: str) -> str | None` (es/en/de/fr/it/pt via stopword frequency on normalized text, min 20 words, confidence margin; None when unsure); stored on offers as `job_offers.language` via a new migration (007) filled at persist time (and lazily for existing rows when needed by documents). `language_gate`: variants and requirement/level phrases for de/fr/it ("Deutschkenntnisse", "fließend", "verhandlungssicher", "courant", "bilingue", "obligatoire", "richiesto", "fluente", "madrelingua"…); `posting_guard`: injection patterns in de/fr/it mirroring the es block.

- [x] Tests per language with invented sentences; migration 007 on a v6 DB; existing language_gate results unchanged for es/en fixtures.
- [x] Commit `feat(i18n): idioma de la oferta y filtros de idioma en de/fr/it`.

### Task 7: Templates per language (letters, follow-ups, LaTeX labels)

**Files:** Move `backend/templates/*.j2` → `backend/templates/es/`; create `backend/templates/en/` (cover_letter_base/tech/sap? — ruling: `base` and `tech` in en; `sap` stays es-only example), `followup.j2` per language; `templates/latex/i18n/{es,en}.yaml` (section titles, salutation, closing, page footer, months, present label); Modify `cover_letter.py`, `followup.py`, `document_generator.py`, `application_documents.py`, `ai_writing.py` (letter language), `config.py` (template lookup `JH_HOME/templates/<lang>/` override first); profile `preferences.default_language` (es|en|…; wizard sets from ui_language); Tests.

**Interfaces:** `available_template_languages() -> set[str]` (directories present); `letter_language(offer, profile) -> str` = offer.language if templates exist for it else profile default else "es"; all generators take `lang`. Backward compat: existing installs keep Spanish output (default "es"), old flat template paths in `JH_HOME/templates/` still honoured as `es`.

- [ ] Tests: German offer + es/en templates → default language; English offer → English letter & LaTeX labels; adding a fake language dir `xx` (fixture files only) is used with no code change (finish-line test).
- [ ] Commit `feat(i18n): cartas, seguimientos y documentos en el idioma de la oferta`.

### Task 8: Frontend i18n infrastructure + selector

**Files:** Create `frontend/lib/i18n/{es,en}.json`, `frontend/lib/i18n/index.ts` (`t(key, vars?)`, `useT()`, `LocaleProvider`, `setLocale`, `formatDate`), `frontend/app/components/LanguageSelector.tsx`; Modify `app/layout.tsx` (`<html lang>` dynamic via client effect), `page.tsx`; Tests `frontend/lib/i18n/i18n.test.ts` (key parity es/en, interpolation, fallback to es then key), selector test.

**Interfaces:** locale persisted in `localStorage` (`jh.locale`) and in profile `preferences.ui_language` (PATCH); initial = profile value → localStorage → `navigator.language` → es. Adding a language = add `<lang>.json` + register in `SUPPORTED` list derived from files via a generated index (no component code). Error codes: map `code` → `errors.<code>` key.

- [x] Commit `feat(i18n): infraestructura de idiomas y selector en la interfaz`.

### Task 9: Migrate all UI strings

**Files:** every component/tab/panel/wizard/lib label map listed in the survey (≈38 files): `T` objects and inline JSX → `t()` keys; `toLocaleDateString("es-ES")` → `formatDate`; tests updated (import dictionaries instead of `T`); backend HTTPExceptions shown in UI get `code` (Task-level ruling: add `code` to the ~25 most common user-facing errors; others fall back to detail).

**Interfaces:** a static check test `frontend/lib/i18n/no-hardcoded.test.ts` that scans `app/**/*.tsx` and `lib/**/*.ts` for JSX text nodes / string literals with letters outside an allowlist (class names, ids, URLs, keys) and fails on Spanish/English prose — keep the allowlist small and justified.

- [ ] Tests: parity, no-hardcoded scan, a happy-dom test that renders main tabs in `en` and asserts no dictionary-es-only value appears.
- [ ] Commit `feat(i18n): toda la interfaz en español e inglés`.

### Task 10: Wizard, Profile and sources UI on the registry

**Files:** SetupWizard (markets → sources from registry with attribution + ack warning es/en; LATAM country picker for Computrabajo; remote sources), ProfileTab Búsqueda (per-source params: country, locations; followed companies), offers list/detail always show source name + link (attribution), `ui_language` step in wizard; Tests.

- [ ] Commit `feat(frontend): fuentes del registro, país y atribución en asistente y perfil`.

### Task 11: Docs and finish line

**Files:** `CONTRIBUTING.md` ("Add a source" = file + fixture test + doc line; "Add a language" = JSON + templates), README/README.es sources table (market, ack, attribution, notes), `docs/sources.md`; Test `backend/tests/test_sp4_finish.py` + frontend parity tests.

- [ ] Finish-line tests: every registered source has a fixture test (meta-test enumerating the registry and asserting a test file references each id); adding a test language (`xx` dictionary + template dir in tmp) works without code; es↔en UI scan clean.
- [ ] Commit `docs(sp4): añadir fuentes e idiomas; pruebas de cierre`.
