# SP5 — App de escritorio · Plan de implementación

> **Para quien ejecute el plan:** metodología SDD (tareas pequeñas, tests primero, un commit atómico por tarea). Las casillas `- [ ]` se marcan `- [x]` al terminar. Lo que no se pueda verificar en este entorno se deja escrito en el apartado «Registro de verificación» al final, sin darlo por hecho.

**Objetivo:** el usuario instala JobHunter con un doble clic (Windows `.msi`/`.exe`, macOS `.dmg`, Linux `.deb`/`.AppImage`), abre la app y el asistente completo funciona sin tocar un terminal: el backend arranca solo en un puerto libre de localhost, el dashboard habla con él, los datos viven en la carpeta de datos del sistema y los PDF se compilan con Tectonic incluido en el instalador.

**Arquitectura:**

```
Tauri 2 (desktop/src-tauri, Rust)
 ├─ ventana web  ← frontend/out (Next.js exportado como web estática)
 │                 URL de la API inyectada en tiempo de ejecución: window.__JH_API_URL__
 └─ proceso hijo ← backend congelado con PyInstaller (carpeta `jobhunter-api/` como recurso)
                   escucha en 127.0.0.1:<puerto libre>, avisa del puerto por stdout,
                   se apaga al cerrar la app (o si la app muere: vigilancia de stdin)
```

**Stack:** Tauri 2 (Rust), Next.js 16 `output: "export"`, PyInstaller (modo carpeta), `platformdirs`, Tectonic (binario suelto, versión fijada y con SHA-256), GitHub Actions + `tauri-apps/tauri-action`.

## Decisiones

1. **PyInstaller en modo carpeta (`onedir`), no `onefile`, y como recurso de Tauri, no como `externalBin`.** El `externalBin` de Tauri solo admite un fichero. Un `onefile` se vuelve a descomprimir (~100+ MB) en cada arranque **y en cada scraper lanzado como subproceso** (`job_manager` ejecuta `sys.executable -m scraper.jobs`). En modo carpeta el arranque es inmediato, los subprocesos no descomprimen nada y los antivirus protestan menos.
2. **El puerto lo abre el propio backend** (socket con puerto 0 entregado a uvicorn) y lo anuncia con una línea `JH_READY port=NNNN` por stdout. Así no hay carrera entre «buscar un puerto libre» y «ocuparlo».
3. **No se abre la API.** `TrustedHostMiddleware` ya ignora el puerto al comparar el `Host`, así que el puerto dinámico no exige tocar `ALLOWED_HOSTS` (`localhost,127.0.0.1`). Lo que cambia es el **origen CORS**: el dashboard dentro de Tauri sirve desde `tauri://localhost` (Linux/macOS) o `http://tauri.localhost` (Windows). El arranque de escritorio fija `CORS_ORIGINS` a exactamente esos orígenes (sin `:3010`), la cabecera `X-JH-Client: dashboard` sigue siendo obligatoria en los métodos que modifican y el listener es solo `127.0.0.1`. Se registra como adenda en `docs/adr/0002-api-local-en-app-de-escritorio.md`.
4. **JH_HOME = carpeta de datos del sistema** vía `platformdirs` (`~/.local/share/jobhunter`, `%APPDATA%\jobhunter`, `~/Library/Application Support/jobhunter`), solo si el usuario no fija `JH_HOME`. Se resuelve en el arranque de escritorio *antes* de importar `config`.
5. **Frontend:** `output: "export"` solo con `JH_DESKTOP_EXPORT=1`; `next dev`/`next start` y el despliegue web actual no cambian. La URL de la API sale de `window.__JH_API_URL__` (la inyecta Tauri con un script de inicialización antes de cargar la página), con `NEXT_PUBLIC_API_URL` y `localhost:8020` como respaldo.
6. **Chromium de Playwright bajo demanda.** Nunca va en el instalador. Antes del primer lanzamiento de Chromium se ejecuta `playwright install chromium` con el driver incluido en el paquete, hacia `JH_HOME/browsers` (`PLAYWRIGHT_BROWSERS_PATH`).
7. **Tectonic** se descarga en la CI (versión y hash fijados en `desktop/scripts/tectonic.json`), se incluye como recurso y la app lo pone delante en el `PATH` del backend (`JH_BUNDLED_BIN`); `latex_compiler` ya busca `tectonic` en el `PATH`. Tectonic descarga los paquetes LaTeX que le faltan la primera vez que compila (necesita red esa primera vez).
8. **Ollama no va incluido.** El backend expone `GET /api/ai/ollama` (instalado / en marcha / modelos) y, en escritorio, el asistente muestra un aviso con enlace de instalación o la opción de elegir otro proveedor. Los enlaces externos se abren en el navegador del sistema con una lista blanca de hosts.
9. **Aviso de versión nueva**: al arrancar, la parte Rust consulta `releases/latest` del repositorio (silencioso si no hay red) y, si hay una versión mayor, muestra un diálogo nativo con enlace a la página de la release. Sin actualización automática ni firma.
10. **Instaladores sin firmar.** macOS con firma ad-hoc (`signingIdentity: "-"`, imprescindible para que arranque en Apple Silicon); el primer arranque exige clic derecho → Abrir. Windows mostrará SmartScreen. Se explica en `desktop/README.md`.
11. **Releases como borrador.** El workflow de tag crea la release en borrador: la publica el usuario, no la CI.

