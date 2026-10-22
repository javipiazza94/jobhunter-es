#!/usr/bin/env python3
"""GET a page with browser headers: the 403 retry from 09-web-research.md.

Portado de MadsLorentzen/ai-job-search @ e16acee (tools/fetch_page.py, licencia MIT,
Copyright (c) 2026 Mads Lorentzen).

Uso: python -m automation.fetch_page <url> [--out PATH] [--text] [--max-chars N]
"""

import argparse
import functools
import gzip
import hashlib
import html
import http.client
import os
import re
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import (
    HTTPHandler, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener,
)

from automation.page_decode import decode_page
from automation.robots_check import BROWSER, curl_network_flags, gate, pinned_port, resolve_public

ROOT = Path(__file__).resolve().parents[2]
ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_LANGUAGE = "en-GB,en;q=0.9"
TIMEOUT_SECONDS = 45
MAX_REDIRECTS = 5
MAX_BYTES = 10 * 1024 * 1024


def build_curl_argv(url: str, out: Path, headers: Path, timeout: float, ip: str | None = None) -> list:
    """One GET without automatic redirects, so the next hop can be gated. With `ip`, the connection is pinned
    to that already-checked address (`--resolve`), so a DNS answer that changes cannot reach another host."""
    pin = curl_network_flags(urlsplit(url), ip) if ip else ["--proto", "=http,https", "--proto-redir", "=http,https", "--noproxy", "*"]
    return [
        "curl", "-sS", *pin,
        "--max-redirs", "0",
        "--max-time", str(timeout),
        "--max-filesize", str(MAX_BYTES),
        "--compressed",
        "-A", BROWSER,
        "-H", f"Accept: {ACCEPT}",
        "-H", f"Accept-Language: {ACCEPT_LANGUAGE}",
        "-D", str(headers),
        "-o", str(out),
        "-w", "%{http_code}",
        "--", url,
    ]


def _location(header_text: str) -> str | None:
    """Read Location from the final response (a proxy may add an earlier one)."""
    for block in reversed(re.split(r"\r?\n\r?\n", header_text)):
        if not block.startswith("HTTP/"):
            continue
        for line in block.splitlines():
            if line.lower().startswith("location:"):
                return line.partition(":")[2].strip()
        break
    return None


def fetch_with_curl(url: str, out: Path, timeout: float, ip: str | None = None) -> tuple[int, str | None]:
    fd, header_name = tempfile.mkstemp(prefix=".fetch_page_headers.")
    os.close(fd)  # curl must be able to open it on Windows too
    headers = Path(header_name)
    try:
        proc = subprocess.run(
            build_curl_argv(url, out, headers, timeout, ip),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout + 15,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"curl exit {proc.returncode}: {proc.stderr.strip()}")
        code = int(proc.stdout.strip())
        location = _location(headers.read_text(encoding="iso-8859-1"))
    finally:
        headers.unlink(missing_ok=True)
    if out.stat().st_size > MAX_BYTES:
        raise RuntimeError(f"response exceeds {MAX_BYTES} bytes after decompression")
    return code, location


class _NoRedirects(HTTPRedirectHandler):
    """Return the 3xx response to the caller for a robots check first."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Conecta siempre a `pinned_ip` (la ya comprobada); Host y SNI siguen siendo el nombre."""

    def __init__(self, *args, pinned_ip: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, pinned_ip: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(HTTPHandler):
    def __init__(self, ip: str):
        super().__init__()
        self._ip = ip

    def http_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPConnection, pinned_ip=self._ip), req)


class _PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, ip: str):
        super().__init__()
        self._ip = ip

    def https_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPSConnection, pinned_ip=self._ip), req)


