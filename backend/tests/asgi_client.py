"""Cliente ASGI mínimo para probar la app sin httpx (no está instalado)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main  # noqa: E402


def call(method, path, headers=(), host="localhost:8020", query="", body=b""):
    """Llama a la app por ASGI y devuelve (status, cabeceras en minúsculas, cuerpo)."""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
        "scheme": "http", "server": ("localhost", 8020), "client": ("127.0.0.1", 50000),
        "headers": [(b"host", host.encode())] + [(k.encode(), v.encode()) for k, v in headers],
    }
    sent = []
    delivered = False

    async def receive():
        # Como un servidor real: el cuerpo una vez; después espera (las respuestas de fichero o en
        # streaming escuchan una desconexión que aquí nunca llega y se cancela al terminar).
        nonlocal delivered
        if delivered:
            await asyncio.Event().wait()
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(main.app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}, body.decode()
