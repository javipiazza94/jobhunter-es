# Atribución y Licencias de Terceros

Este proyecto (`jobhunter-es`) incorpora código, ideas y recursos portados de repositorios de código abierto, conforme a sus respectivas licencias:

---

## 1. ai-job-search

Parte de los módulos de automatización, verificación de PDFs, comprobación de robots, protección contra inyección de prompts, plantillas LaTeX y comandos/agentes de Claude Code han sido portados o adaptados del repositorio:

- **Repositorio:** [https://github.com/MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)
- **Commit fijado de sincronización:** `e16acee` (2026-10-21)
- **Licencia:** MIT License

### Texto de la Licencia MIT (`ai-job-search`):

```text
MIT License

Copyright (c) 2026 Mads Lorentzen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Componentes portados o adaptados de `ai-job-search`:

| Componente local | Archivo original upstream | Descripción |
|---|---|---|
| `backend/automation/posting_guard.py` | `tools/posting_guard.py` | Filtro de integridad de ofertas, desofuscación Unicode y detección de inyecciones |
| `backend/automation/job_key.py` | `tools/job_key.py` | Generación de clave canónica `company:role` para deduplicación |
| `backend/automation/page_decode.py` | `tools/page_decode.py` | Decodificación robusta de páginas HTML/texto |
| `backend/automation/robots_check.py` | `tools/robots_check.py` | Cumplimiento de RFC 9309 (`robots.txt`) previo a fetch |
| `backend/automation/fetch_page.py` | `tools/fetch_page.py` | Reintento de fetch con cabeceras de navegador |
| `backend/automation/verify_pdf.py` | `tools/verify_pdf.py` | Verificación de capas de texto ATS y conteo de páginas |
| `backend/automation/verify_layout.py` | `tools/verify_layout.py` | Medición de cajas delimitadoras y maquetación de PDFs |
| `backend/automation/rank_state.py` | `tools/rank_state.py` | Triage y ordenación de ofertas adaptado a SQLite (rutas de `config`, puntuaciones en `offer_evaluations`) |
| `backend/automation/offer_evaluation.py` | `.claude/commands/rank.md`, `.claude/agents/posting-scorer.md`, `.claude/skills/job-application-assistant/04-job-evaluation.md` | Evaluación con IA de una oferta en la app (rúbrica, pesos y bandas de `/rank`) |
| `backend/automation/company_research.py` | `company_research/` | Caché con TTL de 30 días para datos de empresa |
| `backend/automation/company_researcher.py` | `.claude/skills/job-application-assistant/09-web-research.md` | Investigación de empresa con lectura de la web (robots) y caché compartida; reescrita sobre `backend/ai` |
| `templates/latex/cover_letters/cover.cls` | `cover_letters/cover.cls` | Clase de documento para cartas de presentación |
| `.claude/commands/` | `.claude/commands/` | Comandos `/apply`, `/rank`, `/expand`, `/add-template`, `/add-portal` |
| `.claude/agents/` | `.claude/agents/` | Agentes `posting-fetcher`, `application-reviewer`, `posting-scorer` |
| `.claude/skills/job-application-assistant/` | `.claude/skills/job-application-assistant/` | Guías de redacción, estilo, evaluación y research |
| `backend/automation/document_generator.py` | `cv/` & `cover_letters/` | Generación determinista de CV y carta en LaTeX, escape riguroso, formateo de fechas y recorte a límite de páginas |
| `backend/automation/latex_compiler.py` | `tools/` / pipeline LaTeX | Compilación de fuentes LaTeX con Tectonic y fallback a xelatex/lualatex |
| `backend/automation/application_archive.py` | `.claude/commands/apply.md` | Archivo atómico de documentos generados por candidatura (`JH_HOME/applications/<id>/`) |
| `backend/automation/eligibility_gate.py` | `.claude/skills/job-application-assistant/04-job-evaluation.md` | Filtro de elegibilidad (permiso de trabajo, visado, residencia) como requisito duro o aviso |
| `templates/latex/cv/cv.tex.j2` | `cv/main_example.tex` | Plantilla Jinja2 de CV estilo moderncv banking |
| `templates/latex/cover_letters/cover.tex.j2` | `cover_letters/cover_example.tex` | Plantilla Jinja2 de carta de presentación basada en `cover.cls` |
| `backend/automation/application_documents.py` | `.claude/commands/apply.md` | Orquestación de documentos de candidatura con soporte determinista y flujo de IA |
| `backend/automation/templates_registry.py` | `.claude/commands/add-template.md` | Registro, validación, compilación de prueba y activación de plantillas propias (LaTeX/Typst) |
| `backend/automation/screening.py` | `.claude/skills/job-application-assistant/08-application-forms.md` | Respuestas de preguntas de cribado basadas en el perfil |
| `backend/automation/upskill.py` | `.claude/skills/upskill/` | Mapa de huecos de habilidades y plan de estudio a partir de ofertas |
| `backend/automation/expand_profile.py` | `.claude/commands/expand.md` | Ampliación de competencias del perfil a partir de fuentes públicas (GitHub, web) |
| `backend/automation/ai_documents.py` | `.claude/commands/apply.md`, `.claude/agents/application-reviewer.md`, `.claude/skills/job-application-assistant/0[3-6]-*.md` | Prompts del redactor y del revisor (reglas de honestidad, recorte y cobertura de keywords) derivados del flujo `/apply` |

---

## 2. Tipografías Lato y Raleway (SIL Open Font License 1.1)

Las plantillas LaTeX de cartas de presentación (`templates/latex/cover_letters/OpenFonts/fonts/`) incluyen las familias tipográficas Lato y Raleway:

- **Lato:** Copyright (c) 2010-2014 por tyPoland Lukasz Dziedzic ([http://www.latofonts.com](http://www.latofonts.com)).
- **Raleway:** Copyright (c) 2010 por Matt McInerney ([http://theleagueofmoveabletype.com](http://theleagueofmoveabletype.com)), con añadidos de Pablo Impallari y Rodrigo Fuenzalida.
- **Licencia:** SIL Open Font License, Version 1.1 (texto disponible en `templates/latex/cover_letters/OpenFonts/OFL.txt`).
