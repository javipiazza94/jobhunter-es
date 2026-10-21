# Job Hunter Spain — Review Queue & Profile Classification

**Date:** 2026-06-25  
**Status:** Approved by user  
**Scope:** Capa de calidad sobre el pipeline existente — clasificación de perfil, cola de revisión humana, deduplicación, historial persistente, variación de cover letter.

---

## Context

Pipeline actual: `scraper → filter → envío directo`. Funciona pero no tiene revisión humana ni discriminación SAP/IA. Con dos CVs y dos perfiles profesionales distintos, el riesgo de enviar el CV incorrecto o recontactar a una empresa es alto. Este spec añade control de calidad sin romper lo que ya funciona.

Base:
- Backend FastAPI :8020, SQLite `job_hunter.db`
- Frontend Next.js :3010, 380 líneas en `app/page.tsx`
- 4 tablas: companies, job_offers, contacts, applications
- `MAX_EMAILS_PER_DAY=20`, delays 30-120s

---

## 1. Clasificación de perfil (sap / ia_dev / manual_review)

### Dónde

**`config.py`** — Dos listas separadas nuevas:

```python
SAP_PROFILE_KEYWORDS = [
    "sap", "abap", "btp", "s/4hana", "s4hana", "hana", "fiori",
    "sap ps", "sap mm", "sap sd", "sap fi", "sap co", "sap pp",
    "successfactors", "rise with sap", "sap public cloud",
    "consultor funcional", "consultor sap", "sap consultant",
    "erp", "sap cloud"
]

IADEV_PROFILE_KEYWORDS = [
    "python", "fastapi", "django", "react", "next.js", "nextjs",
    "typescript", "javascript", "llm", "machine learning", "ml",
    "data scientist", "data engineer", "ai engineer", "ia",
    "inteligencia artificial", "full stack", "fullstack",
    "backend developer", "frontend developer", "devops",
    "automatización", "scraping", "playwright", "rag", "llm"
]

PROFILE_CONFIDENCE_THRESHOLD = 0.2  # diferencia mínima para clasificar
```

Eliminar el `SAP_KEYWORDS` duplicado de `application_engine.py` (ya está en config.py).

**`automation/filter_engine.py`** — Nueva función `classify_profile()`:

```python
def classify_profile(offer: dict) -> tuple[str, float]:
    """
    Returns (profile, confidence).
    profile: "sap" | "ia_dev" | "manual_review"
    confidence: 0.0-1.0 (difference between SAP score and IA/dev score)
    """
```

Lógica:
- Suma hits SAP keywords en title+description (normalizado a 0-1)
- Suma hits IA/dev keywords en title+description (normalizado a 0-1)
- Si diferencia < PROFILE_CONFIDENCE_THRESHOLD → "manual_review"
- Si sap_score > iadev_score → "sap"
- Si iadev_score >= sap_score → "ia_dev"

**`database.py`** — Migración inline: añadir `cv_profile TEXT DEFAULT NULL` a `job_offers`. Se ejecuta en `init_db()` con `ALTER TABLE IF NOT EXISTS` pattern (SQLite compatible).

**`automation/application_engine.py`** — Reemplazar `_cv_path()` por función que lee `offer["cv_profile"]` en vez de recalcular. Si `cv_profile == "manual_review"` → skip (log + skip).

### Resultado visible

Cada oferta en el dashboard muestra badge `SAP` | `IA/Dev` | `Revisar` junto al relevance score.

---

## 2. Cola de revisión humana

### Paradigma nuevo

El application engine deja de enviar directamente. Genera **borradores** (`status='pending_approval'`). El envío real solo ocurre tras aprobación explícita desde el dashboard.

### Schema: tabla `applications`

Añadir dos columnas:
- `cover_letter_edited TEXT` — versión editada por el usuario (NULL si no editó)
- `approved_at TEXT` — timestamp de aprobación (NULL hasta aprobar)
- `cv_profile TEXT` — "sap" | "ia_dev" | "manual_review" (desnormalizado para acceso rápido)

El campo `status` ya existe; nuevos valores operativos:
- `pending_approval` — borrador generado, esperando revisión
- `rejected_manual` — rechazado por el usuario desde el dashboard
- `sent` — enviado (ya existía)
- `replied` / `interview` / `rejected` / `withdrawn` — estados post-envío (ya existían)

