#!/usr/bin/env python3
"""robots.txt gate for web scraping: does the site publish a policy that permits fetching this page?

Portado de MadsLorentzen/ai-job-search @ e16acee (tools/robots_check.py, licencia MIT,
Copyright (c) 2026 Mads Lorentzen).

RFC 9309 (Robots Exclusion Protocol), with cautious rules:
  * checks both "User-agent: Claude-User" and "User-agent: *"
  * any match on Disallow that is as long as or longer than Allow denies
    (RFC 9309 says most specific rule wins, ties go to Allow; cautious
    rules in that case, which fails open - see tests)
  * one leading UTF-8 byte-order mark is skipped (left in, it hides a first
    "User-agent" line and drops that whole group, which fails open)
  * 404 means no published policy, which is permission
  * any other failure to read robots.txt leaves permission unconfirmed,
    and the retry does not happen - including a User-agent, Allow or
    Disallow line holding U+FFFD, i.e. a byte that is not valid UTF-8

Usage:  python -m automation.robots_check <url>
Exit 0 = the retry may proceed. Exit 1 = do not retry; go to escalation step 3.
"""

import ipaddress
import os
import re
import socket
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urljoin, urlsplit

BROWSER = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36')


MAX_ROBOTS_REDIRECTS = 5


class BlockedAddress(Exception):
    """El destino no es una dirección pública (red interna, enlace local, no resuelve…)."""


def resolve_public(host, port=None):
    """Resuelve `host` y devuelve la IP a la que hay que conectar, **comprobada**: todas las direcciones
    devueltas deben ser públicas. Quien la use debe conectar a esa IP (curl --resolve) y no volver a resolver,
    o un DNS que cambia entre la comprobación y la conexión (rebinding) esquivaría la comprobación."""
    if not host:
        raise BlockedAddress("sin host")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise BlockedAddress(f"no se pudo resolver {host}") from exc
    ips = [info[4][0].split("%")[0] for info in infos]
    if not ips:
        raise BlockedAddress(f"{host} no resuelve")
    for ip in ips:
        if not ipaddress.ip_address(ip).is_global:
            raise BlockedAddress(f"{host} no es una dirección pública")
    return ips[0]


def pinned_port(parts):
    """Puerto efectivo de una URL ya partida."""
    return parts.port or (443 if parts.scheme.lower() == 'https' else 80)


def curl_network_flags(parts, ip):
    """Opciones de curl comunes: solo http(s) (también en redirecciones), sin proxies del entorno y conexión
    fijada a la IP ya comprobada."""
    host = parts.hostname
    return ['--proto', '=http,https', '--proto-redir', '=http,https', '--noproxy', '*',
            '--resolve', f'{host}:{pinned_port(parts)}:{ip}']


