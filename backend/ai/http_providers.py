"""
http_providers.py — Proveedores por HTTP (`requests`, sin SDKs): ollama, anthropic y openai.

Los errores solo citan el código de estado o el tipo de excepción: nunca la clave ni el cuerpo.
"""
import requests

from search_config import AISettings
from secrets_store import get_secret

from .base import AIError, AIHTTPError, AIUnavailable, BaseProvider


class _HttpProvider(BaseProvider):
    def __init__(self, settings: AISettings):
        self.settings = settings
        self.timeout = settings.timeout_seconds

    def _request(self, method: str, url: str, **kw) -> requests.Response:
        try:
            resp = getattr(requests, method)(url, timeout=self.timeout, **kw)
        except requests.RequestException as exc:
            raise AIError(f"{self.name}: fallo de red ({type(exc).__name__})") from None
        if not 200 <= resp.status_code < 300:
            raise AIHTTPError(f"{self.name}: la API respondió HTTP {resp.status_code}", resp.status_code)
        return resp

    def _json(self, resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            raise AIError(f"{self.name}: respuesta no JSON") from None
        if not isinstance(data, dict):
            raise AIError(f"{self.name}: respuesta inesperada")
        return data


class OllamaProvider(_HttpProvider):
    name = "ollama"

    def _base(self) -> str:
        return (self.settings.base_url or "http://127.0.0.1:11434").rstrip("/")

    def _complete(self, prompt, system, json_mode):
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        body = {"model": self.settings.model or "llama3.1", "messages": messages, "stream": False,
                "options": {"num_ctx": 8192}}
        if json_mode:
            body["format"] = "json"
        data = self._json(self._request("post", f"{self._base()}/api/chat", json=body))
        try:
            return str(data["message"]["content"])
        except (KeyError, TypeError):
            raise AIError("ollama: respuesta inesperada") from None

    def check(self) -> tuple[bool, str]:
        try:
            data = self._json(self._request("get", f"{self._base()}/api/tags"))
        except AIError as exc:
            return False, f"Ollama no responde en {self._base()} ({exc})"
        model = self.settings.model or "llama3.1"
        names = {m.get("name") for m in data.get("models", []) if isinstance(m, dict)}
        if model not in names and f"{model}:latest" not in names:
            return False, f"Modelo {model} no descargado: ollama pull {model}"
        return True, f"Ollama responde en {self._base()}"


class _KeyedProvider(_HttpProvider):
    secret_name = ""

    def _key(self) -> str:
        key = get_secret(self.secret_name)
        if not key:
            raise AIUnavailable("Falta la clave de API")
        return key

    def _verify_request(self, key: str):
        raise NotImplementedError

    def check(self) -> tuple[bool, str]:
        key = get_secret(self.secret_name)
        if not key:
            return False, "Falta la clave de API"
        url, headers = self._verify_request(key)
        try:
            status = requests.get(url, headers=headers, timeout=self.timeout).status_code
        except requests.RequestException:
            return False, "No se pudo conectar"
        if status == 200:
            return True, "Clave de API válida"
        if status in (401, 403):
            return False, "Clave rechazada"
        return False, f"No se pudo verificar (HTTP {status})"


class AnthropicProvider(_KeyedProvider):
    name = "anthropic"
    secret_name = "anthropic_api_key"

    def _verify_request(self, key):
        return "https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"}

    def _complete(self, prompt, system, json_mode):
        headers = {"x-api-key": self._key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {
            "model": self.settings.model or "claude-sonnet-5-5",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        data = self._json(
            self._request("post", "https://api.anthropic.com/v1/messages", headers=headers, json=body)
        )
        try:
            return "".join(b.get("text", "") for b in data["content"] if isinstance(b, dict))
        except (KeyError, TypeError):
            raise AIError("anthropic: respuesta inesperada") from None


class OpenAIProvider(_KeyedProvider):
    name = "openai"
    secret_name = "openai_api_key"

    def _verify_request(self, key):
        base = (self.settings.base_url or "https://api.openai.com/v1").rstrip("/")
        return f"{base}/models", {"Authorization": f"Bearer {key}"}

    def _complete(self, prompt, system, json_mode):
        headers = {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        body = {"model": self.settings.model or "gpt-4o-mini", "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        base = (self.settings.base_url or "https://api.openai.com/v1").rstrip("/")
        data = self._json(self._request("post", f"{base}/chat/completions", headers=headers, json=body))
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise AIError("openai: respuesta inesperada") from None
