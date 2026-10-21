---
name: test
description: Corre en local lo mismo que el CI (ruff + pytest del backend; tsc + lint + bun test del frontend) y resume los fallos. Úsalo antes de commitear o tras tocar código.
disable-model-invocation: true
argument-hint: "[backend|frontend|all]"
---

Ejecuta según `$ARGUMENTS` (por defecto `all`). Para cada bloque, corre los comandos tal cual y resume solo lo que falle (fichero:línea + causa probable); no pegues el log entero.

**backend** (desde `backend/`):
```bash
ruff check --config ../ruff.toml .
python -m pytest -q
```

**frontend** (desde `frontend/`):
```bash
bunx tsc --noEmit
bun run lint
bun test
```

Reglas:
- Si falta `ruff`: `uv tool install ruff`. Si falta el venv, usa `backend/.venv/bin/python -m pytest -q`.
- No arregles nada sin que lo pida el usuario; solo informa. Termina con una línea: `✅ todo verde` o `❌ N fallos en <bloque>`.
- Los tests usan `profile.example.json` y BDs temporales: nunca tocan `profile.json` ni `job_hunter.db`.
