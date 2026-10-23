"""Descarga Tectonic (versión fijada en tectonic.json), verifica su SHA-256 y lo deja en
`desktop/src-tauri/resources/bin/` para que Tauri lo incluya en el instalador.

Uso:
  python desktop/scripts/fetch_tectonic.py [--target TRIPLE] [--out DIR] [--allow-unverified]

Sin hash fijado en tectonic.json la descarga se rechaza, salvo con --allow-unverified (solo para el
ensayo manual que imprime los hashes que hay que fijar). El binario se extrae por su nombre: ninguna
ruta del archivo comprimido decide dónde se escribe.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "tectonic.json"
DEFAULT_OUT = HERE.parent / "src-tauri" / "resources" / "bin"
MAX_BYTES = 200 * 1024 * 1024


class TectonicError(RuntimeError):
    pass


def host_target() -> str:
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "aarch64-apple-darwin" if arm else "x86_64-apple-darwin"
    if sys.platform == "win32":
        return "x86_64-pc-windows-msvc"
    return "x86_64-unknown-linux-musl"


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def asset_for(manifest: dict, target: str) -> tuple[str, str | None]:
    """(URL, sha256 o None) del asset de ese triple."""
    try:
        asset = manifest["assets"][target]
    except KeyError:
        raise TectonicError(f"No hay Tectonic fijado para {target}: {sorted(manifest['assets'])}") from None
    version = manifest["version"]
    return manifest["base_url"].format(version=version) + asset["file"].format(version=version), asset.get("sha256")


def download(url: str, opener=urllib.request.urlopen) -> bytes:
    if not url.startswith("https://"):
        raise TectonicError("Solo se descarga por https")
    with opener(url, timeout=120) as res:
        data = res.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise TectonicError("La descarga supera el tamaño máximo esperado")
    return data


def extract_binary(archive: bytes, url: str, dest_dir: Path) -> Path:
    """Extrae solo el ejecutable `tectonic`/`tectonic.exe`, escribiéndolo con ese nombre en `dest_dir`."""
    wanted = {"tectonic", "tectonic.exe"}
    dest_dir.mkdir(parents=True, exist_ok=True)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            for info in zf.infolist():
                name = Path(info.filename).name
                if name in wanted and not info.is_dir():
                    return _write(dest_dir / name, zf.read(info))
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            for member in tf:
                name = Path(member.name).name
                if name in wanted and member.isfile():
                    return _write(dest_dir / name, tf.extractfile(member).read())  # type: ignore[union-attr]
    raise TectonicError("El archivo descargado no contiene el ejecutable de Tectonic")


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def fetch(target: str, out: Path, manifest: dict | None = None, *, allow_unverified: bool = False,
          opener=urllib.request.urlopen) -> Path:
    manifest = manifest or load_manifest()
    url, expected = asset_for(manifest, target)
    if expected is None and not allow_unverified:
        raise TectonicError(
            f"Falta el SHA-256 de {target} en tectonic.json: no se instala un binario sin verificar. "
            "Ejecuta el workflow «Desktop» a mano para obtener los hashes.")
    data = download(url, opener)
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None and digest != expected.lower():
        raise TectonicError(f"SHA-256 incorrecto para {url}: esperado {expected}, obtenido {digest}")
    print(f"{target} sha256={digest}" + ("" if expected else "  (SIN VERIFICAR: fíjalo en tectonic.json)"))
    return extract_binary(data, url, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default=host_target())
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()
    try:
        print(f"OK: {fetch(args.target, args.out, allow_unverified=args.allow_unverified)}")
    except TectonicError as exc:
        raise SystemExit(f"ERROR: {exc}") from None


if __name__ == "__main__":
    main()
