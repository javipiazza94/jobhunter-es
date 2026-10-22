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

    def test_compile_cmd_only_known_compilers(self, home):
        with pytest.raises(templates_registry.TemplateError, match="compilador conocido"):
            templates_registry.register_template("ok", "cv", {"a.tex.j2": b"x"}, compile_cmd="rm -rf /")
        with pytest.raises(templates_registry.TemplateError, match="compilador conocido"):
            templates_registry.register_template("ok", "cv", {"a.tex.j2": b"x"}, compile_cmd="/bin/typst compile")

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
