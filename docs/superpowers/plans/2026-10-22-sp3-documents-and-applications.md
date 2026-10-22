# SP3 — Documents and applications · Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For a real offer, "Prepare application" produces a CV (2 pages) and a cover letter (1 page) as PDFs that pass `verify_pdf`, with and without AI; the approval email attaches those PDFs; eligibility, AI evaluation, company research cache, screening answers, upskill, expand and custom templates exist in the app and as Claude Code commands.

**Architecture:** Most library code was already ported from MadsLorentzen/ai-job-search (`latex_compiler`, `document_generator`, `verify_pdf`, `verify_layout`, `application_archive`, `eligibility_gate`, `rank_state`, `company_research`, `robots_check`, `fetch_page`, `job_key`, `.claude/` commands/agents) but is not wired. SP3 wires it: an application-documents service (deterministic and AI writer+reviewer paths) writing to `JH_HOME/applications/<id>/`, new API routes and UI buttons, one DB migration for AI evaluations, and adapted Claude Code commands.

**Tech Stack:** FastAPI, SQLite (append-only migrations), Jinja2 → LaTeX, Tectonic (preferred) / XeLaTeX, pypdf (+ optional Poppler), `backend/ai` providers, Next.js 16 / React 19.

**Spec (summary of the private design doc, binding):** Ported from ai-job-search (MIT), adapted to the DB, `profile.json`/`jobhunter.yaml` and the `ai/` layer; each piece exists in the app (button/screen) **and** as a Claude Code command in `.claude/`. LaTeX: moderncv (banking) CV and `cover.cls` letter with Lato/Raleway (OFL), in `templates/latex/`, overridable in `JH_HOME/templates/`. Engine: Tectonic preferred (no TeX install for users), dev mode uses system `tectonic` or `xelatex`/`lualatex`; **first check that both templates compile with Tectonic** and report. With AI — writer + reviewer: (1) evaluate fit; (2) draft CV and letter adapted to the offer using only profile facts; (3) a second call acts as hiring manager, researches the company (cache) and critiques; (4) revise; (5) compile and verify; (6) iterate until it passes. Without AI: deterministic CV and letter from `profile.json` with the same templates. Verification: pages (CV 2, letter 1, configurable), ATS-readable text (email and phone literal, reading order), ASCII dates, keyword coverage of the offer (profile-backed keywords added, gaps stay gaps), layout (orphans, holes, nearly-empty last page, footer collision); `pypdf` mandatory, Poppler optional (`verify_layout` skipped with a warning). Honesty: never invent skills, companies, dates or figures; trim the least relevant content for that offer; escape LaTeX. `add-template`: register a custom template (LaTeX or Typst) with its compile command, style rules and page limit; mandatory test compile; switchable in Profile. Archive per application: CV, letter, clean posting and interview pack in `JH_HOME/applications/<id>/`; email attachments come from there. Eligibility filter (extends `language_gate`): work permit/citizenship, visa sponsorship, required residence, mandatory degree, licence — failing a hard requirement puts the offer at 0, doubtful only warns. AI evaluation (`/rank`) for offers the user marks: verdict, strengths, gaps, deadline urgency, expired; stored with the offer; never changes `relevance_score`. `job_key` dedupe (done). Upskill: skills-gap map from saved/evaluated/applied offers (or one) with study plan; own screen + Markdown report in `JH_HOME/reports/`. Expand: enrich the profile from GitHub/portfolio/certifications the user links; each new competence proposed with its source, saved only if accepted. Screening answers based only on profile + `screening_answers`; ATS filling uses them. Company research cache with expiry shared by reviewer, evaluation and interview. Contributors: `add-portal` command generates a source following the source contract with a sample-data test; `robots_check` (RFC 9309) and `fetch_page` (GET only, robots mandatory, size/time limits). Claude Code agents `posting-fetcher`, `application-reviewer`, `posting-scorer` adapted. Out: Notion sync, HTML report, Gmail sync, salary benchmarking, fork maintenance tools.

## Global Constraints

