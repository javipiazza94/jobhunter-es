"""Tests de secrets_store con un llavero en memoria (nunca toca el llavero real del sistema)."""
import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, NoKeyringError

import secrets_store


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.data = {}

    def get_password(self, service, username):
        return self.data.get((service, username))

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.data:
            raise keyring.errors.PasswordDeleteError("no existe")
        del self.data[(service, username)]


class FailingKeyring(KeyringBackend):
    priority = 1

    def get_password(self, service, username):
        raise NoKeyringError("sin backend")

    def set_password(self, service, username, password):
        raise KeyringError("sin backend")

    def delete_password(self, service, username):
        raise KeyringError("sin backend")


@pytest.fixture
def mem(monkeypatch):
    for var in secrets_store.ENV_FALLBACK.values():
        monkeypatch.delenv(var, raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def failing(monkeypatch):
    for var in secrets_store.ENV_FALLBACK.values():
        monkeypatch.delenv(var, raising=False)
    previous = keyring.get_keyring()
    keyring.set_keyring(FailingKeyring())
    yield
    keyring.set_keyring(previous)


def test_keychain_used_when_env_absent(mem):
    secrets_store.set_secret("anthropic_api_key", "sk-keychain")
    assert mem.data[("jobhunter", "anthropic_api_key")] == "sk-keychain"
    assert secrets_store.get_secret("anthropic_api_key") == "sk-keychain"
    assert secrets_store.has_secret("anthropic_api_key") is True


def test_env_wins_over_keychain(mem, monkeypatch):
    secrets_store.set_secret("smtp_password", "from-keychain")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "from-env")
    assert secrets_store.get_secret("smtp_password") == "from-env"


def test_missing_secret_is_none(mem):
    assert secrets_store.get_secret("openai_api_key") is None
    assert secrets_store.has_secret("openai_api_key") is False


def test_delete_secret(mem):
    secrets_store.set_secret("openai_api_key", "sk-x")
    secrets_store.delete_secret("openai_api_key")
    assert secrets_store.get_secret("openai_api_key") is None


def test_delete_missing_secret_is_noop(mem):
    secrets_store.delete_secret("openai_api_key")


def test_failing_backend_get_returns_none(failing):
    assert secrets_store.get_secret("anthropic_api_key") is None
    assert secrets_store.has_secret("anthropic_api_key") is False


def test_failing_backend_env_fallback_still_works(failing, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert secrets_store.get_secret("anthropic_api_key") == "sk-env"


def test_failing_backend_set_and_delete_raise(failing):
    with pytest.raises(secrets_store.SecretStoreUnavailable):
        secrets_store.set_secret("anthropic_api_key", "sk-secret")
    with pytest.raises(secrets_store.SecretStoreUnavailable):
        secrets_store.delete_secret("anthropic_api_key")


def test_unavailable_error_does_not_leak_value(failing):
    with pytest.raises(secrets_store.SecretStoreUnavailable) as exc:
        secrets_store.set_secret("anthropic_api_key", "sk-top-secret")
    assert "sk-top-secret" not in str(exc.value)


def test_unknown_name_raises_value_error(mem):
    for fn in (secrets_store.get_secret, secrets_store.has_secret, secrets_store.delete_secret):
        with pytest.raises(ValueError):
            fn("nope")
    with pytest.raises(ValueError):
        secrets_store.set_secret("nope", "x")


def test_without_keyring_module_env_still_works(monkeypatch):
    """Si `keyring` no está instalado: lectura por entorno, guardar avisa con SecretStoreUnavailable."""
    import secrets_store

    monkeypatch.setattr(secrets_store, "keyring", None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert secrets_store.get_secret("openai_api_key") == "sk-env"
    monkeypatch.delenv("OPENAI_API_KEY")
    assert secrets_store.get_secret("openai_api_key") is None
    with pytest.raises(secrets_store.SecretStoreUnavailable):
        secrets_store.set_secret("openai_api_key", "x")


def test_set_secret_rejects_non_text():
    import secrets_store

    with pytest.raises(ValueError):
        secrets_store.set_secret("openai_api_key", "")
