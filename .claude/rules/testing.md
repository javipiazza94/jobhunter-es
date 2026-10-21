---
paths:
  - backend/**/*.py
  - backend/tests/**
---

# Testing y estilo (backend)

- Mismo check que el CI, desde `backend/`: `ruff check --config ../ruff.toml .` y `python -m pytest -q`. La skill `test` lo corre todo (backend + frontend).
- Todo parser/scraper/clasificador nuevo lleva test en `backend/tests/` con datos de muestra, no con peticiones reales.
- El hook `.claude/hooks/ruff-check.sh` avisa de errores de ruff tras cada Write/Edit de un `.py`; corregirlos antes de seguir.
- Código y nombres en inglés; mensajes de commit y textos al usuario en español.
