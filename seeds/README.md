# Semillas de empresas (`seeds/`)

Este directorio contiene listas de empresas de referencia para inicializar la base de datos de JobHunter.

## `companies_public_salary.json`

Lista curada y generalizada de empresas del sector tecnológico (principalmente en España y con vacantes remotas o internacionales) conocidas por publicar salarios en sus ofertas o disponer de portales de empleo públicos.

### Campos de cada registro

- `name`: Nombre comercial de la empresa.
- `careers_url`: URL directa al portal de empleo o página de vacantes (Lever, Greenhouse, Ashby, Workable o web propia).
- `website`: Sitio web corporativo.
- `sector`: Sector de actividad (p. ej. `data`, `fintech`, `saas`, `edtech`).
- `country`: Código de país ISO de su sede o principal centro de operaciones (`ES`, `US`, `DE`, etc.).

### Uso

Para cargar estas empresas en la base de datos local:

```bash
python -m scraper.runner --source seed
```

El cargador insertará las empresas que no existan previamente sin sobrescribir las existentes ni sus contactos.

### Personalización

Puedes editar este archivo o añadir tus propias empresas siguiendo la misma estructura JSON antes de ejecutar la carga inicial.
