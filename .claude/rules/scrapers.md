---
paths:
  - backend/scraper/**
---

# Scrapers

- Patrón de cada portal (referencia: `scraper/infojobs.py`): parser puro (HTML → ofertas, sin red) + test con HTML de muestra + registro en `scraper/runner.py` + scoring. Para añadir uno nuevo o arreglar uno roto → skill `new-scraper` / agente `scraper-fixer`.
- Mantener el parser separado de la capa de red para poder testearlo con HTML guardado.
- No machacar los portales: peticiones extra (fichas de detalle) solo para candidatas por encima de un umbral de score; respetar `rate_gate.py`.
- Nunca guardar sesiones, cookies ni HTML con datos personales en el repo (`backend/sessions/` está en `.gitignore`).