## Restricciones globales

- Rama `sp5-app-escritorio`. No se hace push a `main`, no se abren PR, no se crean tags ni releases.
- Solo ficheros nuevos (`desktop/`, `.github/workflows/desktop.yml`, `backend/desktop_main.py`, `backend/desktop_freeze.spec`…) más cambios mínimos en: `frontend/next.config.ts`, `frontend/lib/api.ts` (capa de URL), `backend/config.py` (ruta de recursos al estar congelado) y los puntos de lanzamiento de Chromium. **No se tocan** `frontend/lib/i18n/`, `backend/scraper/sources/`, `templates/` ni los textos existentes de la interfaz (SP4 está en paralelo).
- Los textos nuevos de la interfaz viven en un componente nuevo, con su objeto `T`, y solo se muestran en escritorio; SP4 los pasará a i18n.
- Comentarios y docstrings en español, identificadores en inglés, commits `tipo(desktop): …` en español.
- Suites en verde en cada commit: `cd backend && python -m pytest -q`, `ruff check --config ../ruff.toml .`; `cd frontend && bunx tsc --noEmit && bun run lint && bun test`.
- Ningún secreto en el repositorio. Las acciones de CI no usan secretos propios (solo `GITHUB_TOKEN`).

## Foco de revisión

1. El backend de escritorio **sigue** rechazando `Host` ajenos, orígenes CORS ajenos y POST sin `X-JH-Client`, con puerto dinámico (test sobre el ejecutable congelado).
2. Un backend huérfano nunca queda vivo si la app muere (vigilancia de stdin + parada en `RunEvent::Exit`).
3. Un `config.py` congelado encuentra plantillas, semillas y perfil de ejemplo; el modo normal (repositorio) no cambia.
4. Los subprocesos del backend (`scraper.jobs`) funcionan congelados.
5. El export estático no contiene la URL de la API fija en el JS.

---

### Tarea 1: Plan SP5

**Ficheros:** este documento.

- [x] Escribir el plan y hacer commit `docs(sp5): plan de la app de escritorio`.

### Tarea 2: Arranque de escritorio del backend

**Ficheros:** crear `backend/desktop_main.py`, `backend/tests/test_desktop_main.py`; modificar `backend/requirements.txt` (`platformdirs`), `backend/config.py` (raíz de recursos congelada).

**Interfaces:**
- `desktop_main.prepare_environment(env: MutableMapping[str, str]) -> None`: fija por defecto `JH_HOME` (platformdirs), `CORS_ORIGINS` (orígenes de Tauri), `ALLOWED_HOSTS=localhost,127.0.0.1`, `PLAYWRIGHT_BROWSERS_PATH=<JH_HOME>/browsers`, `JH_INBOX_POLL_SECONDS` sin cambios, y antepone `JH_BUNDLED_BIN` al `PATH`. No pisa lo que el usuario ya haya definido.
- `desktop_main.open_listener() -> socket.socket` (127.0.0.1, puerto 0, `listen`).
- `desktop_main.main(argv)`: sin argumentos arranca la API; `-m <módulo> [args]` se comporta como `python -m` (para que `job_manager` funcione congelado); anuncia `JH_READY port=N`; hilo que vigila stdin y para uvicorn al EOF.
- `config.py`: si `sys.frozen`, `REPO_ROOT = BASE_DIR` (los datos se empaquetan con la misma disposición relativa).

- [x] Tests primero: `prepare_environment` (valores por defecto, no pisa, `PATH`), listener solo en loopback y con puerto asignado, `-m` ejecuta un módulo con sus argumentos, EOF de stdin dispara la parada, la línea `JH_READY` se imprime una vez, y el resultado de `config` con `sys.frozen` simulado.
- [x] Test de protecciones sobre la app real con puerto dinámico y orígenes de Tauri: `Host` ajeno → 400; `Origin` ajeno sin cabecera CORS; POST sin `X-JH-Client` → 403; preflight desde `tauri://localhost` permitido.
- [x] Commit `feat(desktop): arranque del backend en puerto libre con las protecciones de la API`.

