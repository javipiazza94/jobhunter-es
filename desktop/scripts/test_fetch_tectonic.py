"""fetch_tectonic.py con archivos sintéticos (sin red)."""
import hashlib
import io
import json
import os
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import fetch_tectonic as ft  # noqa: E402


def tar_gz(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class Resp:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.data[:n] if n >= 0 else self.data


def manifest(sha: str | None, target="x86_64-unknown-linux-musl", file="tectonic-{version}-x.tar.gz"):
    return {"version": "9.9.9", "base_url": "https://example.test/v{version}/",
            "assets": {target: {"file": file, "sha256": sha}}}


def test_el_manifiesto_real_cubre_las_cuatro_plataformas():
    m = ft.load_manifest()
    assert set(m["assets"]) == {"x86_64-unknown-linux-musl", "x86_64-pc-windows-msvc", "x86_64-apple-darwin", "aarch64-apple-darwin"}
    for target in m["assets"]:
        url, _ = ft.asset_for(m, target)
        assert url.startswith("https://github.com/tectonic-typesetting/tectonic/releases/download/") and "{" not in url


def test_hash_correcto_extrae_y_hace_ejecutable(tmp_path):
    archive = tar_gz({"tectonic": b"#!/bin/sh\necho hola\n"})
    m = manifest(hashlib.sha256(archive).hexdigest())
    exe = ft.fetch("x86_64-unknown-linux-musl", tmp_path, m, opener=lambda url, timeout: Resp(archive))
    assert exe == tmp_path / "tectonic" and exe.read_bytes().startswith(b"#!/bin/sh")
    if os.name == "posix":
        assert os.access(exe, os.X_OK)


def test_hash_incorrecto_se_rechaza_y_no_escribe_nada(tmp_path):
    archive = tar_gz({"tectonic": b"binario"})
    with pytest.raises(ft.TectonicError, match="SHA-256 incorrecto"):
        ft.fetch("x86_64-unknown-linux-musl", tmp_path, manifest("0" * 64), opener=lambda url, timeout: Resp(archive))
    assert list(tmp_path.iterdir()) == []


def test_sin_hash_fijado_se_rechaza_salvo_ensayo(tmp_path, capsys):
    archive = tar_gz({"tectonic": b"binario"})
    opener = lambda url, timeout: Resp(archive)  # noqa: E731
    with pytest.raises(ft.TectonicError, match="Falta el SHA-256"):
        ft.fetch("x86_64-unknown-linux-musl", tmp_path, manifest(None), opener=opener)
    exe = ft.fetch("x86_64-unknown-linux-musl", tmp_path, manifest(None), allow_unverified=True, opener=opener)
    assert exe.exists()
    assert hashlib.sha256(archive).hexdigest() in capsys.readouterr().out


def test_zip_de_windows(tmp_path):
    archive = zip_bytes({"tectonic.exe": b"MZ..."})
    m = manifest(hashlib.sha256(archive).hexdigest(), "x86_64-pc-windows-msvc", "tectonic-{version}.zip")
    exe = ft.fetch("x86_64-pc-windows-msvc", tmp_path, m, opener=lambda url, timeout: Resp(archive))
    assert exe.name == "tectonic.exe"


def test_una_ruta_maliciosa_dentro_del_archivo_no_decide_donde_se_escribe(tmp_path):
    dest = tmp_path / "bin"
    archive = zip_bytes({"../../escape/tectonic.exe": b"MZ"})
    exe = ft.extract_binary(archive, "https://x/y.zip", dest)
    assert exe.parent == dest and not (tmp_path / "escape").exists()
    archive = tar_gz({"../../otro/tectonic": b"x"})
    exe = ft.extract_binary(archive, "https://x/y.tar.gz", dest)
    assert exe.parent == dest and not (tmp_path / "otro").exists()


def test_archivo_sin_ejecutable(tmp_path):
    with pytest.raises(ft.TectonicError, match="no contiene"):
        ft.extract_binary(tar_gz({"LEEME": b"x"}), "https://x/y.tar.gz", tmp_path)


def test_solo_https_y_plataforma_conocida(tmp_path):
    with pytest.raises(ft.TectonicError, match="https"):
        ft.download("http://example.test/x")
    with pytest.raises(ft.TectonicError, match="No hay Tectonic"):
        ft.asset_for(manifest(None), "riscv64-unknown-none")


def test_el_manifiesto_es_json_valido():
    json.loads(ft.MANIFEST.read_text(encoding="utf-8"))
