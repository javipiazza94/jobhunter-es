---
paths:
  - backend/automation/filter_engine.py
  - backend/automation/generic_filter.py
  - backend/automation/experience_classifier.py
  - backend/automation/location.py
  - backend/config.py
  - backend/scraper/tecnoempleo.py
---

# Tuning del filter engine

El scoring (`automation/filter_engine.py::score_offer`) pondera las categorías con los pesos de `scoring:` en `jobhunter.yaml` (`JH_HOME/jobhunter.yaml`, o `backend/defaults/jobhunter.yaml` si no existe; única fuente de verdad, deben sumar 1.0 entre grupos de keywords, location, experience y salary). Ejemplo de configuración:

1. `keyword_groups` — grupos de tecnologías principales y secundarias
2. `location` — remoto o ciudad objetivo = máxima puntuación; presencial/híbrido fuera puntúa según la configuración
3. `experience` — prioridad según años configurados (`scoring.experience`, `experience_classifier.classify_experience`)
4. `salary` — base ≥ `scoring.salary.min_base`

El tamaño de empresa no se puntúa (indiferente).

**Filtro de idiomas** (`automation/language_gate.py`, idiomas y niveles de `profile.json`): una oferta que *exige* un idioma que no tienes puntúa 0, como un negativo; si pide más nivel del tuyo (inglés C1 con tu B2) solo deja un aviso. "Valorable" o "nice to have" no cuentan. Los avisos, junto con los de `automation/posting_guard.py` (texto oculto o instrucciones a una IA dentro de la oferta), se guardan en `job_offers.review_flags` desde `automation/offer_review.py`, que es el único punto de entrada para scrapers e inbox.

## Ficha completa (Tecnoempleo)

`scraper/tecnoempleo.py` primero scrapea los listados (título/ubicación/salario/descripción corta) y calcula un score preliminar. Para las ofertas que superen `detail_fetch_min_score` (0.30 por defecto), pide además la ficha completa de la oferta (`TecnoempleoScraper.fetch_offer_detail`), que aporta:
- Descripción completa (vía JSON-LD `JobPosting`, con fallback a `div[itemprop="description"]`)
- `tech_stack` real (tags de la ficha, no solo texto libre)
- `experience_level` y `contract_type` normalizados desde el sidebar "Experiencia"/"Tipo contrato" (reutiliza `automation.experience_classifier`)
- `posted_date` (JSON-LD `datePosted`)
- Salario si el JSON-LD trae `baseSalary` (raro en Tecnoempleo)

Solo se pide ficha completa a las candidatas (no a todas) para no machacar el sitio con una petición extra por oferta. Subir `detail_fetch_min_score` en `jobhunter.yaml` para ser más selectivo (menos peticiones, más rápido); bajarlo para enriquecer más ofertas a costa de más tiempo/peticiones.

## Qué editar

En `jobhunter.yaml` (`scoring:`), no en `config.py`:
- `keyword_groups`: grupos de keywords con su `weight` (añadir/quitar keywords o grupos)
- `location` (`city`, `area`, `*_score`), `experience` (`scores`), `salary` (`min_base`): reglas de cada categoría
- `min_relevance`: bajar a 0.45 para más resultados, subir a 0.65 para más precisión
- `negative_keywords` / `negative_title_keywords`
- `tracks`: `classify_keywords` de cada track estándar (`classify_track`) y reglas `isolated` del track de trabajo puente (`score_isolated`); `profile_confidence_threshold` en `scoring`

En `backend/config.py` (solo límites de operación y rutas):
- `MAX_EMAILS_PER_DAY`: límite diario de envíos
- Keywords y ubicaciones de cada scraper: `sources:` y `search_keywords` de cada track en `jobhunter.yaml`