def _fetch(url, ua, timeout=12):
    """curl, not urllib: some hosts (jobup.ch) hang urllib indefinitely while
    answering curl in under a second, and --max-time is a hard ceiling.

    Sin -L: cada redirección se sigue a mano (máx. 5) comprobando que su destino es público y fijando la IP
    resuelta en la conexión."""
    for _ in range(MAX_ROBOTS_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme.lower() not in ('http', 'https'):
            raise RuntimeError('redirect to a non-http(s) scheme')
        ip = resolve_public(parts.hostname, pinned_port(parts))
        fd, header_name = tempfile.mkstemp(prefix='.robots_headers.')
        os.close(fd)
        try:
            r = subprocess.run(
                ['curl', '-sS', '--max-redirs', '0', '--max-time', str(timeout), '-A', ua,
                 *curl_network_flags(parts, ip),
                 '-H', 'Accept: text/plain,*/*', '-D', header_name, '-w', '\n%{http_code}', '--', url],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout + 8)
            headers = open(header_name, encoding='iso-8859-1').read()
        finally:
            os.unlink(header_name)
        if r.returncode != 0:
            raise RuntimeError('curl exit %d' % r.returncode)
        body, _, code = r.stdout.rpartition('\n')
        status = int(code or 0)
        if status in (301, 302, 303, 307, 308):
            location = next((line.partition(':')[2].strip() for line in headers.splitlines()
                             if line.lower().startswith('location:')), None)
            if not location:
                return body, status
            url = urljoin(url, quote(location, encoding='iso-8859-1', safe="!#$%&'()*+,/:;=?@[]~"))
            continue
        return body, status
    raise RuntimeError('too many redirects')


def is_robots_body(text):
    """Does this actually look like a robots.txt?

    A misconfigured host can answer /robots.txt with 200 and an HTML error page.
    That body parses to zero rules, and zero rules read as "allowed" - so a
    soft-200 granted permission that was never given. An empty or whitespace-only
    body IS a valid allow-all under RFC 9309 and stays allowed; a non-empty body
    with no recognised directive is treated as unreadable.
    """
    text = text.removeprefix('\ufeff')
    if not text.strip():
        return True
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip().lower()
        if ':' in line and line.split(':', 1)[0].strip() in (
            'user-agent', 'allow', 'disallow', 'sitemap', 'crawl-delay', 'host',
        ):
            return True
    return False


def has_undecodable_rule(text):
    """Does a User-agent, Allow or Disallow line hold U+FFFD?"""
    for raw in text.removeprefix('\ufeff').splitlines():
        line = raw.split('#', 1)[0]
        if '\ufffd' in line and ':' in line:
            field = line.split(':', 1)[0].replace('\ufffd', '').strip().lower()
            if field in ('user-agent', 'allow', 'disallow'):
                return True
    return False


def _groups(text):
    """user-agent -> [(is_allow, pattern)], tolerating blank lines inside a record."""
    out, agents, expect = {}, [], True
    for raw in text.removeprefix('\ufeff').splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line or ':' not in line:
            continue
        field, _, value = line.partition(':')
        field, value = field.strip().lower(), value.strip()
        if field == 'user-agent':
            if not expect:
                agents, expect = [], True
            agents.append(value.lower())
            out.setdefault(value.lower(), [])
        elif field in ('allow', 'disallow') and agents:
            expect = False
            for a in agents:
                out[a].append((field == 'allow', value))
    return out


def _match(pattern, path):
    """RFC 9309 wildcard match; returns match length or -1."""
    if pattern == '':
        return -1
    pattern = unquote(pattern)
    end_anchor = pattern.endswith('$')
    pat = pattern[:-1] if end_anchor else pattern
    rx = '^' + ''.join('.*' if c == '*' else re.escape(c) for c in pat) + ('$' if end_anchor else '')
    return len(pattern) if re.match(rx, path) else -1


def allowed(text, agent, path):
    g = _groups(text)
    rules = g.get(agent.lower()) or g.get('*') or []
    best_len, best_allow = -1, True
    for is_allow, pat in rules:
        n = _match(pat, path)
        if n > best_len or (n == best_len and n >= 0 and not is_allow):
            best_len, best_allow = n, is_allow
    return True if best_len < 0 else best_allow


def gate(url, timeout=12):
    parts = urlsplit(url)
    path = unquote(parts.path) or '/'
    if parts.query:
        path += '?' + unquote(parts.query)
    robots = f'{parts.scheme}://{parts.netloc}/robots.txt'
    body, last = None, 'no attempt'
    for ua in ('Claude-User', BROWSER):
        try:
            text, code = _fetch(robots, ua, timeout) if timeout != 12 else _fetch(robots, ua)
        except Exception as e:
            last = type(e).__name__
            continue
        if code == 404:
            return 0, 'ALLOWED - no robots.txt published'
        if code == 200:
            if not is_robots_body(text):
                last = 'HTTP 200 but the body is not a robots.txt'
                continue
            if has_undecodable_rule(text):
                last = 'HTTP 200 but a User-agent/Allow/Disallow line is not valid UTF-8'
                continue
            body = text
            break
        last = 'HTTP %d' % code
    if body is None:
        return 1, 'UNCONFIRMED (%s) - do not retry, go to step 3' % last
    for a in ('Claude-User', '*'):
        if not allowed(body, a, path):
            return 1, f'DISALLOWED for {a} - do not retry, go to step 3'
    return 0, 'ALLOWED - robots.txt permits this path'


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


if __name__ == '__main__':
    _force_utf8_output()
    if len(sys.argv) != 2:
        print('usage: python -m automation.robots_check <url>', file=sys.stderr)
        sys.exit(2)
    rc, msg = gate(sys.argv[1])
    print(msg)
    sys.exit(rc)
