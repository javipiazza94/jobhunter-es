# Catálogo y Arquitectura de Fuentes de Empleo (Sources)

JobHunter ES cuenta con un sistema modular y autodescubierto de fuentes de empleo bajo `backend/scraper/sources/`. Cada fuente se declara como un módulo independiente mediante un `SourceSpec`.

---

## Tabla de Fuentes Disponibles

| ID | Nombre | Mercados | Tipo | Requiere Aceptación (`ack`) | Atribución Obligatoria | Notas / Requisitos |
|---|---|---|---|---|---|---|
| `tecnoempleo` | Tecnoempleo | `spain`, `remote` | HTML | No | No | Soporta filtrado por provincias y etiqueta "remoto". |
| `infojobs` | InfoJobs | `spain` | HTML | **Sí** | No | Requiere consentimiento explícito sobre condiciones del portal. Desactivada por defecto. |
| `manfred` | Manfred | `spain`, `remote` | JSON / API | No | No | Ofertas tech seleccionadas con condiciones transparentes. |
| `computrabajo` | Computrabajo | `spain`, `latam` | HTML | No | No | Soporta selector de país (`country`: `es`, `mx`, `co`, `ar`, `pe`, `cl`, etc.) y filtrado por localidad. |
| `linkedin` | LinkedIn | `latam`, `remote`, `global` | HTML | **Sí** | No | Requiere aceptación explícita sobre condiciones de automatización. Desactivada por defecto. |
| `remotive` | Remotive | `remote`, `global` | JSON / API | No | **Sí** | API pública de empleo remoto. Enlace obligatorio a la oferta original. |
| `remoteok` | RemoteOK | `remote`, `global` | JSON / API | No | **Sí** | API pública de empleo remoto. Enlace obligatorio y aviso de términos. |
| `arbeitnow` | Arbeitnow | `remote`, `global` | JSON / API | No | No | API pública de empleo remoto y visas patrocinadas en Europa. |
| `freehire` | Freehire | `remote`, `global` | JSON / API | No | No | API pública de puestos remotos sin intermediarios. |
| `indeed` | Indeed | `global` | HTML / API | No | No | Requiere clave `SCRAPERAPI_KEY` configurada en el llavero local o variables de entorno. |
| `company_direct` | Web de empresas | Track directo | HTML | No | No | Ofertas directas de las webs de empleo configuradas por el usuario. |

---

## Arquitectura de Registro (`SourceSpec`)

Cada fuente exporta en su módulo (`backend/scraper/sources/<id>.py`) una instancia o función `spec()` que define:

```python
@dataclass(frozen=True)
class SourceSpec:
    id: str                                  # Identificador único (minúsculas y guiones bajos)
    label: dict[str, str]                    # Nombres en español e inglés: {"es": "...", "en": "..."}
    markets: tuple[str, ...]                 # Subconjunto de: spain, latam, remote, global
    requires_ack: bool                       # Si exige aviso y confirmación explícita del usuario
    default_on: bool                         # Si viene activada por defecto en configuraciones nuevas
    kind: Literal["json", "html", "playwright"]
    attribution: Attribution                 # Nombre, URL y si es obligatoria en la interfaz
    params: dict[str, ParamSpec]             # Parámetros configurables (ej. country, locations)
    run: Callable[[RunContext], ...]         # Función de ejecución del scraper
```

El registro `backend/scraper/sources/__init__.py` descubre dinámicamente todos los módulos del paquete, valida unicidad de IDs y expone catálogos para el Asistente de Configuración (`load_markets`) y la API de Ajustes (`sources_view`).

---

## Mercados Disponibles en el Asistente

El asistente de configuración inicial agrupa las fuentes en 4 mercados estratégicos:

1. **España (`spain`):** Tecnoempleo, InfoJobs, Manfred, Computrabajo España.
2. **Latinoamérica (`latam`):** Computrabajo (con selector de país: Colombia, México, Argentina, Perú, Chile...) y LinkedIn.
3. **Remoto (`remote`):** Tecnoempleo (remoto), Manfred, LinkedIn, Remotive, RemoteOK, Arbeitnow y Freehire.
4. **Global (`global`):** LinkedIn, Remotive, RemoteOK, Arbeitnow, Freehire e Indeed.

---

## Empresas Seguidas sobre Agregadores (`followed_companies`)

En lugar de consultar agresivamente los sitios web individuales de las empresas seguidas (consultoras, agencias o empresas objetivo como Adecco o Manpower), el sistema permite monitorizar sus ofertas directamente sobre los agregadores configurados.

Al definir empresas seguidas en la configuración (`followed_companies`), el runner ejecuta consultas filtradas por empresa sobre las fuentes agregadoras que soportan `company_query: True`, asignando el `followed_tier` correspondiente a las ofertas capturadas.

---

## Parámetros Específicos por Fuente

- **Computrabajo:** `country` (código ISO de dos letras: `es`, `mx`, `co`, `ar`, `cl`, `pe`, `ec`, `uy`, `ve`, `cr`, `pa`, `gt`, `sv`, `hn`, `ni`, `do`). Por defecto: `es`.
- **Tecnoempleo, Indeed y Computrabajo:** `locations` (lista de ubicaciones deseadas, ej. `["remoto", "Madrid", "Barcelona"]`).
- **Indeed:** `requires_secret: "scraperapi_key"` (debe almacenarse en el llavero del sistema mediante `python -m secrets_store set scraperapi_key <clave>` o en la variable de entorno `SCRAPERAPI_KEY`).

---

## Cómo Añadir una Nueva Fuente

1. Crea el archivo `backend/scraper/sources/<mi_fuente>.py` definiendo la función `spec() -> SourceSpec`.
2. Añade un fixture de prueba con datos simulados en `backend/tests/fixtures/sources/<mi_fuente>.json` (o `.html`).
3. Añade los tests correspondientes en `backend/tests/` asegurando que no se realizan conexiones externas reales de red.
4. El registro descubrirá automáticamente la fuente sin requerir modificaciones en el runner, el asistente ni la interfaz.
