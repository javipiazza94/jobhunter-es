# Bandeja de entrada (`inbox/`)

JobHunter puede incorporar ofertas y candidaturas encontradas o tramitadas fuera de los scrapers mediante ficheros de texto plano en `JH_HOME/inbox/` (o `JH_INBOX_DIR`). Los ficheros los puedes escribir a mano, con n8n o con cualquier agente que solo sepa dejar ficheros.

Reglas comunes a los dos formatos:

- Codificación UTF-8, una entrada por línea, campos separados por `|`.
- Las líneas vacías y las que empiezan por `#` se ignoran (salvo las cabeceras de sección de candidaturas, ver abajo).
- El título/puesto puede contener `|`: los cargadores leen los campos fijos desde el principio y desde el final.
- Nada se envía nunca: los cargadores solo escriben en la base de datos.
- Con `--save`, el fichero cargado se **borra**; se conserva si tiene líneas que no se han podido cargar.

## Carga automática

Mientras la API está encendida, el vigilante `backend/inbox_watcher.py` recoge los ficheros al arrancar y cada 60 s (`JH_INBOX_POLL_SECONDS`, `0` = desactivado), hace una copia de la BD (`backups/` junto a la BD; por defecto `JH_HOME/backups/`) y ejecuta el cargador con `--save`:

| Patrón de fichero      | Cargador                                    |
|------------------------|---------------------------------------------|
| `candidaturas_*.txt`   | `backend/scripts/load_inbox_applications.py` |
| `ofertas_*.txt`        | `backend/scripts/load_inbox_offers.py`       |

El dashboard avisa de lo que queda sin cargar (`GET /api/inbox/status`); `POST /api/inbox/sync` fuerza una carga.

---

## 1. Ofertas (`ofertas_*.txt`)

### Formato: 8 campos

```text
tipo|título|empresa|ubicación|url|fecha|contrato|nota
```

| # | Campo       | Obligatorio | Descripción |
|---|-------------|-------------|-------------|
| 1 | `tipo`      | sí | Id de un track de tu `jobhunter.yaml` (p. ej. `developer`), o un alias antiguo (ver abajo). Un valor desconocido hace la línea inválida. |
| 2 | `título`    | sí | Título del puesto (puede contener `|`). |
| 3 | `empresa`   | sí | Nombre de la empresa. |
| 4 | `ubicación` | puede ir vacío | Ciudad o modalidad (`Madrid`, `Remoto`, `Híbrido`…). |
| 5 | `url`       | sí | Enlace a la oferta. |
| 6 | `fecha`     | puede ir vacío | Publicación, `AAAA-MM-DD`. Más antigua que `--max-age-days` (60 por defecto) → se descarta. |
| 7 | `contrato`  | puede ir vacío | Tipo de contrato/jornada; se usa para puntuar. |
| 8 | `nota`      | puede ir vacío | Comentario libre; se guarda en la descripción pero no puntúa. |

Una línea con menos de 8 campos o con un `tipo` no reconocido cuenta como «mal formato».

**Valores de `tipo`:**

- Id de un track **estándar** → oferta normal: se puntúa con `scoring` y se marca relevante si supera `min_relevance`.
- Id de un track **aislado** (`kind: isolated`) → se puntúa con las reglas de ese track; si no llega a su `min_score`, se descarta.
- Alias de compatibilidad: `sap` e `ia` → oferta normal; `puente` → primer track aislado de la config (si no hay ninguno, se descarta).

**Deduplicado:** por URL y por empresa + título (dentro del fichero y contra la BD). Si la empresa ya tiene candidaturas, el informe lo indica.

Ejemplo:

```text
developer|Backend Python (FastAPI)|Acme Robotics|Remoto|https://example.test/oferta/1|2026-10-01|indefinido|vista en un portal
```

### Comando (desde `backend/`)

```bash
# Simulacro: muestra qué se cargaría, no guarda nada
python scripts/load_inbox_offers.py <fichero> [<fichero>...]

# Guardar (y borrar los ficheros cargados sin errores)
python scripts/load_inbox_offers.py <fichero> [<fichero>...] --save [--max-age-days 60]
```

El argumento de fichero es obligatorio.

---

## 2. Candidaturas (`candidaturas_*.txt`)

### Formato: 6 campos

```text
fecha|empresa|puesto|email_destino|estado|gmail_thread_id
```

| # | Campo             | Descripción |
|---|-------------------|-------------|
| 1 | `fecha`           | Fecha de la candidatura o del último cambio, `AAAA-MM-DD`. |
| 2 | `empresa`         | Nombre de la empresa. Si no se conoce, `(por confirmar)`: se guarda como «Sin confirmar» y sale en «Por revisar». |
| 3 | `puesto`          | Título del puesto (puede contener `|`). |
| 4 | `email_destino`   | Email al que se envió; vacío si fue por portal. |
| 5 | `estado`          | `sent`, `replied`, `interview`, `offer`, `rejected` o `rejected_manual`. Otro valor → fila inválida. |
| 6 | `gmail_thread_id` | Id del hilo de Gmail, o una clave estable `portal-<slug>` para candidaturas por portal (p. ej. `portal-acme-backend`). |

Una línea con menos de 6 campos es inválida.

**Comportamiento:**

- Si la candidatura ya existe (mismo hilo/clave, o misma empresa y puesto parecido) no se duplica: solo se actualiza el estado, sin bajarlo nunca (`rejected` pisa `sent`/`replied`; `interview` + `rejected` → dudosa).
- Filas sin `gmail_thread_id`: solo actualizan una candidatura existente con coincidencia clara; si no, quedan como dudosas.
- Coincidencias parciales → dudosas (no se crea ni se toca nada). El fichero se conserva hasta resolverlas.
- Cabeceras de sección: una línea `# ===== ... TRABAJO PUENTE` marca las filas siguientes como trabajo puente (track aislado); en una sección `# ===== ... A REVISAR` los comentarios se listan en «Por revisar».

Ejemplo:

```text
2026-10-01|Acme Robotics|Backend Python (FastAPI)|jobs@example.test|sent|portal-acme-backend
```

### Comando (desde `backend/`)

```bash
# Simulacro sobre una copia temporal de la BD (el informe es fiel, la BD real no se toca)
python scripts/load_inbox_applications.py <fichero> [<fichero>...]

# Guardar (y borrar los ficheros cargados sin dudas)
python scripts/load_inbox_applications.py <fichero> [<fichero>...] --save
```

Para añadir una candidatura suelta sin escribir el fichero a mano: `python scripts/add_application.py "Empresa" "Puesto" [--estado sent] [--fecha AAAA-MM-DD]` (la añade a `inbox/candidaturas_manual.txt`).
