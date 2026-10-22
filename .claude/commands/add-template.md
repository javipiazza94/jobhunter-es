# /add-template — Registrar una plantilla propia de CV o carta

Registra tu propia plantilla de CV o de carta (LaTeX o Typst) para que **Preparar candidatura** y `/apply` la usen. Es lo mismo que el apartado **Plantillas de CV y carta** de la pestaña Perfil (`backend/automation/templates_registry.py`). Integradas: `moderncv-banking` (CV) y `cover-cls` (carta), siempre disponibles.

`$ARGUMENTS`: `--list`, `--use <tipo> <nombre>` (`--use cv moderncv-banking` vuelve a la integrada), una ruta a un `.zip`/`.tex.j2`/`.typ.j2`, o nada.

## Cómo es una plantilla

- Es una plantilla **Jinja** con delimitadores seguros: variables `(((  x )))`, bloques `((* if x *)) … ((* endif *))`, comentarios `((= … =))`. Se renderiza en un entorno **aislado** (sin acceso a atributos internos de Python: un intento da `SecurityError` y la plantilla se rechaza).
- **Toda salida `((( x )))` se escapa por defecto** según el motor (`latex_escape` en LaTeX, `typst_escape` en Typst). Puedes escribir el filtro explícitamente (no se escapa dos veces); los enlaces van con `latex_url` y, solo para texto que de verdad deba ir crudo, `|safe_raw`.
- Contexto del CV: `personal`, `summary_text`, `experience` (cada empleo con `bullets`), `education`, `languages_line`, `certifications`... Contexto de la carta: `personal`, `company_name`, `role_title`, `current_date`, `opening_paragraph`, `body_paragraph`, `bullets`, `connection_paragraph`, `closing_paragraph`. Mira las plantillas integradas `templates/latex/cv/cv.tex.j2` y `templates/latex/cover_letters/cover.tex.j2` como modelo (y `backend/automation/document_generator.py`, `prepare_cv_context` / `prepare_cover_letter_context`, para la lista completa).
- Ficheros de apoyo (`.cls`, fuentes, imágenes) viajan junto a la plantilla en el `.zip` y se copian al compilar. Fuentes con licencia libre (OFL).
- Debe incluir email y teléfono **literales** (los exige la verificación ATS), usar fechas ASCII y caber en el límite de páginas (CV 2, carta 1; configurable en `documents:` de `jobhunter.yaml` o con `--page-limit`).

## Pasos

1. `--list`: desde `backend/`, `.venv/bin/python -m automation.templates_registry list` (la activa va marcada con `*`).
2. Registrar (hace una **compilación de prueba obligatoria** con `backend/profile.example.json`; si no compila o no cabe, no se registra y se muestra el error):

   ```bash
   .venv/bin/python -m automation.templates_registry add <ruta> --name <nombre> --kind cv|letter [--engine latex|typst] [--compiler tectonic|xelatex|lualatex|typst] [--page-limit N] [--style-rules "texto"]
   ```

   Typst exige `typst` en el PATH; LaTeX, Tectonic o TeX Live (sin `--compiler` se usa el primero instalado). Si falta el motor, el error lo dice y cómo instalarlo. `--page-limit` manda sobre `documents:` al preparar candidaturas con esta plantilla y `--style-rules` llega a la IA como reglas de forma (nunca de hechos).
3. Activar: `.venv/bin/python -m automation.templates_registry activate <cv|letter> <nombre>` (se guarda en `documents:` de `jobhunter.yaml`; requiere haber completado el asistente).
4. Borrar: `.venv/bin/python -m automation.templates_registry delete <cv|letter> <nombre>` (si era la activa, vuelve la integrada).
5. Genera una candidatura de prueba (`/apply`) y revisa el PDF.

Seguridad — **una plantilla es código: instala solo las de fuentes de confianza.** Aun así: el `.zip` no puede salirse de su carpeta (sin `..`, rutas absolutas ni enlaces simbólicos) y `latexmkrc`, `.latexmkrc` y `texmf.cnf` se descartan; no hay comando de compilación libre (solo un compilador de la lista, con opciones fijas: sin shell-escape, Tectonic con `--untrusted`, xelatex/lualatex en modo paranoico y Typst con `--root` en la carpeta de trabajo; nunca latexmk); y se rechaza cualquier `\input`, `\include`, `\openin`... con ruta absoluta o con `..`. Si la plantilla falla al preparar, la candidatura se puede preparar con las integradas (`prepare <id> --builtin-templates`).