### `automation/application_engine.py`

Nueva función pública `create_drafts(limit=None)`:
1. Para cada oferta relevante con contacto y sin application existente:
   a. `cv_profile == "manual_review"` → skip
   b. Dedup: `company_id + contact.value` en applications de los últimos `RECONTACT_COOLDOWN_DAYS` → skip
   c. `generate_letter()` → cover_letter
   d. INSERT applications `status='pending_approval'`, `cover_letter_used=`, `cv_profile=`, `contact_id=`
2. Returns `dict(drafts_created, skipped_manual_review, skipped_duplicate)`

Función existente `run_applications()` → renombrar a `_send_approved(application_id)`: lee una application por ID, envía, actualiza status.

### `main.py` — Endpoints nuevos

| Método | Path | Acción |
|--------|------|--------|
| `POST` | `/api/applications/create-drafts` | Genera borradores (no envía) |
| `GET` | `/api/applications/pending` | Lista `status=pending_approval` con cover letter |
| `POST` | `/api/applications/{id}/approve` | Aprueba → envía → status=sent |
| `PATCH` | `/api/applications/{id}/cover-letter` | Guarda edición antes de aprobar |
| `POST` | `/api/applications/{id}/reject` | status=rejected_manual |

El endpoint existente `POST /api/applications/run` → redirigir a `create-drafts` (no envía).

### Frontend — tab "Pendientes"

Nuevo tab entre "Candidaturas" y los actuales. Cada tarjeta:
- Header: empresa + badge perfil (SAP/IA/Dev) + score + email destino
- Body: textarea con cover letter (editable, guarda on blur o botón "Guardar cambios")
- Footer: `[Rechazar]` `[Aprobar y enviar]`
- Badge CV: `cv_ia.pdf` | `cv_sap.pdf` (no editable desde UI, se selecciona automáticamente)
- Estado vacío si no hay pendientes: "No hay candidaturas pendientes de revisión."

---

## 3. Deduplicación y seguimiento

### Dedup

`get_pending_offers()` en `database.py` → añadir exclusión:

```sql
AND NOT EXISTS (
    SELECT 1 FROM applications a
    JOIN contacts ct ON a.contact_id = ct.id
    WHERE a.company_id = jo.company_id
      AND ct.value = (SELECT value FROM contacts WHERE id = a.contact_id)
      AND a.sent_at > datetime('now', '-' || ? || ' days')
      AND a.status NOT IN ('rejected_manual', 'pending_approval')
)
```

**`config.py`**: `RECONTACT_COOLDOWN_DAYS = 180`

### Dashboard metrics

`GET /api/stats/dashboard`:
```json
{
  "sent_this_week": 3,
  "pending_approval": 7,
  "sap_ratio": 0.4,
  "ia_dev_ratio": 0.6,
  "response_rate": 0.15,
  "total_sent": 20
}
```

---

## 4. Rate limiting + variación de cover letter

**`config.py`**: `MAX_EMAILS_PER_DAY = 15` (bajamos de 20).

**`automation/cover_letter.py`** — Añadir `_pick_variant(variants: list[str], seed: str) -> str` que usa `hash(seed) % len(variants)` (determinista por empresa+oferta, no aleatorio puro para reproducibilidad).

**`templates/cover_letter_tech.j2`** — Añadir bloques de variantes:
```jinja
{% set intros = [...3 variantes...] %}
{% set closings = [...3 variantes...] %}
```
La función `generate()` recibe `variant_seed = company_name + (job_title or "")` y pasa la variante seleccionada al template.

**`templates/cover_letter_sap.j2`** — Nueva plantilla para perfil SAP con lenguaje orientado a consultoría funcional / gestión de proyectos ERP.

---

## 5. Historial persistente

### Nueva tabla `company_contact_history`

```sql
CREATE TABLE IF NOT EXISTS company_contact_history (
    id              TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    company_domain  TEXT,
    email_used      TEXT NOT NULL,
    profile_used    TEXT NOT NULL,   -- "sap" | "ia_dev"
    sent_at         TEXT NOT NULL,
    outcome         TEXT DEFAULT 'sin_respuesta',  -- sin_respuesta | respuesta_recibida | entrevista | rechazado
    notes           TEXT,
    application_id  TEXT             -- FK a applications (para trazabilidad)
);
CREATE INDEX IF NOT EXISTS idx_history_company ON company_contact_history(company_name);
CREATE INDEX IF NOT EXISTS idx_history_email ON company_contact_history(email_used);
CREATE INDEX IF NOT EXISTS idx_history_sent ON company_contact_history(sent_at);
```

