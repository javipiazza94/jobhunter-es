"""Tests de lectura de CV (PDF/DOCX) con datos inventados generados en el momento."""
import pytest
from docx import Document
from pypdf import PdfWriter

from automation.cv_reader import CVReadError, extract_text


def make_pdf(path, lines):
    """PDF mínimo válido de una página con un objeto de texto por línea."""
    ops = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({ln}) Tj T*" for ln in lines) + " ET"
    stream = ops.encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


def test_extracts_pdf_text(tmp_path):
    pdf = tmp_path / "cv.pdf"
    make_pdf(pdf, ["Ada Villanova", "Acme Robotics"])
    text = extract_text(pdf)
    assert "Ada Villanova" in text and "Acme Robotics" in text


def test_extracts_docx_paragraphs_and_tables(tmp_path):
    doc = Document()
    doc.add_paragraph("Ada Villanova")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Acme Robotics"
    table.rows[0].cells[1].text = "Ingeniera"
    path = tmp_path / "cv.docx"
    doc.save(path)
    text = extract_text(path)
    assert "Ada Villanova" in text and "Acme Robotics" in text and "Ingeniera" in text


def test_unsupported_extension(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text("hola")
    with pytest.raises(CVReadError, match="no soportado"):
        extract_text(path)


def test_missing_file(tmp_path):
    with pytest.raises(CVReadError):
        extract_text(tmp_path / "nope.pdf")


def test_empty_docx(tmp_path):
    path = tmp_path / "vacio.docx"
    Document().save(path)
    with pytest.raises(CVReadError, match="vac"):
        extract_text(path)


def test_corrupt_docx(tmp_path):
    path = tmp_path / "roto.docx"
    path.write_bytes(b"no es un zip")
    with pytest.raises(CVReadError):
        extract_text(path)


def test_corrupt_pdf(tmp_path):
    path = tmp_path / "roto.pdf"
    path.write_bytes(b"%PDF-1.4 basura")
    with pytest.raises(CVReadError):
        extract_text(path)


def test_empty_pdf_without_text(tmp_path, monkeypatch):
    path = tmp_path / "blanco.pdf"
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    with path.open("wb") as fh:
        writer.write(fh)
    # pdftotext simulado sin texto: el PDF de solo imagen debe dar CVReadError.
    monkeypatch.setattr("automation.verify_pdf.run_tool", lambda cmd: "Pages: 1\n" if cmd[0] == "pdfinfo" else "")
    with pytest.raises(CVReadError, match="vac"):
        extract_text(path)


def test_encrypted_pdf(tmp_path):
    path = tmp_path / "cifrado.pdf"
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt("secreto", algorithm="RC4-128")
    with path.open("wb") as fh:
        writer.write(fh)
    with pytest.raises(CVReadError, match="cifrado"):
        extract_text(path)


def test_file_too_large(tmp_path, monkeypatch):
    path = tmp_path / "grande.docx"
    path.write_bytes(b"x" * 100)
    monkeypatch.setattr("automation.cv_reader.MAX_FILE_BYTES", 50)
    with pytest.raises(CVReadError, match="10 MB"):
        extract_text(path)


def test_pdf_page_cap(tmp_path, monkeypatch):
    path = tmp_path / "largo.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(200, 200)
    with path.open("wb") as fh:
        writer.write(fh)
    seen = {}

    def fake(p, max_pages=None):
        seen["max"] = max_pages
        return "texto", 3, "pypdf"

    monkeypatch.setattr("automation.cv_reader.extract_text_layer", fake)
    assert extract_text(path) == "texto"
    assert seen["max"] == 30


def test_pypdf_respects_max_pages(tmp_path):
    from automation.verify_pdf import _extract_pypdf

    path = tmp_path / "cv.pdf"
    make_pdf(path, ["Ada Villanova"])
    text, pages = _extract_pypdf(path, max_pages=1)
    assert pages == 1 and "Ada" in text


def test_docx_bomb(tmp_path, monkeypatch):
    path = tmp_path / "bomba.docx"
    Document().save(path)

    class Info:
        file_size = 60 * 1024 * 1024

    monkeypatch.setattr("zipfile.ZipFile.infolist", lambda self: [Info()])
    with pytest.raises(CVReadError, match="grande"):
        extract_text(path)


def test_text_truncated(tmp_path, monkeypatch):
    doc = Document()
    doc.add_paragraph("a" * 500)
    path = tmp_path / "cv.docx"
    doc.save(path)
    monkeypatch.setattr("automation.cv_reader.MAX_TEXT_CHARS", 100)
    assert len(extract_text(path)) == 100


def test_owner_password_only_pdf_is_readable(tmp_path):
    plain = tmp_path / "plano.pdf"
    make_pdf(plain, ["Ada Villanova"])
    from pypdf import PdfReader

    writer = PdfWriter(clone_from=PdfReader(str(plain)))
    writer.encrypt(user_password="", owner_password="x", algorithm="RC4-128")
    path = tmp_path / "owner.pdf"
    with path.open("wb") as fh:
        writer.write(fh)
    assert "Ada Villanova" in extract_text(path)


def test_docx_header_footer(tmp_path):
    doc = Document()
    doc.add_paragraph("Cuerpo")
    doc.sections[0].header.paragraphs[0].text = "Ada Villanova"
    doc.sections[0].footer.paragraphs[0].text = "Pie Villanova"
    path = tmp_path / "cv.docx"
    doc.save(path)
    text = extract_text(path)
    assert "Ada Villanova" in text and "Pie Villanova" in text


def test_pdftotext_timeout(monkeypatch):
    import subprocess

    from automation.verify_pdf import VerificationError, run_tool

    def boom(*a, **k):
        assert k["timeout"] == 20
        raise subprocess.TimeoutExpired("pdftotext", 20)

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(VerificationError):
        run_tool(["pdftotext", "x"])
