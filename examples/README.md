# Ejemplos de configuración

Cada fichero es un `jobhunter.yaml` completo y válido. Para usar uno:

```bash
mkdir -p data && cp examples/developer.yaml data/jobhunter.yaml   # o $JH_HOME/jobhunter.yaml
```

| Fichero | Perfil |
|---|---|
| `developer.yaml` | Desarrollador genérico (Madrid) |
| `sap-consultant.yaml` | Consultor SAP (Madrid, sin empresas seguidas) |
| `data-ai.yaml` | Datos / IA (Barcelona) |

Reglas:
- Los pesos de `scoring` (todos los `keyword_groups` + `location` + `experience` + `salary`) suman 1.0.
- Cada `track` estándar es una pestaña del dashboard; el `id` solo admite `[a-z][a-z0-9_]*`.
- Si el YAML es inválido, la API no arranca y el error indica fichero, campo y motivo.
- Lanza el buscador de un track con `python -m scraper.runner --track <id>`.