### Tarea 3: Chromium de Playwright bajo demanda

**Ficheros:** crear `backend/automation/browser_install.py`, `backend/tests/test_browser_install.py`; modificar los tres puntos de lanzamiento (`automation/form_filler.py`, `scraper/base.py`, `scraper/linkedin_jobs.py`).

**Interfaces:** `ensure_chromium() -> None` (async-safe, idempotente, con candado): si ya existe el Chromium de la versión de Playwright instalada, no hace nada; si no, ejecuta el instalador del driver (`playwright install chromium`) y falla con un mensaje claro si no hay red.

- [x] Tests con el instalador simulado: ya instalado → no instala; falta → instala una sola vez aunque haya dos llamadas simultáneas; error → mensaje legible.
- [x] Llamar a `ensure_chromium()` justo antes de `chromium.launch(...)` en los tres sitios, sin cambiar su comportamiento si ya está instalado.
- [x] Commit `feat(desktop): descarga de Chromium la primera vez que se usa el navegador`.

### Tarea 4: Detección de Ollama

**Ficheros:** crear `backend/ollama_status.py`, `backend/tests/test_ollama_status.py`; añadir la ruta en `backend/main.py`; tipos en `frontend/lib/types.ts` y función en `frontend/lib/api.ts`.

**Interfaces:** `GET /api/ai/ollama` → `{installed: bool, running: bool, models: list[str], install_url: str}`. «Instalado» = binario en el `PATH` o en las rutas habituales; «en marcha» = `GET <base_url>/api/tags` responde (por defecto `http://localhost:11434`, mismo `base_url` que ya valida el backend). Nunca lanza: red caída → `running: false`.

- [x] Tests con HTTP y `shutil.which` simulados; `test_api_contract.py` sigue en verde (los tipos TS reflejan el modelo Pydantic).
- [x] Commit `feat(desktop): detectar Ollama y ofrecer instalarlo`.

### Tarea 5: Frontend estático con la API en tiempo de ejecución

**Ficheros:** modificar `frontend/next.config.ts`, `frontend/lib/api.ts`; crear `frontend/lib/apiBase.ts` + test, `frontend/app/components/OllamaNotice.tsx` + test (solo escritorio).

- [ ] `apiBase.ts`: `resolveApiBase(win?, env?)` → `window.__JH_API_URL__` > `NEXT_PUBLIC_API_URL` > `http://localhost:8020`; sin barras finales. `api.ts` lo usa en lugar de la constante.
- [ ] `next.config.ts`: `output: "export"` + `images.unoptimized` si `JH_DESKTOP_EXPORT=1`.
- [ ] `OllamaNotice`: se pinta solo si `window.__JH_DESKTOP__`; avisa si Ollama falta, con el enlace de instalación y la indicación de elegir otro proveedor en «Perfil». Montado en el paso de IA del asistente con una sola línea.
- [ ] Verificar: `JH_DESKTOP_EXPORT=1 bun run build` produce `frontend/out/index.html` y el JS no contiene `localhost:8020` fijo como única opción (queda solo como respaldo documentado).
- [ ] Commit `feat(desktop): dashboard exportable como web estática con la URL de la API en tiempo de ejecución`.

### Tarea 6: Congelado del backend con PyInstaller

**Ficheros:** crear `backend/desktop_freeze.spec`, `desktop/scripts/freeze_backend.py`, `desktop/scripts/smoke_backend.py`, `desktop/scripts/test_smoke_backend.py`.

- [ ] `.spec` en modo carpeta: `collect_submodules` de `scraper`, `automation`, `ai`, módulos de uvicorn, plantillas de correo (`backend/templates`), plantillas LaTeX (`templates/latex`), semillas, `profile.example.json`, `defaults/`, y el driver de Playwright.
- [ ] `freeze_backend.py`: ejecuta PyInstaller y deja `desktop/src-tauri/resources/jobhunter-api/`.
- [ ] `smoke_backend.py`: lanza el ejecutable congelado con un `JH_HOME` temporal, lee `JH_READY`, comprueba `/api/stats`, `Host` ajeno, `Origin` ajeno, POST sin cabecera y preflight desde `tauri://localhost`, cierra stdin y comprueba que el proceso termina solo.
- [ ] Ejecutar el congelado real en Linux y pegar el resultado en el registro.
- [ ] Commit `feat(desktop): backend congelado con PyInstaller y prueba de humo`.

