"""
cli_providers.py — Proveedores por CLI local: `claude -p` y `codex exec`.

La app no guarda credenciales de suscripción: solo comprueba que el CLI está instalado y con sesión.

Seguridad: al CLI (agéntico) le llega texto no confiable (ofertas, CV). Por eso el prompt va por stdin
(nunca en argv: sin límites de tamaño ni prompts que empiecen por «-») y el proceso se ejecuta aislado
en un directorio temporal vacío; `codex` además en sandbox de solo lectura.
"""
import shutil
import subprocess
import tempfile

from search_config import AISettings

from .base import AIError, AIUnavailable, BaseProvider


class _CliTimeout(AIError):
    pass


class _CliExecError(AIError):
    pass


class _CliProvider(BaseProvider):
    binary = ""

    def __init__(self, settings: AISettings):
        self.timeout = settings.timeout_seconds

    def _command(self) -> list[str]:
        raise NotImplementedError

    def _run(self, prompt: str, timeout: int) -> subprocess.CompletedProcess:
        try:
            with tempfile.TemporaryDirectory(prefix="jh-ai-") as cwd:
                return subprocess.run(
                    self._command(), input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd
                )
        except subprocess.TimeoutExpired:
            raise _CliTimeout(f"{self.binary}: tiempo de espera agotado") from None
        except OSError as exc:
            raise _CliExecError(f"{self.binary}: no se pudo ejecutar ({type(exc).__name__})") from None

    def _complete(self, prompt, system, json_mode):
        if not shutil.which(self.binary):
            raise AIUnavailable(f"{self.binary} no está instalado")
        full = f"{system}\n\n{prompt}" if system else prompt
        proc = self._run(full, self.timeout)
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-300:]
            raise AIError(f"{self.binary} terminó con código {proc.returncode}: {tail}")
        return (proc.stdout or "").strip()

    def check(self) -> tuple[bool, str]:
        if not shutil.which(self.binary):
            return False, f"{self.binary} no está instalado"
        try:
            proc = self._run("ok", min(self.timeout, 60))
        except _CliTimeout:
            return False, f"Tiempo agotado comprobando {self.binary}"
        except _CliExecError:
            return False, f"No se pudo ejecutar {self.binary}"
        if proc.returncode != 0:
            return False, f"{self.binary} sin sesión"
        return True, f"{self.binary} listo"


class ClaudeCliProvider(_CliProvider):
    name = "claude_cli"
    binary = "claude"

    def _command(self):
        return ["claude", "-p", "--output-format", "text"]


class CodexCliProvider(_CliProvider):
    name = "codex_cli"
    binary = "codex"

    def _command(self):
        return ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-"]
