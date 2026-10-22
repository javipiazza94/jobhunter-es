"""Tests de la capa de proveedores de IA; red y subprocesos siempre simulados."""
import subprocess
import tempfile

import pytest
import requests

import ai
from ai import AIError, AIUnavailable, base, cli_providers, get_provider, http_providers
from search_config import AISettings

SCHEMA = {"type": "object", "required": ["targets"], "properties": {"targets": {"type": "array"}}}
KEY = "sk-super-secret-123"


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def calls(monkeypatch):
    """Registra las llamadas HTTP; `calls.resp` define la respuesta."""
    class Calls(list):
        resp = FakeResp()

    c = Calls()

    def fake(method):
        def _f(url, **kw):
            c.append((method, url, kw))
            if isinstance(c.resp, Exception):
                raise c.resp
            return c.resp
        return _f

    monkeypatch.setattr(requests, "post", fake("POST"))
    monkeypatch.setattr(requests, "get", fake("GET"))
    return c


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(http_providers, "get_secret", lambda name: KEY)


# ---------- generate_json (base) ----------

def test_extract_json_plain_fenced_and_embedded():
    assert base.extract_json('{"a": 1}') == {"a": 1}
    assert base.extract_json('Aquí:\n```json\n{"a": {"b": 2}}\n```\nfin') == {"a": {"b": 2}}
    assert base.extract_json('texto {no json} luego {"a": 3} resto') == {"a": 3}


@pytest.mark.parametrize("bad", ["", "sin json", "[1, 2]", '{"a": '])
def test_extract_json_malformed(bad):
    with pytest.raises(AIError):
        base.extract_json(bad)


# ---------- none ----------

def test_none_provider_unavailable():
    p = get_provider(AISettings())
    assert p.name == "none"
    with pytest.raises(AIUnavailable):
        p.generate_text("hola")
    with pytest.raises(AIUnavailable):
        p.generate_json("hola", SCHEMA)
    assert p.check()[0] is False


def test_get_provider_default_uses_config(monkeypatch):
    class Cfg:
        ai = AISettings(provider="ollama")
    monkeypatch.setattr(ai, "get_config", lambda: Cfg())
    assert get_provider().name == "ollama"


# ---------- ollama ----------