- Work in `jobhunter-es` (public upstream). Invented data only in tests/fixtures/docs.
- **Existing installs unchanged unless they opt in:** scores and `is_relevant` of existing offers must not change (the eligibility hard-reject is behind `scoring.eligibility_hard_reject: bool`, default `false`; the wizard writes `true` for new users). Existing approve/send flow keeps working when no documents were prepared (current attachment selection stays as fallback).
- Never send email or submit a form without explicit approval.
- AI output is untrusted: honesty validator rejects/strips companies, roles, dates or degrees not present in the profile; LaTeX special characters escaped; offer text is passed as data.
- Tests needing a TeX engine use `pytest.mark.skipif(no engine)`; tests needing Poppler likewise; CI installs both (already in `ci.yml`). No network in tests (Tectonic package download happens only in integration tests, marked).
- DB: one new migration appended to `MIGRATIONS` if needed (AI evaluations); never edit earlier ones.
- Suites green at every commit: backend `pytest -q` + `ruff check --config ../ruff.toml .`; frontend `bun test`, `bun run lint`, `bun node_modules/typescript/bin/tsc --noEmit -p .`; `test_api_contract.py` green (TS types mirror Pydantic).
- Spanish docstrings/comments, English identifiers, Spanish commits. Keep MIT attribution: add rows to `ATTRIBUTION.md`/`NOTICE` for every newly ported or derived piece.
- Frontend: existing dashboard style, lucide-react, strings in a `T` object per component.

## Review Focus

1. A profile with special LaTeX characters (`&`, `%`, `_`, `#`, `$`, accents, emoji) must compile, not inject LaTeX.
2. An AI draft that invents an employer/date/degree must be rejected or cleaned before compiling.
3. A CV longer than 2 pages must be trimmed (least relevant entries first) until it fits, not shipped at 3 pages; if it still fails, the user gets a clear error and the deterministic version.
4. No TeX engine installed → "Prepare application" returns a clear 409/503 message with install hint, never 500; approval still works with the old attachments.
5. Re-preparing an application overwrites its archive atomically (no half-written PDFs attached to an email).

---

### Task 1: Engine check and document pipeline hardening

**Files:** Modify `backend/automation/latex_compiler.py`, `backend/automation/document_generator.py`, `backend/automation/verify_pdf.py`; Tests `backend/tests/test_latex_compiler.py`, `backend/tests/test_document_generator.py`, `backend/tests/test_verify_pdf.py`; Docs: report section in this plan's ledger.

**Interfaces — Produces:**
- `latex_compiler.engine_available() -> str | None` (engine name or None); `compile_latex(..., passes: int = 2)` (second pass for engines other than tectonic, which handles reruns itself).
- `verify_pdf.keyword_coverage(text: str, keywords: list[str]) -> tuple[list[str], list[str]]` (present, missing; case/accents-insensitive, word boundaries).
- `document_generator.generate_deterministic_documents(...)` gains `output_dir` default `config.APPLICATIONS_DIR / "_preview"` when None (never inside the repo), `cv_pages: int = 2`, `letter_pages: int = 1`, verification requires email **and** phone literal, CV page count `<= cv_pages` (trimming loop: drop least relevant experience bullets/entries — relevance = keyword overlap with the offer — until it fits or nothing left to trim), letter exactly 1; returns also `verification: dict` (pages, missing_keywords, layout_warnings or "skipped").
- `verify_layout` called when Poppler exists; otherwise `layout: "skipped: poppler no instalado"`.

