# Job Hunter Spain

Sistema de automatización de candidaturas tech en España. La búsqueda, el scoring y los tracks se configuran en `JH_HOME/jobhunter.yaml` (por defecto `data/`, ver `examples/`).

Arranque, puertos (API 8020, dashboard 3010), instalación y arquitectura → `README.md`.
Flujo de scraping/candidaturas y setup de Gmail/CVs → skill `run-pipeline` (`.claude/skills/run-pipeline/SKILL.md`).
Trabajo con bandeja de entrada (inbox de ofertas, reglas) → `docs/inbox.md`.
Preparar una entrevista de una candidatura → skill `interview` (`.claude/skills/interview/SKILL.md`).
Seguimiento de candidaturas sin respuesta (recordatorios, cerrar como `no_response`) → `automation/followup.py`, pestaña «Seguimiento». Solo propone: nunca envía.

## Filter engine y scrapers

Scoring (`automation/filter_engine.py::score_offer`), pesos (`scoring:` de `jobhunter.yaml`, única fuente de verdad, suman 1.0), ficha completa de Tecnoempleo y qué editar → `.claude/rules/filter-engine.md` (se carga al tocar esos ficheros). Convenciones de scrapers → `.claude/rules/scrapers.md`; tests/estilo → `.claude/rules/testing.md`.

Prioridad de scoring: los `keyword_groups` y pesos que defina el usuario en `jobhunter.yaml`. Tamaño de empresa indiferente.

Datos del usuario (BD, inbox, backups, logs, CVs, `profile.json`) → `JH_HOME` (`config.py`: `DB_PATH`, `INBOX_DIR`, `PROFILE_PATH`…); nunca rutas relativas a `backend/`. Los tracks (pestañas, CV, plantilla, scrapers) salen de `search_config.get_config()`; buscar por track: `python -m scraper.runner --track <id>`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
