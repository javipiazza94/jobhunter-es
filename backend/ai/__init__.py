"""
ai — Capa de proveedores de IA (ollama, anthropic, openai, claude_cli, codex_cli, none).

Uso: `get_provider().generate_json(prompt, schema)`. Con `none` lanza `AIUnavailable` y los
llamadores caen a su alternativa sin IA.
"""
from search_config import AISettings, get_config

from .base import AIError, AIHTTPError, AIUnavailable, NoneProvider, Provider
from .cli_providers import ClaudeCliProvider, CodexCliProvider
from .http_providers import AnthropicProvider, OllamaProvider, OpenAIProvider

_PROVIDERS = {
    "ollama": OllamaProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "claude_cli": ClaudeCliProvider,
    "codex_cli": CodexCliProvider,
}

__all__ = ["AIError", "AIHTTPError", "AIUnavailable", "Provider", "get_provider"]


def get_provider(settings: AISettings | None = None) -> Provider:
    """Proveedor según `settings` (por defecto `get_config().ai`)."""
    settings = settings or get_config().ai
    cls = _PROVIDERS.get(settings.provider)
    return cls(settings) if cls else NoneProvider()
