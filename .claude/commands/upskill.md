# /upskill - Análisis de brechas de habilidades y plan de aprendizaje

Invoca la skill `upskill` para analizar las brechas de competencias entre tu perfil (`data/profile.json`) y las ofertas guardadas o candidaturas en la base de datos `data/job_hunter.db`.

## Instrucciones

1. Lee tu perfil técnico desde `data/profile.json` (sección `stack` y `experience`).
2. Consulta las ofertas relevantes en `data/job_hunter.db` o las ofertas bajo `data/applications/`.
3. Compara las tecnologías demandadas con tu stack actual para identificar:
   - Tecnologías clave que dominas (puntos fuertes).
   - Tecnologías adyacentes de rápida adquisición.
   - Brechas importantes recurrentes en las ofertas objetivo.
4. Genera un plan de estudio y recursos recomendados en Markdown en `data/reports/upskill_plan.md`.