### Tarea 7: Proyecto Tauri 2

**Ficheros:** crear `desktop/package.json`, `desktop/src-tauri/{Cargo.toml,build.rs,tauri.conf.json,capabilities/default.json,src/main.rs,src/lib.rs,src/sidecar.rs,src/update.rs,icons/}`, `desktop/scripts/build_frontend.mjs`.

- [ ] `sidecar.rs`: localizar el ejecutable (recurso), lanzarlo con el entorno de escritorio, leer `JH_READY port=N` con tiempo límite, mantener stdin abierto, matar al salir. Lógica de parseo en funciones puras con tests (`cargo test`).
- [ ] `lib.rs`: crear la ventana **después** de tener el puerto, con `initialization_script` que fija `window.__JH_API_URL__` y `window.__JH_DESKTOP__`; comando `open_external` con lista blanca (https, hosts permitidos); `on_navigation` que impide salir de la app; parada del backend en `RunEvent::Exit`; página de error si el backend no arranca.
- [ ] `update.rs`: comparación de versiones y lectura de `releases/latest` (puro y con tests), diálogo nativo con enlace.
- [ ] `tauri.conf.json`: CSP con `connect-src` solo a `http://127.0.0.1:*`/`http://localhost:*`, `bundle.targets` (`deb`, `appimage`, `msi`, `nsis`, `dmg`), recursos (backend + Tectonic), `frontendDist` → `../../frontend/out`, `signingIdentity: "-"` en macOS.
- [ ] `cargo check` y `cargo test` en Linux (si crates.io y las librerías GTK/WebKit lo permiten).
- [ ] Commit `feat(desktop): proyecto Tauri 2 con el backend como proceso hijo`.

### Tarea 8: Tectonic incluido

**Ficheros:** crear `desktop/scripts/fetch_tectonic.py`, `desktop/scripts/tectonic.json`, `desktop/scripts/test_fetch_tectonic.py`.

- [ ] `tectonic.json`: versión, nombre de recurso y SHA-256 por triple (`x86_64-pc-windows-msvc`, `x86_64-apple-darwin`, `aarch64-apple-darwin`, `x86_64-unknown-linux-gnu/musl`). Solo se escriben hashes que se hayan podido comprobar; los que no, quedan marcados y la CI falla en vez de aceptar un fichero sin verificar.
- [ ] `fetch_tectonic.py`: descarga, verifica SHA-256, extrae a `desktop/src-tauri/resources/bin/` con permisos de ejecución. Tests con un archivo sintético (hash correcto, hash incorrecto, ruta maliciosa en el zip).
- [ ] Commit `feat(desktop): Tectonic fijado por versión y hash e incluido en el instalador`.

### Tarea 9: CI de instaladores

**Ficheros:** crear `.github/workflows/desktop.yml`.

- [ ] Job `smoke` (PR/push que toquen `desktop/` o `backend/`): congela el backend y pasa la prueba de humo en Linux.
- [ ] Job `release` (tag `v*`, o `workflow_dispatch` en modo ensayo sin publicar): matriz Linux x64, Windows x64, macOS Apple Silicon y macOS Intel; instala dependencias, congela el backend, descarga Tectonic, exporta el frontend, comprueba que el tag coincide con la versión y llama a `tauri-apps/tauri-action` con `releaseDraft: true`.
- [ ] Validar el YAML (`yaml.safe_load` + `actionlint` si hay red).
- [ ] Commit `ci(desktop): instaladores para Windows, macOS y Linux en cada tag`.

### Tarea 10: Documentación

**Ficheros:** crear `desktop/README.md`, `docs/adr/0002-api-local-en-app-de-escritorio.md`; añadir una línea en `README.md`/`README.es.md`.

- [ ] Instalación, primer arranque (avisos de macOS/Windows), dónde están los datos, cómo compilar en local, cómo se publica una release.
- [ ] ADR-0002: puerto dinámico, orígenes de Tauri, qué protecciones se mantienen y cuáles cambian.
- [ ] Commit `docs(desktop): guía de la app de escritorio y ADR de la API local`.

### Tarea 11: Cierre

- [ ] `git fetch origin` y `git merge origin/main` (merge, sin rebase), conflictos resueltos sin perder lo de SP4.
- [ ] Suites completas, `graphify update .` si procede, revisión de privacidad antes del push.
- [ ] Push a `sp5-app-escritorio`. Actualizar el registro de verificación.

---

## Registro de verificación

> Se rellena al terminar cada tarea con lo realmente ejecutado y lo que no se pudo ejecutar en este entorno.

_(pendiente)_