- [x] First step: compile `cv.tex.j2` and `cover.tex.j2` rendered from `profile.example.json` with **Tectonic** (local `~/.local/bin/tectonic`) and record the result in the report (works / what had to change). If a template fails with Tectonic, fix the template (XeTeX-compatible) — not the engine.
- [x] Tests: skip markers when no engine/poppler; LaTeX escaping of `& % _ # $ { } ~ ^ \` and emoji (stripped or replaced); trimming loop with a synthetic long profile yields ≤2 pages; missing phone → verification failure; keyword_coverage cases.
- [x] Commit `feat(docs): motor LaTeX comprobado con Tectonic, verificación completa y recorte a 2 páginas`.

### Task 2: Application documents service, archive and API (deterministic path)

**Files:** Create `backend/automation/application_documents.py`; Modify `backend/automation/application_archive.py`, `backend/automation/application_engine.py`, `backend/main.py`, `backend/schemas.py`, `frontend/lib/types.ts`; Test `backend/tests/test_application_documents.py`.

**Interfaces — Produces:**
- `prepare_application(application_id: str, use_ai: bool | None = None) -> PreparedDocs` where `PreparedDocs` (Pydantic): `application_id, cv_pdf: str, cover_pdf: str, source: Literal["ai","deterministic"], verification: dict, warnings: list[str]`. `use_ai=None` → AI if provider != none. Writes to a temp dir then `archive_application(...)` atomically (write into `<id>.tmp/` then `os.replace` the dir) incl. `job_posting.md` (clean offer text) and `metadata.json`.
- Errors: `NoTexEngine` → API 409 `{"detail": "Instala Tectonic …"}`; `VerificationFailed` (after deterministic fallback also fails) → 422 with reasons.
- API: `POST /api/applications/{id}/prepare` (`{use_ai?: bool}`) → `PreparedDocs`; `GET /api/applications/{id}/documents` → list of files; `GET /api/applications/{id}/documents/{name}` → file (only names in the archive whitelist: cv.pdf, cover.pdf, job_posting.md, interview.md; `FileResponse`).
- `_send_approved` keeps using `get_application_attachments` (archive first, old selection fallback) — add a test proving prepared PDFs are attached.
- Interview pack (`ai_writing.generate_interview_pack`) and `application_archive.save_interview_prep` unified on `interview.md`.

- [x] Tests (engine-dependent ones skipped without engine; others monkeypatch `generate_deterministic_documents`): prepare writes archive atomically; failure leaves the previous archive intact; whitelist blocks `../`; approve attaches archived PDFs (fake SMTP); no engine → 409.
- [x] Commit `feat(applications): preparar candidatura con CV y carta en PDF archivados`.

### Task 3: AI writer + reviewer flow

**Files:** Create `backend/automation/ai_documents.py`; Modify `application_documents.py`; Test `backend/tests/test_ai_documents.py`.

**Interfaces — Produces:**
- `draft_documents(profile, offer, provider, research: dict | None) -> DocsDraft` (JSON: `cv` = same context shape `prepare_cv_context` produces — summary, ordered experience with selected bullets, skills, education, languages; `letter` = paragraphs) — generated with `generate_json` and a schema.
- `review_documents(draft, offer, provider, research) -> Review` (`verdict: "ok"|"revise"`, `issues: list[str]`, `missing_keywords: list[str]`).
- `revise_documents(draft, review, profile, offer, provider) -> DocsDraft`.
- `validate_honesty(draft, profile) -> DocsDraft` — drops experience entries whose company/role/dates do not match a profile entry (normalized), drops skills not in profile skills/stack/experience stack, drops degrees not in education; returns cleaned draft + list of removed items (warnings).
- `run_ai_flow(profile, offer, provider, max_rounds=2) -> (cv_ctx, letter_ctx, warnings)`; `prepare_application` uses it when `use_ai`, renders with the same templates, compiles, verifies (2/1 pages, keywords), and on page overflow asks one more revision ("shorten") then falls back to the trimming loop; any AIError → deterministic path with warning `"IA no disponible: …"`.
- Research: `company_research.get_cached_research(company)` passed to writer/reviewer when present (Task 6 fills it).

- [x] Tests with a scripted fake provider: happy path (draft → review revise → revised → ok); invented company removed by honesty validator; AIError → deterministic; overflow → shorten request issued.
- [x] Commit `feat(ai): redactor y revisor de CV y carta adaptados a la oferta`.

### Task 4: Eligibility as hard requirement (opt-in)

**Files:** Modify `backend/search_config.py` (`Scoring.eligibility_hard_reject: bool = False`), `backend/automation/offer_review.py` / scoring path (`scraper/persist.py` or `filter_engine`), `backend/setup_builder.py` (wizard writes `true`), `backend/automation/eligibility_gate.py` (add visa sponsorship from `personal.needs_sponsorship`/`eligibility.needs_sponsorship`, required residence vs `personal.country_code`); Tests.

**Interfaces:** When the flag is true and `eligibility_gate` returns `"reject"`, the persisted offer gets `relevance_score = 0`, `is_relevant = 0`, and a review flag `"elegibilidad: <reason>"`; `"flag"` only warns (as today). Flag false → identical to today (test with the existing fixture config).

- [x] Tests: flag false → unchanged scores; flag true + US-only offer + ES permit → 0; doubtful → flag only; wizard config has flag true.
- [x] Commit `feat(eligibility): requisitos duros dejan la oferta a 0 (opcional, activado por el asistente)`.

### Task 5: AI evaluation of offers (/rank in the app)

**Files:** Create `backend/automation/offer_evaluation.py`; Modify `backend/database.py` (migration 006 `offer_evaluations(offer_id PK/FK, verdict, score_0_100, strengths JSON, gaps JSON, urgency, expired, evaluated_at, provider)`), `backend/automation/rank_state.py` (paths from `config.DB_PATH`/JH_HOME, no hardcoded repo paths), `backend/main.py`, `schemas.py`, `frontend` (button "Evaluar con IA" in offer detail + shortlist action, display); Tests.

**Interfaces:** `evaluate_offer(offer_id, provider=None) -> Evaluation` (weights technical .30, experience .25, behavioral .15, career .30 and bands from `rank_state` reused); stored; never touches `relevance_score`. API: `POST /api/offers/{id}/evaluate` (409 with `none`), `GET /api/offers/{id}/evaluation`, `POST /api/offers/evaluate-batch` (`{ids}` sequential with AIBudget). OfferOut gains optional `evaluation` summary (verdict, score) — contract types updated.

- [x] Tests: migration applies on a v5 DB; evaluation stored; relevance unchanged; 409 on none; batch respects budget.
- [x] Commit `feat(rank): evaluación detallada con IA de las ofertas marcadas`.

### Task 6: Company research cache

**Files:** Create `backend/automation/company_researcher.py`; Modify `company_research.py` (use `config.COMPANY_RESEARCH_DIR` at call time), `ai_writing.generate_interview_pack`, `ai_documents`, `offer_evaluation`; API `POST /api/companies/{name}/research`, `GET` cached; Tests.

**Interfaces:** `research_company(name, website: str | None, provider) -> dict` — fetches the website home/about page with `fetch_page` (robots respected, size/time limits; fetch failures tolerated) and asks the provider for a JSON summary `{summary, products, culture_signals, tech_stack, size_hint, sources: [url]}`; cached 30 days via `save_cached_research`; `get_or_research(...)` used by reviewer, evaluation and interview pack.

- [x] Tests: cache hit avoids provider call; robots disallow → summary from offer text only with warning; expired cache refreshed.
- [x] Commit `feat(research): caché de investigación de empresas compartida`.

### Task 7: Screening answers

**Files:** Modify `backend/profile_store.py`/profile validation (`screening_answers: list[{question, answer}]`), create `backend/automation/screening.py`, modify `backend/automation/form_filler.py` (use answers for known fields/questions when filling; never submits), API `POST /api/applications/{id}/answers` (`{questions: [{text, max_chars?}]}` → answers), Profile tab section to edit `screening_answers`; Tests.

**Interfaces:** `answer_questions(questions, profile, offer, provider) -> list[{question, answer, source: "profile"|"ai"|"needs_input"}]` — exact/fuzzy match against `screening_answers` first; AI only with profile facts; respects `max_chars` (truncate at sentence boundary); unknown factual questions (salary, notice period not in profile) → `needs_input`.

- [x] Tests: saved answer reused; max_chars respected; AI none → needs_input for unmatched; form_filler gets answers (unit, no browser).
- [x] Commit `feat(forms): respuestas de cribado basadas en el perfil`.

### Task 8: Upskill and expand

**Files:** Create `backend/automation/upskill.py`, `backend/automation/expand_profile.py`; API `POST /api/upskill` (`{offer_ids?: [], scope: "saved"|"evaluated"|"applied"|"one"}` → `{report_path, markdown}`), `POST /api/profile/expand` (`{sources: [url]}` → proposals), `POST /api/profile/expand/accept` (`{items}` → merges into profile); Frontend: "Upskill" screen (tab or section) and Profile "Ampliar perfil" panel with accept/reject per item showing its source; Tests.

**Interfaces:** Upskill: deterministic gap count (offer keywords from track keyword groups + offer text vs profile skills) → top gaps; AI (if available) adds study plan + resources (resources only as names/URLs the model gives, marked "sin verificar"); Markdown saved to `JH_HOME/reports/upskill-<date>.md`. Expand: for each URL, `fetch_page` (robots) → GitHub: repos/languages via public API `https://api.github.com/users/<u>/repos` (GET, no token) when the URL is a GitHub profile; others: page text → AI JSON `{skills:[{name, evidence, source_url}]}`; nothing saved until accepted.

