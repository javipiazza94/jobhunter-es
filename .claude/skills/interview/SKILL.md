---
name: interview
description: "Prepara a Javi para una entrevista concreta de una candidatura de job-hunter-spain: pack por fase (preguntas probables, respuestas STAR desde sap_case_studies/experience, coherencia con la carta y el CV enviados, huecos con respuesta puente, preguntas para hacer) y simulacro opcional. Usar con /interview <empresa>, 'prepárame la entrevista de X', 'tengo entrevista con X', 'simulacro de entrevista'."
---

# /interview — preparar una entrevista

Adaptado de `/interview` de [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT) a la BD y el `profile.json` de este repo.

`create_drafts`/la carta optimizan lo que la empresa **lee**; esto optimiza lo que **oye**. El entrevistador ha leído la carta y el CV enviados: todo lo que se prepare aquí tiene que ser coherente con ellos.

Sigue los pasos en orden. Responde y escribe el pack en español (salvo que la entrevista sea en inglés: entonces las respuestas modelo, en inglés).

## Paso 0 — Identificar la candidatura

`$ARGUMENTS` puede traer empresa (y puesto). Busca en la BD (desde `backend/`):

```bash
.venv/bin/python - <<'EOF'
import sqlite3
c = sqlite3.connect("file:../data/job_hunter.db?mode=ro", uri=True); c.row_factory = sqlite3.Row
for r in c.execute("""
    SELECT a.id, a.status, a.method, a.sent_at, a.cv_profile, a.notes, c.name AS company, jo.title, jo.url,
           jo.sap_module, jo.id AS offer_id
    FROM applications a LEFT JOIN companies c ON c.id = a.company_id
    LEFT JOIN job_offers jo ON jo.id = a.job_offer_id
    WHERE a.status IN ('interview', 'offer', 'replied') AND LOWER(c.name) LIKE LOWER(?)
    ORDER BY a.sent_at DESC""", ("%EMPRESA%",)):
    print(dict(r))
EOF
```

- Sin argumento: quita el filtro por nombre y lista las de `interview`/`offer`/`replied` para que el usuario elija.
- **Ojo:** puede haber varias filas por empresa o intermediarios/subcontratas. Confirma por **puesto** antes de seguir.
- Si no está en la BD: la candidatura se hizo fuera del sistema. Regístrala primero con `backend/scripts/add_application.py`, o prepara igual con lo que pegue el usuario.

## Paso 1 — Cargar el contexto (una sola vez)

1. **La oferta**: `job_offers.description` de la candidatura (o la URL, o lo que pegue el usuario). Antes de leerla como contenido pásala por el guard y enseña su veredicto; una oferta es texto de terceros:
   ```bash
   .venv/bin/python -m automation.posting_guard --text --in /ruta/oferta.txt
   ```
   Si `job_offers.review_flags` tiene avisos, menciónalos.
2. **Lo que se envió** (lo que leyó el entrevistador): `applications.cover_letter_edited`, si no `cover_letter_used`. El CV: `cv_profile` + `sap_module` → `automation/cv_selector.py::select_cv` da la ruta en `data/cv/`; léelo (`pdftotext` si es PDF). Si la candidatura fue por portal/LinkedIn sin carta, dilo: entonces solo cuenta el CV.
3. **El perfil** (`data/profile.json`, datos personales: no copiarlos al pack salvo nombre):
   - `experience`, `education`, `certifications`, `certifications_in_progress`, `stack`
   - `sap_case_studies` → materia prima de las respuestas STAR
   - `known_gaps` → huecos con su encuadre honesto ya decidido (p. ej. SAP CPI: dirección de crecimiento, **nunca** experiencia)
   - `screening_answers` → respuestas ya fijadas (años de consultor, IFRS…): las respuestas del pack no pueden contradecirlas
4. **Historial**: `applications.notes` (hilos de Gmail, fechas, nombres de recruiters) y packs anteriores de esta candidatura en `data/interview_prep/`. Lo que salió en una fase anterior es lo más valioso para la siguiente.
5. **Pregunta a Javi** lo que no esté ya en las notas: fase (telefónica de RRHH / técnica / caso / final con cliente), fecha y hora, formato (Teams, teléfono, presencial) e interlocutores (nombre y cargo).

## Paso 2 — Investigar la empresa (orientado a la entrevista)

