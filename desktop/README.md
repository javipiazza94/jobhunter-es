# JobHunter de escritorio

La misma aplicación que el dashboard web, empaquetada para usarla sin terminal. Se instala como
cualquier programa, abre su propia ventana y arranca el backend en segundo plano.

## Instalar

Descarga el instalador de tu sistema desde la
[página de versiones](https://github.com/javipiazza94/jobhunter-es/releases):

| Sistema | Fichero |
|---|---|
| Windows | `JobHunter_<versión>_x64-setup.exe` o `.msi` |
| macOS, Apple Silicon (M1 o posterior) | `JobHunter_<versión>_aarch64.dmg` |
| macOS, Intel | `JobHunter_<versión>_x64.dmg` |
| Linux | `.deb` (Debian, Ubuntu…) o `.AppImage` (el resto) |

Los instaladores **no están firmados**, así que el sistema avisa la primera vez:

- **Windows:** SmartScreen dice «Windows protegió su equipo». Pulsa «Más información» y luego «Ejecutar de todas formas».
- **macOS:** haz clic derecho sobre la app y elige «Abrir»; confirma en el cuadro. Si dice que está dañada,
  quita la marca de descarga: `xattr -cr /Applications/JobHunter.app`.
- **Linux (AppImage):** `chmod +x JobHunter_*.AppImage` y ábrelo con doble clic.

La app no se actualiza sola. Al arrancar comprueba si hay una versión nueva y, si la hay, te lo dice y
te lleva a la página de descarga. Sin conexión no pasa nada.

## Primer arranque

Se abre el asistente: subes tu CV (o lo rellenas a mano), eliges dónde buscar y listo. Algunas cosas se
preparan solas la primera vez que las necesitas:

- **PDF del CV y la carta:** Tectonic viene incluido. La primera compilación descarga los paquetes de
  LaTeX que faltan, así que necesita conexión esa vez.
- **Rellenar formularios de candidatura:** descarga Chromium (unos 150 MB) cuando lo pides por primera vez.
  No va en el instalador.
- **IA local:** Ollama no viene incluido. Si eliges Ollama en el asistente y no está, la app te lo dice y te
  enlaza a su descarga; también puedes elegir otro proveedor (Anthropic, OpenAI) o ninguno.

## Dónde se guardan tus datos

Todo está en una carpeta del sistema, fuera de la aplicación (desinstalar no la borra):

| Sistema | Carpeta |
|---|---|
| Linux | `~/.local/share/jobhunter` |
| macOS | `~/Library/Application Support/jobhunter` |
| Windows | `%APPDATA%\jobhunter` |

Ahí están la base de datos, `jobhunter.yaml`, `profile.json`, los CV, las candidaturas preparadas, los
logs y el Chromium descargado. Para copiarlos a otro equipo basta con copiar la carpeta. Si quieres otra
ubicación, define `JH_HOME` antes de abrir la app.

## Cómo funciona por dentro

```
ventana Tauri ── carga ──► frontend/out  (dashboard exportado como web estática)
      │                        │  window.__JH_API_URL__ = http://127.0.0.1:<puerto>
      └── lanza y vigila ──► jobhunter-api  (backend FastAPI congelado con PyInstaller)
                                  └── tectonic (en el PATH del backend)
```

- El backend elige un puerto libre en `127.0.0.1` y lo anuncia por stdout (`JH_READY port=N`). La ventana
  se abre cuando lo ha recibido.
- La API sigue protegida como en la versión web: solo loopback, `Host` de confianza, cabecera
  `X-JH-Client` en lo que modifica y CORS solo para el origen de la app. Detalles en
  [ADR-002](../docs/adr/0002-api-local-en-app-de-escritorio.md).
- Si la app se cierra de golpe, el backend se apaga solo al perder su `stdin`.

## Compilar en local

Necesitas Python 3.11+, [bun](https://bun.sh), Rust (estable) y, en Linux, las librerías de Tauri
(`libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev libayatana-appindicator3-dev libsoup-3.0-dev patchelf`).

```bash
pip install -r backend/requirements.txt pyinstaller
python desktop/scripts/freeze_backend.py                    # backend → desktop/src-tauri/resources/jobhunter-api/
python desktop/scripts/smoke_backend.py desktop/src-tauri/resources/jobhunter-api/jobhunter-api
python desktop/scripts/fetch_tectonic.py --allow-unverified  # → resources/bin/ (sin --allow-unverified exige el hash fijado)
cd desktop && bun install
bunx tauri build                                            # exporta el frontend y genera los instaladores
```

Para desarrollar con recarga: `bunx tauri dev` (dashboard en `localhost:3010`). Si no has congelado el
backend, apunta a uno propio con `JH_BACKEND_EXE=/ruta/a/un/script`, que debe imprimir `JH_READY port=N`
y quedarse leyendo stdin (por ejemplo, un script que ejecute `python backend/desktop_main.py`).

Para compilar el crate sin haber congelado nada basta con que existan `resources/bin/` y
`resources/jobhunter-api/` (el repositorio incluye un `.gitkeep` en cada una).

Pruebas:

```bash
python -m pytest -q desktop/scripts        # empaquetado de Tectonic y versión
cd desktop/src-tauri && cargo test         # sidecar, versiones, enlaces permitidos
cd backend && python -m pytest -q tests/test_desktop_main.py
```

## Publicar una versión

1. Sube la versión en `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml` y
   `desktop/package.json` (`python desktop/scripts/check_version.py` comprueba que coinciden).
2. Haz un tag `vX.Y.Z` y súbelo. El workflow **Desktop** construye Windows, macOS (Apple Silicon e Intel) y
   Linux y los deja en una release **en borrador**. La publicas tú.
3. La primera vez hay que fijar los hashes de Tectonic: lanza el workflow a mano (Actions → Desktop →
   Run workflow), copia los SHA-256 que imprime en el resumen a `desktop/scripts/tectonic.json` y haz
   commit. Con un tag la CI no instala un Tectonic sin hash.

## Limitaciones conocidas

- Sin firma de código: avisos de SmartScreen y Gatekeeper (ver arriba).
- Los textos del aviso de versión y de los errores de arranque están en español.
- Si cierras la app mientras corre un scraper, ese subproceso termina por su cuenta (tiene tiempo límite).