Esta tabla **nunca se limpia**. Es independiente del ciclo operativo de `applications`.

### Escritura

En `_send_approved()` de application_engine, tras envío exitoso → INSERT en `company_contact_history`.

### Endpoints

| Método | Path | Descripción |
|--------|------|-------------|
| `GET` | `/api/history` | Lista completa con filtros opcionales (company, profile, outcome) |
| `PATCH` | `/api/history/{id}/outcome` | Actualiza outcome manualmente |
| `GET` | `/api/history/export` | Descarga JSON o CSV (query param `format=json|csv`) |

### Export

- JSON: `application/json`, array de objetos
- CSV: `text/csv`, headers en primera fila, `Content-Disposition: attachment; filename=job_hunter_history_YYYY-MM-DD.csv`

Recomendación: exportar periódicamente como backup. El archivo CSV es legible en Excel/Google Sheets para seguimiento manual.

---

## Flujo completo (nuevo)

```
SCRAPER
  └─ score_offer() → relevance_score
  └─ classify_profile() → cv_profile (sap | ia_dev | manual_review)
  └─ upsert_job_offer() → job_offers.cv_profile populated

CONTACT EXTRACTION (sin cambios)
  └─ emails/forms → contacts table

DRAFT GENERATION  →  POST /api/applications/create-drafts
  Para cada oferta relevante + contacto disponible:
  ├─ cv_profile == "manual_review"?  → skip, log
  ├─ company+email contactado en < 180 días? → skip, log
  ├─ generate_letter(variant_seed) → cover_letter (variante determinista)
  ├─ cv_path ← cv_profile
  └─ INSERT applications(status='pending_approval', cv_profile, cover_letter_used)

DASHBOARD — tab "Pendientes"
  ├─ Lista applications(status='pending_approval')
  ├─ [Editar cover letter] → PATCH /api/applications/{id}/cover-letter
  ├─ [Rechazar] → POST /api/applications/{id}/reject → status='rejected_manual'
  └─ [Aprobar y enviar] → POST /api/applications/{id}/approve

APPROVE → POST /api/applications/{id}/approve
  ├─ Comprueba daily limit (≤ 15/día)
  ├─ Usa cover_letter_edited si existe, sino cover_letter_used
  ├─ rate_limited_send() → email enviado
  ├─ UPDATE applications SET status='sent', sent_at=now, approved_at=now
  └─ INSERT company_contact_history

TRACKING (manual desde dashboard)
  └─ PATCH /api/applications/{id}/status
     sent → replied | interview | rejected | withdrawn
  └─ PATCH /api/history/{id}/outcome (para historial permanente)
```

---

## Ficheros modificados (resumen)

| Fichero | Cambio |
|---------|--------|
| `config.py` | SAP/IA keyword lists, PROFILE_CONFIDENCE_THRESHOLD, RECONTACT_COOLDOWN_DAYS, MAX_EMAILS_PER_DAY=15 |
| `database.py` | Migración inline (cv_profile, cover_letter_edited, approved_at, cv_profile en applications); nueva tabla company_contact_history; nueva función get_weekly_stats() |
| `automation/filter_engine.py` | Nueva función classify_profile() |
| `automation/application_engine.py` | create_drafts(), _send_approved(id), eliminar SAP_KEYWORDS local |
| `automation/cover_letter.py` | _pick_variant(), soporte cover_letter_sap template |
| `automation/email_sender.py` | Sin cambios |
| `templates/cover_letter_tech.j2` | Bloques de variantes de intro/cierre |
| `templates/cover_letter_sap.j2` | Nueva plantilla para perfil SAP |
| `main.py` | 7 endpoints nuevos, modificar /api/applications/run |
| `frontend/app/page.tsx` | Tab "Pendientes" con cola de aprobación |

---

## Lo que NO se hace en este spec

- LinkedIn scraper (topic separado, requiere evaluación de API vs scraping)
- InfoJobs scraper (puede ser Fase 2 independiente)
- Form filler Playwright (ya existe como stub, fuera de scope aquí)
- Hunter.io API integration
