---
name: run-pipeline
description: "Runs the job-hunter-spain scraping-to-application pipeline end-to-end (seed load, Tecnoempleo scraping, contact extraction, application drafts/sending/form-fill), and covers one-time Gmail/CV/profile setup needed before sending. Use when asked to scrape jobs, extract contacts, or send/review job applications in this repo."
---

## Flujo completo

```bash
# 1. Cargar seed (50 empresas del repo companies-with-public-salary)
cd backend && python -m scraper.runner --source seed

# 2. Scraping de Tecnoempleo (dry-run primero)
python -m scraper.runner --source tecnoempleo --dry-run
python -m scraper.runner --source tecnoempleo --max-pages 3

# 2b. Pipeline multi-portal de un track definido en jobhunter.yaml (Tecnoempleo, InfoJobs, Computrabajo, webs de empresa, LinkedIn)
python -m scraper.runner --track sap --max-pages 2
# Cada --track ejecuta solo las búsquedas de LinkedIn con `track:` igual al suyo (las que no declaran track, en todos).
# Para las búsquedas de IA/desarrollo de LinkedIn lanza también: python -m scraper.runner --track ia_dev

# 3. Extraer emails y formularios de webs de empresas
python -m scraper.runner --source contacts

# 4. Ver candidaturas pendientes (dry-run)
python -m automation.application_engine --dry-run

# 5. Enviar candidaturas (límite diario: MAX_EMAILS_PER_DAY en config.py; delays automáticos)
python -m automation.application_engine --limit 10

# 6. Rellenar formularios de candidatura (SuccessFactors / genérico) — nunca envía
python -m automation.application_engine fill-forms --dry-run
python -m automation.application_engine fill-forms
```

## `fill-forms`

El comando `fill-forms` nunca envía la candidatura por ti: detecta el ATS por la URL
(`workday` | `greenhouse` | `lever` | `successfactors` | `generic`), rellena los campos
que reconoce a partir de `profile.json`, sube el CV correspondiente y avanza los pasos
intermedios del asistente — pero se para en la pantalla final para que la revises y la
envíes tú mismo/a. Cada formulario rellenado queda registrado en `applications` con
`method='form'` y `status='form_filled_pending_review'`.

## Antes de enviar emails

1. Añade tu App Password de Gmail en `.env`:
   - Ve a myaccount.google.com/apppasswords
   - Crea password para "Job Hunter Spain"
   - Pon el valor en `GMAIL_APP_PASSWORD`
2. Copia tus CVs a `data/cv/` con los nombres de `profile.json` (`cv_ia_path`, `cv_sap_path`, `cv_sap_modules`…)
3. `mkdir -p data && cp backend/profile.example.json data/profile.json` y completa tus datos — `profile.json` está en `.gitignore` porque incluye DNI y fecha de nacimiento (los pide SuccessFactors)
