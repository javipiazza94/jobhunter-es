# Operations and technical details

[Leer en español](operacion.md)

This document collects the operational details that do not fit in the [README](../README.md): local API security, scraping jobs, the inbox, the database schema and scoring tuning. To start using JobHunter ES, read the README first.

## Local API security

The API has no login, so it only listens on `127.0.0.1`, only serves requests whose `Host` is `localhost`/`127.0.0.1` (configurable with `ALLOWED_HOSTS`) and requires the `X-JH-Client: dashboard` header on `POST`/`PUT`/`PATCH`/`DELETE`. If you call the API with `curl` or a script, add that header. Each source of `POST /api/scraper/run` waits `SCRAPER_COOLDOWN_SECONDS` (300 by default) between runs and cannot be started twice at once. Details and reasoning: [docs/adr/0001-proteccion-de-la-api-local.md](adr/0001-proteccion-de-la-api-local.md).

## Jobs, inbox, schema and API contract

- `POST /api/scraper/run` starts each source as a separate process (`python -m scraper.jobs <source>`) with a time limit (`JOB_TIMEOUT_SECONDS`, 1800 s by default). Its status and the last log lines are available at `GET /api/jobs` and `GET /api/jobs/{id}`. The state lives in the API process.
- **Inbox (n8n):** files dropped in `data/inbox/` (`candidaturas_*.txt`, `ofertas_*.txt`) are loaded by the API itself: at startup and every 60 s (`JH_INBOX_POLL_SECONDS`, 0 = disabled), after backing up the database (`data/backups/job_hunter.db.bak-auto-<date>`, the last 10 are kept). The loaders deduplicate, never move a status backwards and leave doubtful rows in the file. The dashboard refreshes by itself and warns about what is still unloaded (`GET /api/inbox/status`; `POST /api/inbox/sync` forces a load). The `inbox` (dry run) and `inbox-apply` jobs remain available through `POST /api/scraper/run`. To test without touching your data, point `JH_DB_PATH` and `JH_INBOX_DIR` to a copy of the database and a temporary inbox. File format: [inbox.md](inbox.md).
- The database is versioned (`PRAGMA user_version`). To change the schema, add a `_migration_00N_…` function at the end of `MIGRATIONS` in `backend/database.py` and do not edit the existing ones; each runs once and atomically.
- The API models live in `backend/schemas.py`; `backend/tests/test_api_contract.py` checks that the types in `frontend/lib/types.ts` stay in sync with them.

## Isolated tracks (bridge jobs)

An isolated track (bridge job) keeps its searches in `search_keywords` and `remote_search_keywords` (the latter are searched as "<word> teletrabajo"); the locations of that search are in `sources.generic`.

## Custom templates: security

**A template can read files on your computer and put them in the PDF you send: install only templates from sources you trust.** Registering one requires an explicit confirmation (`trusted`; a checkbox in the dashboard, `--trusted` in the CLI). As a safety net, custom templates render in a sandboxed Jinja environment, every `((( value )))` is escaped by default (`|safe_raw` opts out), and compilers run without shell-escape. For custom LaTeX templates xelatex is preferred and runs with kpathsea in paranoid mode (`openin_any=p`, `openout_any=p`: no absolute or `..` paths); lualatex is not used for them (`\directlua` reads files outside kpathsea); **Tectonic does not confine file reads**, so it is used for custom templates only when xelatex is not installed, and "Prepare application" then warns about it. A custom template's files are copied into their own subfolder without following symlinks and cannot use the built-ins' reserved names (`cover.cls`, `OpenFonts/`...); rendering is capped in size and time. Typst runs with `--root` on the work folder. `latexmkrc`/`texmf.cnf` files are dropped, and a best-effort lint over every text file of the template rejects `\input`/`\include`/`\openin`/`\read`/`\includegraphics`... with absolute, `~` or `..` paths, `\@@input`, `\let` aliases and macro-built paths of read commands, `\directlua`/`luacode`, `\write18`, `\catcode` changes and `\csname`-built read commands (it is not a complete barrier).

## Scoring and limits tuning

Thresholds, weights, keywords, tracks and scraper parameters live in `jobhunter.yaml` (`min_relevance`, `keyword_groups`, `tracks`, `sources`…). Operating limits (`MAX_EMAILS_PER_DAY`, `RECONTACT_COOLDOWN_DAYS`…) remain in `backend/config.py`. To run the search of one track: `python -m scraper.runner --track <id>`. Scoring tuning guide: `CLAUDE.md`.

## Database

SQLite at `data/job_hunter.db` (inside `JH_HOME`, ignored by git; `JH_DB_PATH` redirects it).

| Table | Contents |
|-------|----------|
| `companies` | Companies with URL, city, sector |
| `job_offers` | Offers with score, cv_profile, description; `job_kind='generic'` = bridge job (isolated from normal scoring) |
| `contacts` | Extracted emails and forms |
| `applications` | Drafts and sent applications (status, cover_letter_edited, approved_at) |
| `company_contact_history` | Contact history used for the cooldown |