- [x] Tests: gap counting deterministic; report written; expand proposals carry source; accept merges without duplicates; no network (mock fetch).
- [x] Commit `feat(profile): mapa de huecos (upskill) y ampliación del perfil con fuentes`.

### Task 9: Custom templates (add-template)

**Files:** Create `backend/automation/templates_registry.py`; Modify `document_generator`/`application_documents` to use the active template; API `GET /api/templates`, `POST /api/templates` (upload a zip or a .tex.j2/.typ.j2 + meta: name, kind cv|letter, engine latex|typst, compile_cmd optional, page_limit, style_rules), `POST /api/templates/{name}/activate`, `DELETE`; Profile UI selector; Tests.

**Interfaces:** Templates live in `JH_HOME/templates/<kind>/<name>/` with `template.json`; registering runs a mandatory test compile with `profile.example.json` (fail → not registered, error returned); Typst requires `typst` on PATH (409 otherwise); built-ins `moderncv-banking` (cv) and `cover-cls` (letter) always listed; active selection stored in `jobhunter.yaml` `documents: {cv_template, letter_template, cv_pages: 2, letter_pages: 1}` (new config section, defaults = built-ins).

- [x] Tests: register valid template (skip w/o engine), invalid one rejected, zip path traversal blocked, activate changes the template used.
- [x] Commit `feat(templates): plantillas propias de CV y carta con compilación de prueba`.

