"""Plantillas propias de CV y carta: registro con compilación de prueba, activación y API."""
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import search_config  # noqa: E402
from automation import document_generator, templates_registry  # noqa: E402
from automation.latex_compiler import engine_available  # noqa: E402
from tests.asgi_client import call  # noqa: E402

requires_engine = pytest.mark.skipif(engine_available() is None, reason="no hay motor LaTeX instalado")
requires_typst = pytest.mark.skipif(shutil.which("typst") is None, reason="typst no instalado")
CLIENT = ("x-jh-client", "dashboard")

CV_TEMPLATE = (
    "\\documentclass[a4paper]{article}\n\\begin{document}\n"
    "MI-PLANTILLA-PROPIA ((( personal.name | latex_escape )))\n\\end{document}\n"
)
LETTER_TEMPLATE = CV_TEMPLATE
TYPST_TEMPLATE = "= ((( personal.name | typst_escape )))\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """JH_HOME temporal con un jobhunter.yaml propio; restaura la config fijada por los tests."""
    original = search_config.get_config()
    monkeypatch.setattr(config, "JH_HOME", tmp_path)
    search_config.save_config(original, search_config.user_config_path())
    yield tmp_path
    search_config.set_config(original)


def _zip(members: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


class TestListing:
    def test_builtins_always_listed_and_active_by_default(self, home):
        listing = {(t.kind, t.name): t for t in templates_registry.list_templates()}
        assert listing[("cv", "moderncv-banking")].builtin and listing[("cv", "moderncv-banking")].active
        assert listing[("letter", "cover-cls")].builtin and listing[("letter", "cover-cls")].active

    def test_builtin_cannot_be_deleted(self, home):
        with pytest.raises(templates_registry.TemplateError):
            templates_registry.delete_template("cv", "moderncv-banking")

    def test_unknown_template(self, home):
        with pytest.raises(templates_registry.TemplateNotFound):
            templates_registry.activate_template("cv", "no-existe")

    def test_active_name_missing_falls_back_to_builtin(self, home):
        cfg = search_config.get_config()
        docs = cfg.documents.model_copy(update={"cv_template": "borrada"})
        search_config.save_config(cfg.model_copy(update={"documents": docs}), search_config.user_config_path())
        assert templates_registry.active_template("cv") is None


class TestValidation:
    @pytest.mark.parametrize("name", ["", "Mayus", "../x", "a b", "-x", "x" * 41, "moderncv-banking"])
    def test_bad_names(self, home, name):
        with pytest.raises(templates_registry.TemplateError):
            templates_registry.register_template(name, "cv", {"a.tex.j2": b"x"})

    def test_bad_kind_and_engine(self, home):
        with pytest.raises(templates_registry.TemplateError):
            templates_registry.register_template("ok", "otro", {"a.tex.j2": b"x"})
        with pytest.raises(templates_registry.TemplateError):
            templates_registry.register_template("ok", "cv", {"a.tex.j2": b"x"}, engine="word")

    def test_missing_main_file(self, home):
        with pytest.raises(templates_registry.TemplateError, match="principal"):
            templates_registry.register_template("ok", "cv", {"notas.txt": b"x"})

    @pytest.mark.parametrize("compiler", ["latexmk", "pdflatex", "sh", "/usr/bin/xelatex", "xelatex -shell-escape"])
    def test_only_known_compilers(self, home, compiler):
        with pytest.raises(templates_registry.TemplateError, match="compilador"):
            templates_registry.register_template("ok", "cv", {"a.tex.j2": b"x"}, compiler=compiler)

    def test_member_paths_cannot_escape(self, home):
        for bad in ("../evil.tex.j2", "/abs/evil.tex.j2", "a/../../evil.tex.j2", "C:/evil.tex.j2"):
            with pytest.raises(templates_registry.TemplateError, match="Ruta no permitida"):
                templates_registry.register_template("ok", "cv", {bad: b"x"})
        assert not (home / "templates" / "evil.tex.j2").exists()

    def test_zip_path_traversal_blocked(self, home):
        data = _zip({"../../evil.tex.j2": "x"})
        with pytest.raises(templates_registry.TemplateError, match="Ruta no permitida"):
            templates_registry.files_from_zip(data)

    def test_zip_symlink_blocked(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            info = zipfile.ZipInfo("link.tex.j2")
            info.external_attr = (0o120777) << 16
            z.writestr(info, "/etc/passwd")
        with pytest.raises(templates_registry.TemplateError, match="simbólicos"):
            templates_registry.files_from_zip(buf.getvalue())

    def test_not_a_zip(self):
        with pytest.raises(templates_registry.TemplateError, match="zip"):
            templates_registry.files_from_zip(b"no es un zip")

    def test_zip_too_many_files(self):
        data = _zip({f"f{i}.txt": "x" for i in range(templates_registry.MAX_ZIP_FILES + 1)})
        with pytest.raises(templates_registry.TemplateError, match="demasiados"):
            templates_registry.files_from_zip(data)

    def test_typst_escape_neutralises_markup(self):
        assert templates_registry.typst_escape("#import 'x' *a* _b_ $c$ @d") == "\\#import 'x' \\*a\\* \\_b\\_ \\$c\\$ \\@d"
        assert templates_registry.typst_escape("hola 😀") == "hola "


class TestRegistration:
    @requires_engine
    def test_valid_latex_template_registers_and_activation_changes_output(self, home):
        info = templates_registry.register_template("mia", "cv", {"cv.tex.j2": CV_TEMPLATE.encode()}, page_limit=1)
        assert info.name == "mia" and not info.builtin and not info.active and info.main_file == "cv.tex.j2"
        assert (home / "templates" / "cv" / "mia" / "template.json").is_file()
        # aún manda la integrada
        assert "MI-PLANTILLA-PROPIA" not in document_generator.render_cv_from_context({"personal": {"name": "Ana"}} | _cv_ctx())
        templates_registry.activate_template("cv", "mia")
        assert templates_registry.active_template("cv").name == "mia"
        assert search_config.get_config().documents.cv_template == "mia"
        rendered = document_generator.render_cv_from_context(_cv_ctx())
        assert "MI-PLANTILLA-PROPIA" in rendered
        assert templates_registry.active_suffix("cv") == ".tex"
        # borrar la activa devuelve la integrada
        templates_registry.delete_template("cv", "mia")
        assert templates_registry.active_template("cv") is None
        assert not (home / "templates" / "cv" / "mia").exists()

    @requires_engine
    def test_template_that_does_not_compile_is_rejected_and_leaves_nothing(self, home):
        broken = b"\\documentclass{article}\\begin{document}\\nonexistentmacro\\end{document}"
        with pytest.raises(templates_registry.TemplateError, match="compilación de prueba"):
            templates_registry.register_template("rota", "cv", {"cv.tex.j2": broken})
        assert not (home / "templates" / "cv" / "rota").exists()
        assert not (home / "templates" / "cv" / "rota.tmp").exists()
        assert all(t.name != "rota" for t in templates_registry.list_templates())

    @requires_engine
    def test_template_over_page_limit_is_rejected(self, home):
        many = "\\documentclass{article}\\begin{document}" + "\\newpage x " * 3 + "\\end{document}"
        with pytest.raises(templates_registry.TemplateError, match="páginas"):
            templates_registry.register_template("larga", "letter", {"c.tex.j2": many.encode()}, page_limit=1)

    def test_jinja_error_is_a_clean_error(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "engine_available", lambda *a, **k: "tectonic")
        with pytest.raises(templates_registry.TemplateError, match="renderizar"):
            templates_registry.register_template("jinja", "cv", {"c.tex.j2": b"((* if *))"})
        assert not (home / "templates" / "cv" / "jinja").exists()

    def test_no_engine_gives_clear_error(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "engine_available", lambda *a, **k: None)
        with pytest.raises(templates_registry.EngineMissing, match="Tectonic"):
            templates_registry.register_template("sinmotor", "cv", {"c.tex.j2": CV_TEMPLATE.encode()})

    def test_typst_without_binary_gives_409_style_error(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry.shutil, "which", lambda *_: None)
        with pytest.raises(templates_registry.EngineMissing, match="typst"):
            templates_registry.register_template("typ", "cv", {"c.typ.j2": TYPST_TEMPLATE.encode()}, engine="typst")

    @requires_typst
    def test_typst_template_registers(self, home):
        info = templates_registry.register_template("typ", "cv", {"c.typ.j2": TYPST_TEMPLATE.encode()}, engine="typst")
        assert info.engine == "typst"

    def test_registration_replaces_atomically(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
        templates_registry.register_template("v", "cv", {"c.tex.j2": b"uno"})
        templates_registry.register_template("v", "cv", {"c.tex.j2": b"dos"})
        assert (home / "templates" / "cv" / "v" / "c.tex.j2").read_bytes() == b"dos"
        assert not (home / "templates" / "cv" / "v.old").exists()

    def test_assets_are_copied_next_to_source(self, home, monkeypatch, tmp_path):
        monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
        templates_registry.register_template(
            "conclase", "letter", {"c.tex.j2": b"x", "mi.cls": b"cls", "fuentes/f.ttf": b"ttf"}
        )
        templates_registry.activate_template("letter", "conclase")
        out = tmp_path / "out"
        out.mkdir()
        assert templates_registry.copy_assets("letter", out) is True
        assert (out / "mi.cls").read_bytes() == b"cls" and (out / "fuentes" / "f.ttf").is_file()
        assert not (out / "c.tex.j2").exists() and not (out / "template.json").exists()


def _cv_ctx() -> dict:
    profile = json.loads((config.REPO_ROOT / "backend" / "profile.example.json").read_text(encoding="utf-8"))
    return document_generator.prepare_cv_context(profile)


class TestAPI:
    def _upload(self, fields, filename, data):
        boundary = "BOUNDARY123"
        body = b""
        for key, value in fields.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        return body, f"multipart/form-data; boundary={boundary}"

    def _post(self, fields, filename, data):
        body, ctype = self._upload(fields, filename, data)
        status, _, text = call("POST", "/api/templates", headers=[CLIENT, ("content-type", ctype),
                                                                   ("content-length", str(len(body)))], body=body)
        return status, text

    def test_list(self, home):
        status, _, text = call("GET", "/api/templates", headers=[CLIENT])
        body = json.loads(text)
        assert status == 200
        assert {(t["kind"], t["name"]) for t in body if t["builtin"]} == {("cv", "moderncv-banking"), ("letter", "cover-cls")}

    def test_upload_bad_name_is_422(self, home):
        status, body = self._post({"name": "../x", "kind": "cv"}, "c.tex.j2", b"x")
        assert status == 422 and "nombre" in body

    def test_upload_without_file_is_400(self, home):
        boundary = "B"
        body = f'--{boundary}\r\nContent-Disposition: form-data; name="name"\r\n\r\nx\r\n--{boundary}--\r\n'.encode()
        status, _, _ = call("POST", "/api/templates", headers=[CLIENT, ("content-type", f"multipart/form-data; boundary={boundary}"),
                                                             ("content-length", str(len(body)))], body=body)
        assert status == 400

    def test_upload_zip_traversal_is_422(self, home):
        status, body = self._post({"name": "zip", "kind": "cv"}, "t.zip", _zip({"../x.tex.j2": "x"}))
        assert status == 422 and "Ruta no permitida" in body

    def test_upload_no_engine_is_409(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "engine_available", lambda *a, **k: None)
        status, _ = self._post({"name": "mia", "kind": "cv"}, "c.tex.j2", CV_TEMPLATE.encode())
        assert status == 409

    def test_upload_activate_delete_flow(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
        status, text = self._post({"name": "mia", "kind": "cv"}, "c.tex.j2", CV_TEMPLATE.encode())
        assert status == 200 and json.loads(text)["name"] == "mia"
        status, _, text = call("POST", "/api/templates/mia/activate", headers=[CLIENT], query="kind=cv")
        assert status == 200 and json.loads(text)["active"] is True
        status, _, text = call("GET", "/api/templates", headers=[CLIENT])
        assert {t["name"] for t in json.loads(text) if t["active"]} == {"mia", "cover-cls"}
        status, _, _ = call("DELETE", "/api/templates/mia", headers=[CLIENT], query="kind=cv")
        assert status == 200
        status, _, _ = call("DELETE", "/api/templates/moderncv-banking", headers=[CLIENT], query="kind=cv")
        assert status == 422
        status, _, _ = call("POST", "/api/templates/nada/activate", headers=[CLIENT], query="kind=cv")
        assert status == 404


class TestPipeline:
    @requires_engine
    def test_generator_uses_active_custom_templates(self, home, tmp_path):
        tpl = ("\\documentclass[a4paper]{article}\n\\begin{document}\n%s ((( personal.name | latex_escape )))\n"
               "\\end{document}\n")
        templates_registry.register_template("cvp", "cv", {"c.tex.j2": (tpl % "CV-PROPIO").encode()}, page_limit=1)
        templates_registry.register_template("carp", "letter", {"c.tex.j2": (tpl % "CARTA-PROPIA").encode()}, page_limit=1)
        templates_registry.activate_template("cv", "cvp")
        templates_registry.activate_template("letter", "carp")
        profile = json.loads((config.REPO_ROOT / "backend" / "profile.example.json").read_text(encoding="utf-8"))
        out = document_generator.generate_deterministic_documents(
            profile_data=profile, output_dir=tmp_path / "out", verify=False
        )
        assert "CV-PROPIO" in out["cv_tex"].read_text(encoding="utf-8")
        assert "CARTA-PROPIA" in out["cover_tex"].read_text(encoding="utf-8")
        assert out["cv_pdf"].is_file() and out["cover_pdf"].is_file()
        assert out["verification"]["pages"] == {"cv": 1, "cover": 1}


# ── Seguridad de las plantillas propias (revisión SP3: C1, C2, I5) ─────────────

SSTI = "((( cycler.__init__.__globals__.os.popen('touch {marker}').read() )))"


def _install_raw(home: Path, kind: str, name: str, files: dict[str, str], **meta) -> Path:
    """Instala una plantilla directamente en disco (como si viniera de una versión anterior) y la activa."""
    target = home / "templates" / kind / name
    target.mkdir(parents=True)
    for rel, text in files.items():
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_text(text, encoding="utf-8")
    data = {"name": name, "kind": kind, "engine": "latex", "main_file": next(iter(files))} | meta
    (target / "template.json").write_text(json.dumps(data), encoding="utf-8")
    cfg = search_config.get_config()
    field = "cv_template" if kind == "cv" else "letter_template"
    docs = cfg.documents.model_copy(update={field: name})
    search_config.save_config(cfg.model_copy(update={"documents": docs}), search_config.user_config_path())
    return target


class TestSandbox:
    def test_ssti_payload_rejected_at_registration(self, home, monkeypatch, tmp_path):
        marker = tmp_path / "pwned"
        monkeypatch.setattr(templates_registry, "engine_available", lambda *a, **k: "tectonic")
        payload = SSTI.format(marker=marker).encode()
        with pytest.raises(templates_registry.TemplateError, match="SecurityError"):
            templates_registry.register_template("ssti", "cv", {"c.tex.j2": payload})
        assert not marker.exists()
        assert not (home / "templates" / "cv" / "ssti").exists()

    def test_ssti_payload_in_installed_template_fails_cleanly_on_render(self, home, tmp_path):
        marker = tmp_path / "pwned"
        _install_raw(home, "cv", "vieja", {"c.tex.j2": SSTI.format(marker=marker)})
        with pytest.raises(templates_registry.TemplateRenderError, match="SecurityError"):
            document_generator.render_cv_from_context(_cv_ctx())
        assert not marker.exists()

    def test_sandbox_raises_security_error(self, tmp_path):
        import jinja2.sandbox

        (tmp_path / "t.tex.j2").write_text("((( cycler.__init__.__globals__ )))", encoding="utf-8")
        env = templates_registry._custom_jinja_env(tmp_path, "latex")
        assert isinstance(env, jinja2.sandbox.ImmutableSandboxedEnvironment)
        with pytest.raises(jinja2.sandbox.SecurityError):
            env.get_template("t.tex.j2").render()


class TestCompilerArgv:
    def test_fixed_argv_per_compiler(self, tmp_path):
        src, out = tmp_path / "cv.tex", tmp_path / "out"
        for engine in ("xelatex", "lualatex"):
            assert templates_registry.compile_argv(engine, src, out) == [
                engine, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                f"-output-directory={out}", str(src),
            ]
        assert templates_registry.compile_argv("tectonic", src, out, passes=1) == [
            "tectonic", "--untrusted", "-o", str(out), "--reruns", "0", str(src),
        ]
        assert templates_registry.compile_argv("tectonic", src, out, passes=2) == [
            "tectonic", "--untrusted", "-o", str(out), str(src),
        ]
        typ = tmp_path / "cv.typ"
        assert templates_registry.compile_argv("typst", typ, out) == [
            "typst", "compile", "--root", str(tmp_path), str(typ), str(out / "cv.pdf"),
        ]

    @pytest.mark.parametrize("compiler", ["latexmk", "pdflatex", "sh", "xelatex -shell-escape"])
    def test_unknown_compiler_rejected(self, tmp_path, compiler):
        with pytest.raises(templates_registry.TemplateError, match="compilador"):
            templates_registry.compile_argv(compiler, tmp_path / "a.tex", tmp_path)

    def test_custom_latex_runs_fixed_argv_with_paranoid_env(self, tmp_path, monkeypatch):
        seen = []

        def fake_run(cmd, cwd=None, env=None, **kwargs):
            seen.append((cmd, env))
            (tmp_path / "out" / "cv.pdf").write_bytes(b"%PDF")
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(templates_registry, "_resolve_binary", lambda name: f"/opt/bin/{name}")
        monkeypatch.setattr(templates_registry.subprocess, "run", fake_run)
        src = tmp_path / "cv.tex"
        src.write_text("x", encoding="utf-8")
        pdf = templates_registry._compile(src, tmp_path / "out", 2, "latex", "xelatex")
        assert pdf == tmp_path / "out" / "cv.pdf"
        assert len(seen) == 2  # dos pasadas
        cmd, env = seen[0]
        assert cmd[0] == "/opt/bin/xelatex" and "-no-shell-escape" in cmd
        assert env["openin_any"] == "p" and env["openout_any"] == "p" and env["shell_escape"] == "f"
        assert all("latexmk" not in c for c, _ in seen for c in c)

    def test_latexmkrc_and_texmf_are_stripped(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
        templates_registry.register_template("rc", "cv", {
            "c.tex.j2": b"x", "latexmkrc": b"system('id')", "sub/.latexmkrc": b"y", "texmf.cnf": b"z",
            "LATEXMKRC": b"w",
        })
        stored = {p.name for p in (home / "templates" / "cv" / "rc").rglob("*")}
        assert stored.isdisjoint({"latexmkrc", ".latexmkrc", "texmf.cnf", "LATEXMKRC"})

    def test_api_ignores_free_compile_cmd_and_rejects_bad_compiler(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
        api = TestAPI()
        status, text = api._post({"name": "mia", "kind": "cv", "compile_cmd": "latexmk -e 'system(1)' {input}"},
                                 "c.tex.j2", CV_TEMPLATE.encode())
        assert status == 200 and json.loads(text)["compiler"] is None
        stored = json.loads((home / "templates" / "cv" / "mia" / "template.json").read_text(encoding="utf-8"))
        assert "compile_cmd" not in stored
        status, text = api._post({"name": "otra", "kind": "cv", "compiler": "latexmk"}, "c.tex.j2", CV_TEMPLATE.encode())
        assert status == 422 and "compilador" in text


class TestLegacyCompileCmd:
    @pytest.mark.parametrize("cmd,compiler", [
        ("xelatex -shell-escape {input}", "xelatex"),
        ("xelatex -output-directory=/home {input}", "xelatex"),
        ("typst compile --root / {input} {output}", "typst"),
        ("tectonic {input}", "tectonic"),
    ])
    def test_known_engine_is_mapped_and_flags_dropped(self, home, cmd, compiler):
        _install_raw(home, "cv", "vieja", {"c.tex.j2": "x"}, compile_cmd=cmd)
        info = templates_registry.active_template("cv")
        assert info is not None and info.compiler == compiler and info.invalid_reason is None

    @pytest.mark.parametrize("cmd", ["latexmk -e '$pdflatex=q/sh -c id/' -pdf {input}", "pdflatex {input}", "sh -c id", "'"])
    def test_unknown_command_marks_template_invalid(self, home, cmd):
        _install_raw(home, "cv", "vieja", {"c.tex.j2": "x"}, compile_cmd=cmd)
        listing = {t.name: t for t in templates_registry.list_templates() if t.kind == "cv"}
        assert listing["vieja"].invalid_reason
        assert not listing["vieja"].active and listing["moderncv-banking"].active
        assert templates_registry.active_template("cv") is None
        with pytest.raises(templates_registry.TemplateError, match="no es válida"):
            templates_registry.activate_template("cv", "vieja")


class TestEscapingAndLint:
    def test_custom_latex_escapes_every_output_by_default(self, tmp_path):
        (tmp_path / "t.tex.j2").write_text(
            "A:((( v ))) B:((( v | latex_escape ))) C:((( raw | safe_raw ))) U:((( url | latex_url ))) N:((( n )))",
            encoding="utf-8",
        )
        env = templates_registry._custom_jinja_env(tmp_path, "latex")
        out = env.get_template("t.tex.j2").render(v="R&D_50% {x}", raw="\\textbf{ok}", url="https://e.org/a%b", n=3)
        assert "A:R\\&D\\_50\\% \\{x\\}" in out
        assert "B:R\\&D\\_50\\% \\{x\\}" in out  # sin doble escape
        assert "C:\\textbf{ok}" in out
        assert "U:https://e.org/a\\%b" in out
        assert "N:3" in out

    def test_profile_injection_is_neutralised_in_custom_template(self, home):
        _install_raw(home, "cv", "propia", {"c.tex.j2": "NOMBRE ((( personal.name )))"})
        ctx = _cv_ctx()
        ctx["personal"] = {**ctx["personal"], "name": "\\input{/etc/passwd}"}
        rendered = document_generator.render_cv_from_context(ctx)
        assert "\\input{" not in rendered and "\\textbackslash{}input\\{/etc/passwd\\}" in rendered

    def test_custom_typst_escapes_by_default(self, tmp_path):
        (tmp_path / "t.typ.j2").write_text("= ((( v )))", encoding="utf-8")
        env = templates_registry._custom_jinja_env(tmp_path, "typst")
        assert env.get_template("t.typ.j2").render(v="#read(\"/etc/passwd\")") == "= \\#read(\"/etc/passwd\")"

    @pytest.mark.parametrize("src", [
        "\\input{/etc/passwd}", "\\input /etc/passwd", "\\include{../../secreto}", "\\openin5=/home/u/.ssh/id_rsa",
        "\\InputIfFileExists{~/x}{}{}", "\\includegraphics[width=1cm]{C:/x.png}", "\\input{a/../../b}",
    ])
    def test_lint_rejects_absolute_or_parent_paths(self, home, monkeypatch, src):
        monkeypatch.setattr(templates_registry, "engine_available", lambda *a, **k: "tectonic")
        with pytest.raises(templates_registry.TemplateError, match="fuera de su carpeta"):
            templates_registry.register_template("lint", "cv", {"c.tex.j2": src.encode()})

    def test_lint_checks_support_files_and_allows_relative(self, home, monkeypatch):
        monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
        with pytest.raises(templates_registry.TemplateError, match="fuera de su carpeta"):
            templates_registry.register_template("lint", "cv", {"c.tex.j2": b"x", "mi.sty": b"\\input{/etc/hostname}"})
        templates_registry.register_template("ok", "cv", {"c.tex.j2": b"\\input{secciones/a}", "secciones/a.tex": b"y"})


def test_assets_are_refreshed_when_the_template_changes(home, monkeypatch, tmp_path):
    """Revisión SP3 M7: volver a preparar tras actualizar la plantilla copia los ficheros de apoyo nuevos."""
    monkeypatch.setattr(templates_registry, "_test_compile", lambda *a, **k: None)
    templates_registry.register_template("conclase", "letter", {"c.tex.j2": b"x", "mi.cls": b"v1", "latexmkrc": b"y"})
    templates_registry.activate_template("letter", "conclase")
    out = tmp_path / "out"
    out.mkdir()
    templates_registry.copy_assets("letter", out)
    templates_registry.register_template("conclase", "letter", {"c.tex.j2": b"x", "mi.cls": b"v2"})
    templates_registry.copy_assets("letter", out)
    assert (out / "mi.cls").read_bytes() == b"v2"
    assert not (out / "latexmkrc").exists()