def test_ollama_text(calls):
    calls.resp = FakeResp(payload={"message": {"content": "hola"}})
    p = get_provider(AISettings(provider="ollama"))
    assert p.generate_text("q", system="s") == "hola"
    method, url, kw = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert kw["json"]["model"] == "llama3.1"
    assert kw["json"]["stream"] is False
    assert kw["json"]["messages"] == [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    assert "format" not in kw["json"]
    assert kw["timeout"] == 120


def test_ollama_json_and_custom_base(calls):
    calls.resp = FakeResp(payload={"message": {"content": '{"targets": ["x"]}'}})
    p = get_provider(AISettings(provider="ollama", base_url="http://box:1/", model="m", timeout_seconds=7))
    assert p.generate_json("q", SCHEMA) == {"targets": ["x"]}
    _, url, kw = calls[0]
    assert url == "http://box:1/api/chat"
    assert kw["json"]["format"] == "json" and kw["json"]["model"] == "m" and kw["timeout"] == 7
    assert "targets" in kw["json"]["messages"][-1]["content"]  # esquema embebido


def test_ollama_check(calls):
    p = get_provider(AISettings(provider="ollama"))
    calls.resp = FakeResp(payload={"models": [{"name": "llama3.1"}]})
    ok, msg = p.check()
    assert ok and msg.startswith("Ollama responde en") and calls[0][:2] == ("GET", "http://127.0.0.1:11434/api/tags")
    calls.resp = requests.ConnectionError("boom")
    assert p.check()[0] is False


def test_ollama_timeout_is_aierror(calls):
    calls.resp = requests.Timeout("lento")
    with pytest.raises(AIError):
        get_provider(AISettings(provider="ollama")).generate_text("q")


# ---------- anthropic ----------

def test_anthropic_text(calls, key):
    calls.resp = FakeResp(payload={"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]})
    p = get_provider(AISettings(provider="anthropic"))
    assert p.generate_text("q", system="s") == "ab"
    _, url, kw = calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert kw["headers"]["x-api-key"] == KEY and kw["headers"]["anthropic-version"] == "2023-06-01"
    assert kw["json"]["model"] == "claude-sonnet-5-5" and kw["json"]["max_tokens"] == 4096
    assert kw["json"]["system"] == "s"
    assert kw["json"]["messages"] == [{"role": "user", "content": "q"}]


def test_anthropic_json_fenced(calls, key):
    calls.resp = FakeResp(payload={"content": [{"type": "text", "text": '```json\n{"targets": []}\n```'}]})
    assert get_provider(AISettings(provider="anthropic")).generate_json("q", SCHEMA) == {"targets": []}


def test_json_missing_required_key(calls, key):
    calls.resp = FakeResp(payload={"content": [{"type": "text", "text": '{"otra": 1}'}]})
    with pytest.raises(AIError, match="targets"):
        get_provider(AISettings(provider="anthropic")).generate_json("q", SCHEMA)


def test_json_malformed_reply(calls, key):
    calls.resp = FakeResp(payload={"content": [{"type": "text", "text": "lo siento"}]})
    with pytest.raises(AIError):
        get_provider(AISettings(provider="anthropic")).generate_json("q", SCHEMA)


def test_anthropic_401_no_key_leak(calls, key):
    calls.resp = FakeResp(status=401, payload={"error": {"message": f"bad key {KEY}"}}, text=f"bad {KEY}")
    with pytest.raises(AIError) as ei:
        get_provider(AISettings(provider="anthropic")).generate_text("q")
    assert "401" in str(ei.value) and KEY not in str(ei.value)


def test_anthropic_exception_no_key_leak(calls, key):
    calls.resp = requests.ConnectionError(f"fallo con {KEY}")
    with pytest.raises(AIError) as ei:
        get_provider(AISettings(provider="anthropic")).generate_text("q")
    assert KEY not in str(ei.value)


def test_anthropic_missing_key(monkeypatch, calls):
    monkeypatch.setattr(http_providers, "get_secret", lambda name: None)
    p = get_provider(AISettings(provider="anthropic"))
    with pytest.raises(AIUnavailable):
        p.generate_text("q")
    assert p.check() == (False, "Falta la clave de API")
    assert calls == []


def test_anthropic_check_variants(calls, key):
    p = get_provider(AISettings(provider="anthropic"))
    calls.resp = FakeResp(status=200, payload={})
    assert p.check() == (True, "Clave de API válida")
    m, url, kw = calls[0]
    assert (m, url) == ("GET", "https://api.anthropic.com/v1/models") and kw["headers"]["x-api-key"] == KEY
    calls.resp = FakeResp(status=401)
    assert p.check() == (False, "Clave rechazada")
    calls.resp = FakeResp(status=500)
    assert p.check() == (False, "No se pudo verificar (HTTP 500)")
    calls.resp = requests.ConnectionError(KEY)
    ok, msg = p.check()
    assert (ok, msg) == (False, "No se pudo conectar") and KEY not in msg


def test_openai_check(calls, key):
    p = get_provider(AISettings(provider="openai", base_url="http://l:1/v1"))
    calls.resp = FakeResp(status=200, payload={})
    assert p.check() == (True, "Clave de API válida")
    assert calls[0][1] == "http://l:1/v1/models" and calls[0][2]["headers"]["Authorization"] == f"Bearer {KEY}"
    calls.resp = FakeResp(status=403)
    assert p.check() == (False, "Clave rechazada")


def test_http_error_carries_status(calls, key):
    calls.resp = FakeResp(status=429)
    with pytest.raises(ai.AIHTTPError) as ei:
        get_provider(AISettings(provider="openai")).generate_text("q")
    assert ei.value.status == 429


def test_extract_json_array_rejected():
    for t in ('[{"a": 1}]', '```json\n[{"a": 1}]\n```'):
        with pytest.raises(AIError):
            base.extract_json(t)


def test_extract_json_prefers_object_with_required():
    t = 'Ejemplo: {} y luego {"targets": ["x"]} fin'
    assert base.extract_json(t, ["targets"]) == {"targets": ["x"]}
    assert base.extract_json('{"targets": 1} y {"otro": 2}', ["targets"]) == {"targets": 1}


def test_ollama_options_and_model_check(calls):
    calls.resp = FakeResp(payload={"message": {"content": "x"}})
    get_provider(AISettings(provider="ollama")).generate_text("q")
    assert calls[0][2]["json"]["options"] == {"num_ctx": 8192}
    p = get_provider(AISettings(provider="ollama"))
    calls.resp = FakeResp(payload={"models": [{"name": "llama3.1:latest"}]})
    assert p.check()[0] is True
    calls.resp = FakeResp(payload={"models": [{"name": "otro:7b"}]})
    assert p.check() == (False, "Modelo llama3.1 no descargado: ollama pull llama3.1")


# ---------- openai ----------

def test_openai_text_and_json(calls, key):
    calls.resp = FakeResp(payload={"choices": [{"message": {"content": '{"targets": ["t"]}'}}]})
    p = get_provider(AISettings(provider="openai"))
    assert p.generate_json("q", SCHEMA, system="s") == {"targets": ["t"]}
    _, url, kw = calls[0]
    assert url == "https://api.openai.com/v1/chat/completions"
    assert kw["headers"]["Authorization"] == f"Bearer {KEY}"
    assert kw["json"]["model"] == "gpt-4o-mini"
    assert kw["json"]["response_format"] == {"type": "json_object"}
    assert kw["json"]["messages"][0] == {"role": "system", "content": "s"}
    assert p.generate_text("q") == '{"targets": ["t"]}'
    assert "response_format" not in calls[1][2]["json"]


def test_openai_base_url_and_401(calls, key):
    calls.resp = FakeResp(status=401, text=KEY)
    p = get_provider(AISettings(provider="openai", base_url="http://local:9/v1/"))
    with pytest.raises(AIError) as ei:
        p.generate_text("q")
    assert calls[0][1] == "http://local:9/v1/chat/completions"
    assert "401" in str(ei.value) and KEY not in str(ei.value)


def test_openai_missing_key(monkeypatch):
    monkeypatch.setattr(http_providers, "get_secret", lambda name: None)
    with pytest.raises(AIUnavailable):
        get_provider(AISettings(provider="openai")).generate_text("q")


def test_unexpected_payload_shape(calls, key):
    calls.resp = FakeResp(payload={"nope": 1})
    with pytest.raises(AIError):
        get_provider(AISettings(provider="openai")).generate_text("q")


# ---------- CLI ----------

class Run:
    def __init__(self, monkeypatch, which="/usr/bin/x", rc=0, out="respuesta", err=""):
        self.calls = []
        self.rc, self.out, self.err = rc, out, err
        monkeypatch.setattr(cli_providers.shutil, "which", lambda name: which)
        monkeypatch.setattr(cli_providers.subprocess, "run", self._run)

    def _run(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if isinstance(self.rc, Exception):
            raise self.rc
        return subprocess.CompletedProcess(cmd, self.rc, self.out, self.err)


def test_claude_cli_text_and_json(monkeypatch):
    r = Run(monkeypatch, out='```json\n{"targets": []}\n```')
    p = get_provider(AISettings(provider="claude_cli", timeout_seconds=9))
    assert p.generate_json("q", SCHEMA, system="sis") == {"targets": []}
    cmd, kw = r.calls[0]
    assert cmd == ["claude", "-p", "--output-format", "text"]
    assert kw["input"].startswith("sis") and "q" in kw["input"] and not any("q" == a for a in cmd)
    assert kw["capture_output"] is True and kw["text"] is True and kw["timeout"] == 9
    assert kw["cwd"] and kw["cwd"].startswith(tempfile.gettempdir())


def test_codex_cli_text(monkeypatch):
    r = Run(monkeypatch, out="hola\n")
    assert get_provider(AISettings(provider="codex_cli")).generate_text("q") == "hola"
    cmd, kw = r.calls[0]
    assert cmd == ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-"] and kw["input"] == "q"


def test_cli_nonzero_exit_stderr_tail(monkeypatch):
    Run(monkeypatch, rc=1, err="x" * 1000 + "FINAL")
    with pytest.raises(AIError) as ei:
        get_provider(AISettings(provider="claude_cli")).generate_text("q")
    assert str(ei.value).endswith("FINAL") and len(str(ei.value)) < 400


def test_cli_not_installed(monkeypatch):
    r = Run(monkeypatch, which=None)
    p = get_provider(AISettings(provider="codex_cli"))
    with pytest.raises(AIUnavailable):
        p.generate_text("q")
    assert p.check() == (False, "codex no está instalado")
    assert r.calls == []


def test_cli_timeout(monkeypatch):
    Run(monkeypatch, rc=subprocess.TimeoutExpired("claude", 1))
    with pytest.raises(AIError):
        get_provider(AISettings(provider="claude_cli")).generate_text("q")


def test_claude_cli_check(monkeypatch):
    Run(monkeypatch)
    assert get_provider(AISettings(provider="claude_cli")).check()[0] is True
    Run(monkeypatch, rc=1)
    assert get_provider(AISettings(provider="claude_cli")).check() == (False, "claude sin sesión")
    Run(monkeypatch, which=None)
    assert get_provider(AISettings(provider="claude_cli")).check() == (False, "claude no está instalado")
    Run(monkeypatch, rc=subprocess.TimeoutExpired("claude", 1))
    assert get_provider(AISettings(provider="claude_cli")).check() == (False, "Tiempo agotado comprobando claude")
    Run(monkeypatch, rc=PermissionError("x"))
    assert get_provider(AISettings(provider="claude_cli")).check() == (False, "No se pudo ejecutar claude")


def test_cli_prompt_never_in_argv(monkeypatch):
    r = Run(monkeypatch)
    get_provider(AISettings(provider="claude_cli")).generate_text("--peligroso secreto")
    cmd, kw = r.calls[0]
    assert not any("peligroso" in a for a in cmd) and kw["input"] == "--peligroso secreto"