### Task 10: Frontend wiring for applications

**Files:** `frontend/app/components/PendingCard.tsx`, applications tab, offer detail, `frontend/lib/api.ts`, types; Tests.

**Interfaces:** PendingCard: "Preparar candidatura" (toggle "con IA" when provider ≠ none) → shows status, warnings, verification summary (pages, missing keywords) and links to open `cv.pdf`/`cover.pdf`; "Aprobar y enviar" states which attachments will be sent. Offer detail: "Evaluar con IA", "Investigar empresa", evaluation panel. Screening answers panel per application. All errors surfaced.

- [x] Tests: helpers + static markup + happy-dom click tests where behaviour matters.
- [x] Commit `feat(frontend): preparar candidatura, evaluación e investigación desde el dashboard`.

### Task 11: Claude Code commands/agents adapted + attribution

**Files:** `.claude/commands/{apply,rank,add-template,add-portal,expand,upskill}.md`, `.claude/agents/{posting-fetcher,posting-scorer,application-reviewer}.md`, skills referencing stale paths; `ATTRIBUTION.md`, `NOTICE`; Test `backend/tests/test_claude_commands.py`.

**Interfaces:** Each command uses this repo's real paths and CLIs: `JH_HOME/profile.json`, the DB via `backend/` modules (provide thin CLIs: `python -m automation.application_documents prepare <id> [--ai]`, `python -m automation.offer_evaluation <offer_id>`, `python -m automation.upskill`, `python -m automation.expand_profile <url>`, `python -m automation.templates_registry add …`); `add-portal` generates a scraper following `.claude/rules/scrapers.md` + `skills/new-scraper` with a sample-data test (the source registry contract arrives in SP4 — reference it as "if `backend/scraper/sources/` exists use its contract"). Remove references to `job_scraper/seen_jobs.json`, `salary_lookup.py`, markdown candidate profile, Danish portals.
- Test: parse every `.claude/commands/*.md` and `.claude/agents/*.md`, extract backtick paths/`python -m` modules and assert each exists/imports; assert no `seen_jobs.json`/`salary_lookup` strings.
- Attribution rows for `document_generator`, `latex_compiler`, `application_archive`, `eligibility_gate`, LaTeX templates, new derived modules.

- [x] Commit `docs(claude): comandos y agentes adaptados al repo y atribución completa`.

### Task 12: Finish line

**Files:** `backend/tests/test_sp3_e2e.py`; README/README.es sections ("Preparing an application", templates, Tectonic install hint per OS); CONTRIBUTING (templates, commands).

- [x] E2E (skipped without engine): fresh JH_HOME + wizard-applied profile (invented) + one offer + draft application → `POST /prepare` with `use_ai=false` → CV 2 pages / letter 1 page, `verify_pdf` passes; with `use_ai=true` and a scripted fake provider → same; approve with fake SMTP → email has both PDFs from the archive. Without engine → 409 path tested always.
- [x] Docs; all suites green; commit `test(sp3): candidatura completa con y sin IA`.
