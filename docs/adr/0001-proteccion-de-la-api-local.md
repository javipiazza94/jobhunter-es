# ADR-001: Protección de la API local

**Estado:** Aceptado e implementado
**Fecha:** 2026-10-07
**Decide:** Equipo JobHunter

## Contexto

La API (FastAPI, `:8020`) no tiene autenticación y se arrancaba con `--host 0.0.0.0` (`modo jh`);
el dashboard de Next.js (`:3010`) también escuchaba en todas las interfaces. Pruebas hechas sobre
la API real:

- Desde la IP de la LAN y sin credenciales se leían `/api/applications` (518 KB), `/api/contacts`
  (42 KB, con emails de reclutadores), el historial y el propio dashboard.
- `POST /api/applications/{id}/approve` envía un correo desde el Gmail del usuario con su CV.
  El riesgo existe siempre que haya borradores pendientes.
- CORS bloqueaba el `preflight` de `DELETE`/`PATCH` desde otros orígenes, pero un `POST` «simple»
  desde cualquier web llegaba al handler (`scraper/run`, `applications/run`, `create-drafts`):
  CORS solo oculta la respuesta, no impide que se ejecute.
- Un `Host` falso (DNS rebinding) obtenía 200.
- No había límite de uso: `POST /api/scraper/run` se podía repetir sin freno, con riesgo de machacar
  los portales de empleo desde la IP del usuario (bloqueos) y de apilar procesos de Playwright.
  (Ninguna de esas fuentes usa ScraperAPI: solo el modo `generic`, que se lanza por línea de comandos.)
- La exportación CSV del historial escribía tal cual textos que vienen de portales y correos
  externos: una celda que empiece por `=`, `+`, `-` o `@` se ejecuta como fórmula al abrirla en Excel.

El `0.0.0.0` no tenía justificación funcional: el dashboard apunta por defecto a
`localhost:8020` (desde otro equipo no funcionaría) y n8n ya no llama a la API; entrega los
eventos por ficheros de `backend/inbox/`.

## Decisión

Defensa en capas, sin añadir login ni guardar secretos en el frontend:

1. **Solo loopback.** API y dashboard escuchan en `127.0.0.1` (`modo jh`, `main.py` y los scripts
   `dev`/`start` de `frontend/package.json`).
2. **Host de confianza.** `TrustedHostMiddleware` con `ALLOWED_HOSTS` (por defecto
   `localhost,127.0.0.1`). Frena el DNS rebinding.
3. **Cabecera propia en los métodos que modifican.** `POST`/`PUT`/`PATCH`/`DELETE` exigen
   `X-JH-Client: dashboard`. Al no ser una cabecera «simple», el navegador hace `preflight` y CORS
   lo rechaza para orígenes no permitidos. Frena el CSRF.
4. **Límite de uso del scraper.** `backend/rate_gate.py`: una fuente no se lanza dos veces a la vez
   (409) ni se repite antes de `SCRAPER_COOLDOWN_SECONDS` (300 por defecto; 0 lo desactiva) desde
   que terminó la anterior (429 + `Retry-After`). El turno se libera aunque el scraper falle. El
   estado vive en el proceso. El dashboard muestra el motivo del rechazo.
5. **CSV sin fórmulas.** Las celdas que empiezan por `=`, `+`, `-`, `@`, tab o CR llevan una comilla
   simple delante; los teléfonos y números sueltos (`+34 600…`, `-5`) no se tocan. El JSON no cambia.

El frontend añade la cabecera en un único sitio (`request()` de `frontend/lib/api.ts`).
Ver `backend/tests/test_api_security.py`.

## Opciones consideradas

| Opción | Complejidad | Cubre LAN | Cubre webs ajenas y rebinding |
|---|---|---|---|
| A. Solo `127.0.0.1` | Baja | ✅ | ❌ |
| **B. A + host de confianza + cabecera propia (elegida)** | Media | ✅ | ✅ |
| C. Token (Bearer) para todo | Media-alta | ✅ | ✅ |
| D. No hacer nada | — | ❌ | ❌ |

## Consecuencias

- Más fácil: ninguna otra máquina de la red ve nada; una web ajena no puede actuar sobre la API.
- Más difícil: un cliente que no sea el dashboard (curl, scripts) debe enviar
  `X-JH-Client: dashboard` en los métodos que modifican.
- n8n (en Docker) no puede llegar a la API por `host.docker.internal` mientras escuche solo en
  loopback. Hoy no lo necesita; si algún día lo hace habrá que enlazar a la IP del puente de Docker
  **y** pasar a la opción C (token), porque la cabecera propia no es un secreto.
- La cabecera no es una credencial: protege del navegador, no de un proceso local malicioso.

## Seguimiento

- `modo` aplicaba el mismo `--host 0.0.0.0` a Finance-Portfolio (8005) y social-scraper (8012):
  corregido a `127.0.0.1` (sus frontends y su único script cliente ya usaban `localhost`).
- Siguen escuchando en todas las interfaces los servidores de desarrollo de Next.js de otros modos
  (`next dev` usa `0.0.0.0` por defecto) y lo que publique Docker; no se han tocado por no ser de
  este proyecto.
- `applications/run` y `create-drafts` no tienen límite de uso: no tocan portales, solo generan
  borradores en local.
