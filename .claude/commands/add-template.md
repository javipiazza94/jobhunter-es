# /add-template — Registrar una plantilla propia de CV o carta

Registra tu propia plantilla de CV o de carta (LaTeX o Typst) para que **Preparar candidatura** y `/apply` la usen. Es lo mismo que el apartado **Plantillas de CV y carta** de la pestaña Perfil (`backend/automation/templates_registry.py`). Integradas: `moderncv-banking` (CV) y `cover-cls` (carta), siempre disponibles.

`$ARGUMENTS`: `--list`, `--use <tipo> <nombre>` (`--use cv moderncv-banking` vuelve a la integrada), una ruta a un `.zip`/`.tex.j2`/`.typ.j2`, o nada.

## Cómo es una plantilla

- Es una plantilla **Jinja** con delimitadores seguros: variables `(((  x )))`, bloques `((* if x *)) … ((* endif *))`, comentarios `((= … =))`. Los textos del usuario van siempre con el filtro `latex_escape` (o `typst_escape` en Typst; los enlaces con `latex_url`).
- Contexto del CV: `personal`, `summary_text`, `experience` (cada empleo con `bullets`), `education`, `languages_line`, `certifications`... Contexto de la carta: `personal`, `company_name`, `role_title`, `current_date`, `opening_paragraph`, `body_paragraph`, `bullets`, `connection_paragraph`, `closing_paragraph`. Mira las plantillas integradas `templates/latex/cv/cv.tex.j2` y `templates/latex/cover_letters/cover.tex.j2` como modelo (y `backend/automation/document_generator.py`, `prepare_cv_context` / `prepare_cover_letter_context`, para la lista completa).
- Ficheros de apoyo (`.cls`, fuentes, imágenes) viajan junto a la plantilla en el `.zip` y se copian al compilar. Fuentes con licencia libre (OFL).
- Debe incluir email y teléfono **literales** (los exige la verificación ATS), usar fechas ASCII y caber en el límite de páginas (CV 2, carta 1; configurable en `documents:` de `jobhunter.yaml` o con `--page-limit`).

## Pasos

1. `--list`: desde `backend/`, `.venv/bin/python -m automation.templates_registry list` (la activa va marcada con `*`).
2. Registrar (hace una **compilación de prueba obligatoria** con `backend/profile.example.json`; si no compila o no cabe, no se registra y se muestra el error):

   ```bash
   .venv/bin/python -m automation.templates_registry add <ruta> --name <nombre> --kind cv|letter [--engine latex|typst] [--page-limit N] [--style-rules "texto"]
   ```

   Typst exige `typst` en el PATH; LaTeX, Tectonic o TeX Live. Si falta el motor, el error lo dice y cómo instalarlo.
3. Activar: `.venv/bin/python -m automation.templates_registry activate <cv|letter> <nombre>` (se guarda en `documents:` de `jobhunter.yaml`; requiere haber completado el asistente).
4. Borrar: `.venv/bin/python -m automation.templates_registry delete <cv|letter> <nombre>` (si era la activa, vuelve la integrada).
5. Genera una candidatura de prueba (`/apply`) y revisa el PDF.

Seguridad: el `.zip` no puede salirse de su carpeta (sin `..`, rutas absolutas ni enlaces simbólicos) y un comando de compilación propio solo puede ser un compilador conocido, sin shell.