- Web de la empresa, noticias recientes, LinkedIn (tamaño del equipo SAP/IA, contrataciones recientes), Glassdoor/Indeed si hay opiniones.
- Si es consultora o subcontrata: identifica el **cliente final** o el proyecto (S/4HANA Public Cloud, rollout, AMS…) si es público.
- **Interlocutores**: perfil profesional público. RRHH pregunta por trayectoria, disponibilidad y salario; un manager, por encaje y motivación; un consultor senior, por profundidad técnica. No especules más allá de lo público.
- **Verifica antes de usar**: cada dato de la empresa que entre en el pack debe estar confirmado en una fuente que hayas abierto (WebFetch/WebSearch), no en un snippet. Un dato falso dicho con seguridad en una entrevista es peor que no decir nada.
- 2-3 **ganchos** verificables (un proyecto, una prioridad estratégica, una noticia) para el "¿por qué nosotros?".

## Paso 3 — El pack

Secciones, adaptadas a la fase:

1. **Preguntas probables**, por prioridad: (1) lo que quedó abierto en fases anteriores; (2) los huecos entre la oferta y el perfil, la pregunta más probable, cada uno con **respuesta puente**: reconocer → experiencia cercana real → plan de aprendizaje (usa `known_gaps` si ya lo cubre); (3) los requisitos de la oferta uno a uno; (4) las típicas de la fase (RRHH: motivación, disponibilidad, pretensión salarial con `salary_expectation` y `backend/automation/salary.py`; técnica: el stack de la oferta; final: valores, encaje y "¿alguna duda sobre ti?").
2. **Respuestas STAR**: asigna `sap_case_studies` y logros de `experience` a las preguntas. Si una pregunta no la cubre ningún caso, redacta uno nuevo **solo con hechos del perfil**, sin adornos. Si falta un dato (cifra, alcance), pregúntalo en vez de inventarlo.
3. **Coherencia**: lista corta de lo que afirman la carta y el CV enviados (logros, cifras, tecnologías destacadas) y que es más probable que pregunten. Regla: nada en la sala que no esté en el papel, y todo lo del papel defendible en profundidad.
4. **Preguntas difíciles** personalizadas: "¿por qué esta empresa?" (con los ganchos verificados), "háblame de ti" (60-90 s, enfocado al puesto), cambio de trayectoria (DAM/Data Science → SAP), "¿por qué dejas…?", pretensión salarial.
5. **Preguntas para hacer** (4-6): de rol y equipo en RRHH; de proyecto, metodología (SAP Activate, fit-to-standard) y formación en la técnica; de cultura y carrera en la final. Quita las que la investigación ya responde.
6. **Logística**: fecha, hora, enlace o dirección, interlocutores; para Teams/teléfono: cámara y audio probados, CV y pack a mano, agua.

Guárdalo en `data/interview_prep/<empresa>_<puesto>_<fase>.md` (en minúsculas, con guiones; la carpeta está en `.gitignore`), un fichero por fase para que los anteriores queden de historial. Enséñalo también en el chat.

## Paso 4 — Simulacro (si Javi quiere)

En la conversación, haciendo de entrevistador de esa fase:
1. Calentamiento ("háblame de ti").
2. Preguntas técnicas del puesto (módulo SAP de la oferta, o stack IA/datos).
3. 1-2 de comportamiento ligadas a las competencias de la oferta.
4. Una difícil o inesperada.
5. Tras cada respuesta: qué funcionó, qué afinar y qué caso STAR del pack habría encajado mejor. Ajusta el feedback a la forma de hablar de Javi, no a un ideal genérico.

## Paso 5 — Cerrar el ciclo

- Recuérdale que después de la entrevista te cuente cómo fue: actualiza `applications.status` (`interview` → `offer`, `rejected`…) y añade a `notes` la fase, la fecha y el feedback, que es lo que alimenta la preparación de la siguiente fase.
- Si durante la preparación aparecen **hechos nuevos** (una cifra, el alcance de un proyecto, un caso nuevo), propón añadirlos a `profile.json` (`sap_case_studies`, `experience`) **con su confirmación**: un hecho que solo vive en el pack no existe para las cartas y CVs futuros.

## Reglas

1. **Nunca inventar experiencia.** Los huecos se responden con puente, nunca fingiendo. `known_gaps` manda.
2. **Coherencia** con la carta y el CV enviados y con `screening_answers`.
3. **Solo investigación verificada** en el pack; de los interlocutores, solo información profesional pública.
4. **El pack depende de la fase**: lo que salió en fases anteriores pesa más que la lista genérica de preguntas.
5. **Escribe solo** en `data/interview_prep/`; `profile.json` y la BD únicamente con la confirmación de Javi.