def fetch_with_urllib(url: str, out: Path, timeout: float, ip: str | None = None) -> tuple[int, str | None]:
    """Fallback for machines without curl. One GET, gzip/deflate only. With `ip` it connects to that
    checked address (Host/SNI keep the hostname); without proxies from the environment."""
    request = Request(url, headers={
        "User-Agent": BROWSER,
        "Accept": ACCEPT,
        "Accept-Language": ACCEPT_LANGUAGE,
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        handlers = [_NoRedirects(), ProxyHandler({})]
        if ip:
            handlers += [_PinnedHTTPHandler(ip), _PinnedHTTPSHandler(ip)]
        response = build_opener(*handlers).open(request, timeout=timeout)  # noqa: S310
    except HTTPError as exc:
        response = exc
    with response:
        code = response.status if hasattr(response, "status") else response.code
        location = response.headers.get("Location")
        if code in (301, 302, 303, 307, 308) and location:
            return code, location
        encoding = (response.headers.get("Content-Encoding") or "").lower()
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise RuntimeError(f"response exceeds {MAX_BYTES} bytes")
    if encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding == "deflate":
        body = zlib.decompress(body, -zlib.MAX_WBITS)
    if len(body) > MAX_BYTES:
        raise RuntimeError(f"response exceeds {MAX_BYTES} bytes after decompression")
    out.write_bytes(body)
    return code, location


def strip_tags(markup: str, limit: int) -> str:
    """Plain text from HTML: drop script/style/noscript/svg and comments, strip
    tags, unescape entities, fold whitespace. Modern sites embed copy inside
    JSON blobs, so stray attribute fragments around real text are normal."""
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", markup)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


def _default_out(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"fetch_page_{digest}.html"


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return True


class RobotsRefused(Exception):
    """robots.txt no permite la ruta pedida (o la de una redirección)."""


def download(url: str, out: Path, say=print, timeout: float | None = None) -> str:
    """GET `url` (siguiendo redirecciones una a una, con robots.txt en cada salto) y guarda el cuerpo en `out`.

    Devuelve «HTTP <código> size=<bytes>». Lanza `RobotsRefused` si robots lo impide y cualquier otra
    excepción ante fallos de transporte. `say` recibe los mensajes de robots.

    En cada salto el destino se resuelve una vez, se exige que sea una dirección pública
    (`robots_check.BlockedAddress` si no) y la conexión se fija a esa IP, así que un DNS que cambia entre la
    comprobación y la conexión no puede llevar la petición a la red interna. `timeout` (segundos) acota el
    total (por defecto TIMEOUT_SECONDS), robots incluido.
    """
    current = url
    deadline = None
    for redirects in range(MAX_REDIRECTS + 1):
        scheme = urlsplit(current).scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError(f"redirect target must be http(s), got scheme {scheme!r}")
        parts = urlsplit(current)
        ip = resolve_public(parts.hostname, pinned_port(parts))
        if deadline is None:
            deadline = time.monotonic() + min(TIMEOUT_SECONDS, timeout if timeout is not None else TIMEOUT_SECONDS)
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("fetch exceeded the time limit")
        rc, message = gate(current) if timeout is None else gate(current, timeout=min(12, left))
        say(message)
        if rc != 0:
            raise RobotsRefused(current)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("fetch exceeded the time limit")
        out.parent.mkdir(parents=True, exist_ok=True)
        fd, body_name = tempfile.mkstemp(dir=out.parent, prefix=".fetch_page.", suffix=".tmp")
        os.close(fd)  # curl/urllib may reopen the path on Windows
        body = Path(body_name)
        try:
            code, location = (
                fetch_with_curl(current, body, remaining, ip)
                if shutil.which("curl") else fetch_with_urllib(current, body, remaining, ip)
            )
            if code in (301, 302, 303, 307, 308) and location:
                if redirects == MAX_REDIRECTS:
                    raise RuntimeError(f"more than {MAX_REDIRECTS} redirects")
                # Encode the header's raw bytes before resolving; preserve Unicode in the base URL.
                current = urljoin(current, quote(location, encoding="iso-8859-1", safe=string.punctuation))
                continue
            os.replace(body, out)
            return f"HTTP {code} size={out.stat().st_size}"
        finally:
            body.unlink(missing_ok=True)
    raise RuntimeError("redirect loop")  # inalcanzable: el último salto lanza arriba


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default encoding is.

    A piped stdout on Windows defaults to the ANSI code page (cp1252 on most
    Western installs), so printing a page with characters outside it raised
    UnicodeEncodeError before the workflow saw any output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        prog="fetch_page.py",
        description="GET a page with browser headers (robots.txt enforced); see module docstring.",
    )
    parser.add_argument("url")
    parser.add_argument("--out", type=Path, default=None,
                        help="where to save the body (default: system temp dir; never inside the repo)")
    parser.add_argument("--text", action="store_true", help="also print the tag-stripped text")
    parser.add_argument("--max-chars", type=int, default=6000, help="cap for --text (default 6000)")
    args = parser.parse_args(argv)

    scheme = urlsplit(args.url).scheme.lower()
    if scheme not in ("http", "https"):
        print(f"fetch_page: only http(s) URLs are fetched, got scheme {scheme!r}", file=sys.stderr)
        return 2

    out = args.out if args.out is not None else _default_out(args.url)
    if _inside_repo(out):
        print(
            f"fetch_page: refusing to write inside the repo ({out}); fetched content is "
            "untrusted and belongs in the session scratchpad or the temp directory",
            file=sys.stderr,
        )
        return 2

    try:
        status = download(args.url, out)
    except RobotsRefused:
        print(
            "fetch_page: refused - robots.txt does not permit this path, so the "
            "browser-header retry does not run. Go to escalation step 4: search for "
            "the employer's own posting."
        )
        return 1
    except Exception as exc:  # transport failures of any shape: report, exit 2
        print(f"fetch_page: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"{status} saved={out}")
    if args.text:
        print("--- text ---")
        print(strip_tags(decode_page(out.read_bytes()), args.max_chars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
