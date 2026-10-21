# SP2 — AI layer, first-run wizard and "Profile" · Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new user with an empty `JH_HOME` reaches scored offers using only the wizard (upload CV or fill a form → review → where to search), with any AI provider (`ollama`, `anthropic`, `openai`, `claude_cli`, `codex_cli`) or with `none`; everything is editable later in a "Profile" tab.

**Architecture:** New `backend/ai/` package (one provider interface, six implementations, factory from config). Secrets in the OS keychain (`keyring`) with env-var fallback. `jobhunter.yaml` gains `ai:` and `email:` sections and a writer; `profile.json` gets a store with atomic writes. The wizard is pure backend logic (`setup_builder`) behind `/api/setup/*`; the frontend adds a 3-step wizard and a Profile tab. AI also adapts cover letters (template as fallback) and generates an interview pack.

**Tech Stack:** FastAPI, Pydantic 2, PyYAML, `requests` (HTTP providers, no vendor SDKs), `subprocess` (CLI providers), `keyring`, `pypdf`, `python-docx`, `python-multipart`; Next.js 16 / React 19 / Tailwind 4 / bun test.

**Spec (summary of the private design doc, binding):** AI layer with a common interface (generate text, generate JSON for a schema) and providers `ollama` (local HTTP, default suggested by the wizard), `anthropic` and `openai` (API key from keychain or env), `claude_cli` (`claude -p`, uses the user's subscription), `codex_cli` (`codex exec`), `none`. The app never stores passwords or session tokens of subscriptions: it only checks the CLI is installed and logged in. API keys and the SMTP password go to the keychain, never to files; env vars still work (developer mode). Uses: (1) read the CV and propose the profile (JSON); (2) adapt the cover letter to each offer with the template as fallback; (3) interview pack from the app. Scoring never uses AI. With `none` everything works (manual form, template letters). Wizard: 1) CV upload (PDF/DOCX, text extracted locally) or manual form; 2) review what was understood: targets, experience, tools, languages with CEFR level, modality and city, eligibility (work permit / visa sponsorship / driving licence) — all editable; 3) where to search: markets → suggested sources per market (`requires_ack` sources unchecked with a warning) → followed companies → "Search offers". The wizard writes `profile.json` and `jobhunter.yaml`: each target is a track, tools are keywords, languages feed `language_gate`; one keyword group per target plus one with the user's tools, weights split evenly. "Profile" lets the user fix everything later, including AI provider and sources. SMTP is generic with a Gmail preset, configured in Profile, password in the keychain.

## Global Constraints

- Work in `jobhunter-es` (public upstream). No personal data anywhere (names, emails, cities of real people); test data invented (city "Villanova", companies "Acme Robotics", "Globex Data").
- Behaviour of existing installs must not change: a `jobhunter.yaml` **without** `ai:` means provider `none`; without `email:` means the Gmail preset with `GMAIL_USER` / `GMAIL_APP_PASSWORD` env vars exactly as today. Existing scoring results unchanged.
- Never send email or submit a form without explicit approval (unchanged flows).
- No secret ever written to `jobhunter.yaml`, `profile.json`, logs or API responses (responses say `has_key: true/false`).
- AI providers use `requests` / `subprocess` only (no `anthropic`/`openai` SDKs). Network and subprocess are always mocked in tests.
- Default models (overridable in `ai.model`): ollama `llama3.1`, anthropic `claude-sonnet-5-5`, openai `gpt-4o-mini`; CLI providers use the CLI's default.
- New deps pinned in `backend/requirements.txt`: `keyring`, `pypdf`, `python-docx`, `python-multipart` (versions ≥ 2 weeks old).
- Migrations: none needed (no DB schema change). If one becomes necessary, append to `MIGRATIONS` only.
- Suites green at every commit: backend `pytest -q` + `ruff check --config ../ruff.toml .`; frontend `bun test`, `bun run lint`, `bunx tsc --noEmit` (or `bun node_modules/typescript/bin/tsc --noEmit -p .`). `test_api_contract.py` must stay green (TS types in `frontend/lib/types.ts` mirror Pydantic models).
- Docstrings/comments in Spanish (repo style), identifiers in English. Commits in Spanish.
- Frontend: follow current dashboard style (dark CSS vars in `app/globals.css`, lucide-react icons, no new UI libs). Next 16 has breaking changes: read `frontend/node_modules/next/dist/docs` before using an unfamiliar API.

## Review Focus

1. An existing install (config without `ai:`/`email:`) must behave exactly as before: drafts use templates, email uses the env vars. Test it.
2. A keychain backend that is unavailable (headless Linux without Secret Service) must not crash the app: env var fallback works and saving a secret returns a clear 409/503 message.
3. A provider returning malformed JSON / non-JSON / timing out: `generate_json` raises `AIError`, the wizard falls back to an empty draft, cover letters fall back to the template.
4. Wizard input with duplicate/unicode/blank target names must still produce valid, unique track ids (`^[a-z][a-z0-9_]*$`, not `manual_review`) and weights summing to 1.0.
5. Upload of a non-PDF/DOCX, an encrypted/empty PDF, or a >10 MB file → 4xx with a message, never 500.

---

### Task 1: Config sections, config writer and profile store

**Files:** Modify `backend/search_config.py`; Create `backend/profile_store.py`; Modify `backend/automation/cover_letter.py`, `backend/automation/application_engine.py`; Tests `backend/tests/test_config_ai_email.py`, `backend/tests/test_profile_store.py`.

**Interfaces — Produces:**
- `class AISettings(_Model)`: `provider: Literal["none","ollama","anthropic","openai","claude_cli","codex_cli"] = "none"`, `model: str | None = None`, `base_url: str | None = None`, `timeout_seconds: int = 120`.
- `class EmailSettings(_Model)`: `preset: Literal["gmail","custom"] = "gmail"`, `smtp_host: str = "smtp.gmail.com"`, `smtp_port: int = 587`, `use_starttls: bool = True`, `username: str | None = None`, `from_name: str | None = None`.
- `JobHunterConfig` gains `ai: AISettings = AISettings()`, `email: EmailSettings = EmailSettings()`.
- `save_config(cfg: JobHunterConfig, path: Path | None = None) -> Path`: writes YAML (`model_dump(mode="json", exclude_defaults=False)`, `yaml.safe_dump(allow_unicode=True, sort_keys=False)`) atomically (tmp + `os.replace`) to `path` or `JH_HOME/jobhunter.yaml`; re-validates by loading the written file; calls `reload_config()`.
- `profile_store.load_profile() -> dict` (tolerant: `{}` on missing/corrupt), `profile_store.save_profile(data: dict) -> Path` (atomic write to `config.PROFILE_PATH`, read at call time from `config`, then `language_gate.candidate_languages.cache_clear()`), `profile_store.profile_exists() -> bool`.
- `cover_letter._load_profile` and `application_engine._load_profile` delegate to `profile_store.load_profile()` (no more exception when `profile.json` is missing).

- [ ] Tests first: default `ai.provider == "none"` when section absent; unknown provider rejected with `ConfigError`; `save_config` round-trip equals original model; written file has no key named like `*key*`/`*password*`; `save_profile` then `load_profile` round-trip; missing profile → `{}`; `create_drafts` with no `profile.json` does not raise (returns 0 drafts or skips with log).
- [ ] Implement; run focused tests; full suite; commit `feat(config): secciones ai/email, escritura de jobhunter.yaml y almacén de perfil`.

### Task 2: Secrets in the keychain

**Files:** Create `backend/secrets_store.py`; Modify `backend/requirements.txt`; Test `backend/tests/test_secrets_store.py`.

**Interfaces — Produces:**
- `SERVICE = "jobhunter"`; secret names: `"anthropic_api_key"`, `"openai_api_key"`, `"smtp_password"`.
- `ENV_FALLBACK = {"anthropic_api_key": "ANTHROPIC_API_KEY", "openai_api_key": "OPENAI_API_KEY", "smtp_password": "GMAIL_APP_PASSWORD"}`.
- `get_secret(name: str) -> str | None`: env var first, then `keyring.get_password(SERVICE, name)`; any keyring exception → `None` (logged at debug, never the value).
- `set_secret(name: str, value: str) -> None` / `delete_secret(name: str) -> None`: raise `SecretStoreUnavailable(str)` if keyring has no usable backend or errors.
- `has_secret(name) -> bool`.

- [ ] Tests (monkeypatch `keyring` functions or install an in-memory `keyring.backend.KeyringBackend` subclass): env wins over keychain; keychain used when env absent; failing backend → `get_secret` returns None and `set_secret` raises `SecretStoreUnavailable`; unknown name → `ValueError`.
- [ ] Implement; commit `feat(secrets): claves y contraseña SMTP en el llavero del sistema`.

### Task 3: AI provider layer

**Files:** Create `backend/ai/__init__.py`, `backend/ai/base.py`, `backend/ai/http_providers.py` (ollama, anthropic, openai), `backend/ai/cli_providers.py` (claude_cli, codex_cli); Test `backend/tests/test_ai_providers.py`.

**Interfaces — Produces:**
- `class AIError(Exception)`; `class AIUnavailable(AIError)` (provider `none` or not configured/installed).
- `class Provider(Protocol)`: `name: str`; `generate_text(prompt: str, system: str | None = None) -> str`; `generate_json(prompt: str, schema: dict, system: str | None = None) -> dict`; `check() -> tuple[bool, str]` (ok, human message: "Ollama responde en …", "Falta la clave de API", "claude no está instalado", "claude sin sesión").
- `get_provider(settings: AISettings | None = None) -> Provider` (default `get_config().ai`).
- `generate_json` default implementation in `base.py`: asks for JSON matching `schema` (schema embedded in the prompt), extracts the first JSON object from the reply (handles ```json fences), validates required top-level keys from `schema["required"]`; on failure raises `AIError`.
- Ollama: `POST {base_url or http://127.0.0.1:11434}/api/chat` `{"model","messages","stream":false}` (+ `"format":"json"` for JSON); check = `GET /api/tags`.
- Anthropic: `POST https://api.anthropic.com/v1/messages`, headers `x-api-key`, `anthropic-version: 2023-06-01`; body `{"model","max_tokens":4096,"system","messages"}`; text = concatenated `content[*].text`. Key from `get_secret("anthropic_api_key")`; missing → `AIUnavailable`.
- OpenAI: `POST {base_url or https://api.openai.com/v1}/chat/completions` with `Authorization: Bearer`; JSON mode `response_format: {"type":"json_object"}`.
- `claude_cli`: `subprocess.run(["claude", "-p", prompt, "--output-format", "text"], capture_output=True, text=True, timeout=…)` (system prepended to prompt); check = `shutil.which("claude")` then `claude -p "ok"` exit code 0. `codex_cli`: `["codex", "exec", prompt]` analogous. Non-zero exit → `AIError` with stderr tail (≤300 chars).
- HTTP errors / timeouts → `AIError` (status code in message, never the key).

- [ ] Tests with doubles (monkeypatch `requests.post/get`, `subprocess.run`, `shutil.which`): each provider happy path text + JSON; malformed JSON → `AIError`; HTTP 401 → `AIError` without key in message; missing key → `AIUnavailable`; `none` → `AIUnavailable`; fenced JSON parsed.
- [ ] Implement; commit `feat(ai): capa de proveedores (ollama, anthropic, openai, claude_cli, codex_cli, none)`.

### Task 4: Generic SMTP

**Files:** Modify `backend/automation/email_sender.py`, `backend/config.py` (keep constants for compat); Test `backend/tests/test_email_sender_smtp.py`.

**Interfaces — Produces:** `smtp_settings() -> tuple[host, port, starttls, username, password, from_header]` resolved as: `cfg.email` values; `username = cfg.email.username or GMAIL_USER env`; `password = get_secret("smtp_password")` (env `GMAIL_APP_PASSWORD` via fallback); `from_header = formataddr((from_name, username))` if `from_name`. `send_email(...)` signature unchanged; reads settings at call time (not import time). `test_smtp_connection() -> tuple[bool, str]` (connect + login, no send).

- [ ] Tests (monkeypatch `smtplib.SMTP` with a fake recording calls): config without `email:` + env vars → smtp.gmail.com:587 STARTTLS login with env user/password (today's behaviour); custom preset uses its host/port; no password → `(False, None)` and no connection; From header uses from_name.
- [ ] Implement; commit `feat(email): SMTP genérico con preset de Gmail y contraseña en el llavero`.

### Task 5: CV reading and profile proposal

**Files:** Create `backend/automation/cv_reader.py`, `backend/automation/profile_proposal.py`; Modify `backend/requirements.txt`; Tests `backend/tests/test_cv_reader.py`, `backend/tests/test_profile_proposal.py` (+ tiny generated fixtures at test time: build a DOCX with python-docx and a PDF with an existing test helper or `pypdf` writer — no binary personal files committed).

**Interfaces — Produces:**
- `extract_text(path: Path) -> str` for `.pdf` (pypdf; fallback `verify_pdf` pdftotext extractor) and `.docx` (python-docx paragraphs + tables); raises `CVReadError` for unsupported type, encrypted/empty/unreadable file.
- Pydantic `ProfileDraft`: `full_name: str = ""`, `email: str = ""`, `phone: str = ""`, `city: str = ""`, `country: str = ""`, `targets: list[TargetDraft]` (`title: str`, `keywords: list[str]`), `years_experience: int | None`, `experience: list[ExperienceDraft]` (`company, role, start, end, description, stack: list[str]`), `tools: list[str]`, `languages: list[LanguageDraft]` (`language: str`, `level: Literal["A1","A2","B1","B2","C1","C2","native"]`), `modality: list[Literal["remote","hybrid","onsite"]]`, `eligibility: EligibilityDraft` (`work_permit_countries: list[str]`, `needs_sponsorship: bool | None`, `driving_license: bool | None`).
- `propose_profile(cv_text: str, provider: Provider | None = None) -> tuple[ProfileDraft, str]` → (draft, source) with source `"ai"` or `"empty"`; any `AIError` → empty draft (source `"empty"`), never raises. Prompt states: only facts present in the CV, no invention.

- [ ] Tests: PDF and DOCX text extraction; unsupported/empty → `CVReadError`; proposal with a fake provider returning valid JSON → draft fields; invalid level coerced or dropped; provider raising `AIError` → empty draft; `none` → empty draft.
- [ ] Implement; commit `feat(setup): lectura de CV (PDF/DOCX) y propuesta de perfil con IA`.

### Task 6: Wizard builder (answers → profile.json + jobhunter.yaml)

**Files:** Create `backend/setup_builder.py`, `backend/defaults/markets.yaml`; Test `backend/tests/test_setup_builder.py`.

**Interfaces — Produces:**
- `markets.yaml`: markets `spain`, `latam`, `remote`, `global`, each with suggested sources `[{id, label, requires_ack, default_on}]` limited to sources that exist today in `backend/scraper/runner.py` (e.g. spain: tecnoempleo, infojobs(requires_ack), manfred, computrabajo; remote: remote-friendly existing sources; global: linkedin (requires_ack, default_on false), indeed). Unknown future sources are added in SP4.
- `class SetupAnswers(BaseModel)`: `draft: ProfileDraft`, `markets: list[str]`, `sources: list[str]`, `acknowledged_sources: list[str]`, `followed_companies: list[str]`, `ai: AISettings`, `ui_language: Literal["es","en"] = "es"`.
- `build_profile(answers) -> dict` (shape compatible with `profile.example.json`: `personal.*`, `languages`, `experience`, `stack.other_tools`, `availability.work_mode_preference`, plus `eligibility`).
- `build_config(answers, base: JobHunterConfig | None = None) -> JobHunterConfig`: one standard track per target (`id = slugify(title)` → ascii, `[a-z][a-z0-9_]*`, dedup with `_2`, avoid `manual_review`), `label {es,en}` = title, `classify_keywords`/`search_keywords` = target keywords; keyword groups: one per target (`id = <track_id>`) + `tools`; weights: keyword groups share `1 - (location+experience+salary weights of base defaults)` evenly, rounding so the total is exactly 1.0; `scoring.location.city` = draft city; `sources` = selected sources with keywords = union of target keywords, `requires_ack` sources only if in `acknowledged_sources` (else dropped); followed companies → `followed_companies` on every standard track (tier 1); `ai` = answers.ai.
- `apply_setup(answers) -> dict` writes both files via `save_profile` / `save_config` and returns `{"tracks": [...ids], "sources": [...]}`.

- [ ] Tests: two targets → two tracks + 3 keyword groups, weights sum 1.0 (exact, `math.isclose` with 1e-9); unicode/duplicate/blank titles → valid unique ids; requires_ack source without ack is excluded; result validates by loading the written YAML with `load_config`; profile languages map to `language_gate.candidate_languages()` after `cache_clear()`.
- [ ] Implement; commit `feat(setup): construcción de perfil y jobhunter.yaml desde el asistente`.

### Task 7: Setup, profile and settings API

**Files:** Modify `backend/main.py`, `backend/schemas.py`, `frontend/lib/types.ts` (contract), `backend/requirements.txt` (`python-multipart`); Test `backend/tests/test_setup_api.py`.

**Interfaces — Produces (all JSON; mutating routes keep the `X-JH-Client` check):**
- `GET /api/setup/status` → `{needs_setup: bool, has_profile: bool, has_config: bool}` (`needs_setup` = no `JH_HOME/jobhunter.yaml` or no profile).
- `GET /api/setup/markets` → markets.yaml content.
- `POST /api/setup/cv` (multipart `file`) → `{draft: ProfileDraft, source: "ai"|"empty", text_chars: int}`; ≤10 MB, `.pdf`/`.docx` only → else 400/413 with message; file saved to `JH_HOME/cv/` with a sanitized name and recorded as `cv_path` on apply.
- `POST /api/setup/propose` `{text}` → same as above (manual paste).
- `POST /api/setup/apply` `SetupAnswers` → `{tracks, sources}`.
- `GET /api/profile` / `PUT /api/profile` (whole profile dict, validated loosely: must be an object; returns saved profile).
- `GET /api/settings/ai` → `{provider, model, base_url, timeout_seconds, has_key: {anthropic: bool, openai: bool}}`; `PUT /api/settings/ai` `{provider, model?, base_url?, timeout_seconds?, api_key?}` (api_key stored with `set_secret` for anthropic/openai; never echoed); `POST /api/settings/ai/test` → `{ok, message}` from `provider.check()`.
- `GET /api/settings/email` → `{preset, smtp_host, smtp_port, use_starttls, username, from_name, has_password}`; `PUT /api/settings/email` (+ optional `password` → `set_secret("smtp_password")`); `POST /api/settings/email/test` → `{ok, message}`.
- `SecretStoreUnavailable` → 503 `{"detail": "El llavero del sistema no está disponible: usa la variable de entorno …"}`.

- [ ] Tests via `tests/asgi_client.call` (multipart body built by hand): each route happy path; missing header on PUT → 403; upload too big / wrong type → 4xx; secrets never in any response body; `/api/setup/apply` then `/api/tracks` returns the new tracks.
- [ ] Implement; keep `test_api_contract.py` green; commit `feat(api): asistente de primer arranque, perfil y ajustes de IA/email`.

### Task 8: AI cover letter and interview pack

**Files:** Create `backend/automation/ai_writing.py`; Modify `backend/automation/application_engine.py`, `backend/main.py`; Test `backend/tests/test_ai_writing.py`.

**Interfaces — Produces:**
- `adapt_cover_letter(template_letter: str, offer: dict, profile: dict, provider: Provider | None = None) -> tuple[str, str]` → (letter, `"ai"`|`"template"`); uses only profile facts; output must keep the template's greeting/sign-off language; on `AIError`/`AIUnavailable` or output shorter than 200 chars → template.
- `create_drafts` uses it after the template letter (provider from config; `none` → unchanged behaviour).
- `generate_interview_pack(application_id: str) -> Path` → Markdown at `APPLICATIONS_DIR/<id>/interview.md` with sections: company, role, likely questions, STAR stories from the profile, questions to ask, logistics; raises `AIUnavailable` with provider `none`.
- `POST /api/applications/{id}/interview-pack` → `{path, markdown}`; 409 with message when AI unavailable; 404 unknown id.

- [ ] Tests: provider double → adapted letter; failing provider → template; `none` → template and no call; interview pack written with all section headings; endpoint 409 on `none`.
- [ ] Implement; commit `feat(ai): carta adaptada a la oferta y pack de entrevista`.

### Task 9: Frontend — wizard and Profile tab

**Files:** Create `frontend/app/components/setup/SetupWizard.tsx`, `frontend/app/components/tabs/ProfileTab.tsx`, `frontend/lib/setup.ts` (pure helpers); Modify `frontend/app/page.tsx`, `frontend/lib/api.ts`, `frontend/lib/types.ts`; Tests `frontend/lib/setup.test.ts`, `frontend/app/components/setup/SetupWizard.test.tsx`, `frontend/app/components/tabs/ProfileTab.test.tsx`.

**Interfaces — Consumes:** Task 7 routes. **Produces:**
- `api.ts`: `fetchSetupStatus`, `fetchMarkets`, `uploadCv(file)` (FormData, header `X-JH-Client`), `proposeProfile(text)`, `applySetup(answers)`, `fetchProfile`, `saveProfile`, `fetchAISettings`, `saveAISettings`, `testAI`, `fetchEmailSettings`, `saveEmailSettings`, `testEmail`, `generateInterviewPack(id)`; all check `res.ok` and throw `Error(detail)`.
- `setup.ts` pure helpers: `emptyDraft()`, `addTarget/removeTarget`, `suggestedSources(markets, selectedMarkets)` (requires_ack unchecked), `validateStep(step, state) -> string[]` (errors: at least one target with title; at least one source), `toAnswers(state) -> SetupAnswers`.
- `SetupWizard` (3 steps: "Tu CV" upload or manual form / "Revisa lo que hemos entendido" editable fields incl. CEFR levels, modality, city, eligibility / "Dónde buscar" markets → sources with a visible warning text for `requires_ack` and an explicit checkbox per such source → followed companies → button "Buscar ofertas" which applies setup and triggers `POST /api/scraper/run`). Shown full-screen by `page.tsx` when `needs_setup` is true.
- `ProfileTab`: sections Perfil (basic fields + languages), IA (provider select, model, API key password field with "guardada"/"no guardada", "Probar"), Email (preset, host, port, user, from name, password, "Probar"), Búsqueda (sources on/off with ack, link to re-run wizard). New tab `"profile"` in the tab bar.
- UI strings in Spanish for now (i18n arrives in SP4) but kept in one `const T = {...}` object per component to ease extraction.

- [ ] Tests (bun test, pure helpers + `renderToStaticMarkup` snapshots of each step with given props): validation rules; requires_ack sources default unchecked and warning text present; ProfileTab never renders a stored secret value; api functions send `X-JH-Client` on mutating calls and throw on `!res.ok`.
- [ ] Implement; `bun test`, lint, tsc; commit `feat(frontend): asistente de primer arranque y pestaña Perfil`.

### Task 10: Finish line — empty JH_HOME to scored offers

**Files:** Test `backend/tests/test_first_run_e2e.py`; Docs `README.md`, `README.es.md` (section "First run" / "Primer arranque" + AI providers + keychain note), `CONTRIBUTING.md` (how to add an AI provider).

- [ ] E2E test (subprocess or in-process with a fresh temp `JH_HOME`, no `jobhunter.yaml`, no profile): `GET /api/setup/status` → needs_setup; `POST /api/setup/propose` with a sample CV text using (a) provider `none` → empty draft, then manual answers; (b) each of the 5 other providers with doubles → draft from fake JSON; `POST /api/setup/apply`; insert 3 invented offers through `scraper.persist` (or the same upsert path the runner uses) matching/not matching the targets; `GET /api/offers?track=<new id>` → the matching offer has `relevance_score > 0` and is in that track; non-matching offer not relevant.
- [ ] Docs updated; all suites green; commit `test(setup): de JH_HOME vacío a ofertas puntuadas con cada proveedor`.
