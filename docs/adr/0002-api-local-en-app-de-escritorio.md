# ADR-002: La API local dentro de la app de escritorio

**Estado:** Aceptado e implementado
**Fecha:** 2026-10-23
**Continúa:** [ADR-001](0001-proteccion-de-la-api-local.md)

## Contexto

La app de escritorio (`desktop/`, Tauri 2) arranca el backend como proceso hijo y el dashboard,
exportado como web estática, habla con él. Dos cosas cambian respecto a ADR-001:

- El puerto ya no es el 8020 fijo. Lo elige el sistema en cada arranque, porque el 8020 puede estar
  ocupado o el usuario puede abrir otra copia del proyecto en modo desarrollo.
- El dashboard no se sirve desde `http://localhost:3010` sino desde el origen del webview:
  `tauri://localhost` (Linux y macOS) o `http://tauri.localhost` / `https://tauri.localhost` (Windows).

## Decisión

Se mantienen las cinco capas de ADR-001 y se ajusta lo mínimo:

1. **Solo loopback.** El socket se abre en `127.0.0.1` con el puerto 0 y se entrega ya abierto a uvicorn
   (`backend/desktop_main.py`). No hay un momento en que otro proceso pueda quedarse con el puerto
   entre «buscar uno libre» y «usarlo».
2. **Host de confianza, sin cambios.** `TrustedHostMiddleware` compara solo el nombre, no el puerto, así
   que `ALLOWED_HOSTS=localhost,127.0.0.1` sigue valiendo con cualquier puerto. En escritorio se fuerza
   ese valor aunque el entorno diga otra cosa.
3. **CORS con los orígenes de Tauri y nada más.** `CORS_ORIGINS` se fija a los tres orígenes del webview.
   El de `localhost:3010` no se admite en escritorio. Solo `tauri dev` añade el suyo, y lo hace con una
   variable explícita (`JH_DESKTOP_EXTRA_ORIGINS`) que las compilaciones de producción no pasan.
4. **Cabecera `X-JH-Client: dashboard`, sin cambios.** Sigue siendo obligatoria en los métodos que modifican.
5. **El puerto llega al frontend en tiempo de ejecución.** Tauri crea la ventana cuando el backend ya
   ha anunciado su puerto (`JH_READY port=N` por stdout) y le inyecta `window.__JH_API_URL__` antes de que
   cargue la página. El frontend solo acepta una URL `http://127.0.0.1:<puerto>` o `http://localhost:<puerto>`
   (`frontend/lib/apiBase.ts`): una URL inyectada hacia otro servidor se ignora.
6. **La ventana solo carga páginas de la app.** `on_navigation` rechaza cualquier otra URL, y los
   enlaces `https` del dashboard se abren en el navegador del sistema solo si son de `ollama.com` o de este
   repositorio.
7. **El backend no sobrevive a la app.** Tauri lo para al salir. Si la app muere de golpe (kill, caída), el
   backend detecta el cierre de su `stdin` y se apaga solo; a los 10 segundos, si no ha terminado, sale a
   la fuerza.
8. **Una sola instancia.** Abrir la app dos veces enfoca la primera: dos backends escribirían la misma
   base de datos SQLite.

## Qué no cambia

- La cabecera propia no es un secreto: protege del navegador, no de un proceso local malicioso
  (igual que en ADR-001). Cualquier programa del usuario puede leer el puerto de la lista de procesos o
  escanear el loopback y llamar a la API con la cabecera. Si algún día eso importa, la salida es la
  opción C de ADR-001 (token por arranque que Tauri entrega solo al webview).
- Los scrapers y trabajos siguen lanzándose como subprocesos del backend. El ejecutable congelado
  emula `python -m <módulo>` para eso.

## Consecuencias

- Un origen que no sea el de Tauri (otra pestaña del navegador, otra web) no recibe cabeceras CORS ni
  puede escribir sin la cabecera propia. Los tests lo cubren (`tests/test_desktop_main.py` y
  `desktop/scripts/smoke_backend.py` sobre el ejecutable congelado).
- Si Tauri cambia los esquemas del webview en una versión futura, hay que actualizar
  `TAURI_ORIGINS` en `backend/desktop_main.py` y `is_app_url` en `desktop/src-tauri/src/external.rs`.
- Se guarda una línea por arranque en la salida del backend; no hay fichero de log propio de la app.
