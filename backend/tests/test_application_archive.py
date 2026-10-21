"""
test_application_archive.py — Pruebas para el archivo por candidatura
en JH_HOME/applications/<id>/ y resolución de adjuntos de email.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from automation.application_archive import (  # noqa: E402
    archive_application,
    get_application_attachments,
    get_application_dir,
    load_application_archive,
    save_interview_prep,
)


class TestApplicationArchive(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_apps_dir = Path(self.temp_dir.name) / "applications"
        self.fake_apps_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_application_dir(self):
        with patch("automation.application_archive.APPLICATIONS_DIR", self.fake_apps_dir):
            app_dir = get_application_dir("app_123")
            self.assertEqual(app_dir, self.fake_apps_dir / "app_123")

    def test_archive_application_creates_files_and_metadata(self):
        with patch("automation.application_archive.APPLICATIONS_DIR", self.fake_apps_dir):
            # Crear ficheros de muestra
            cv_file = Path(self.temp_dir.name) / "sample_cv.pdf"
            cv_file.write_bytes(b"%PDF-1.5 sample cv")
            cover_file = Path(self.temp_dir.name) / "sample_cover.pdf"
            cover_file.write_bytes(b"%PDF-1.5 sample cover")

            posting_dict = {
                "title": "Backend Senior",
                "company": "Acme Corp",
                "location": "Remoto",
                "description": "Buscamos desarrollador Python.",
            }

            app_dir = archive_application(
                application_id="42",
                cv_pdf=cv_file,
                cover_pdf=cover_file,
                job_posting=posting_dict,
                metadata={"offer_id": 101, "track": "ia"},
            )

            self.assertTrue((app_dir / "cv.pdf").is_file())
            self.assertTrue((app_dir / "cover.pdf").is_file())
            self.assertTrue((app_dir / "job_posting.md").is_file())
            self.assertTrue((app_dir / "metadata.json").is_file())

            # Verificar contenido de job_posting.md
            posting_md = (app_dir / "job_posting.md").read_text(encoding="utf-8")
            self.assertIn("Backend Senior", posting_md)
            self.assertIn("Acme Corp", posting_md)

            # Verificar metadata.json
            meta = json.loads((app_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["application_id"], "42")
            self.assertEqual(meta["offer_id"], 101)
            self.assertIn("cv.pdf", meta["files"])

    def test_get_application_attachments(self):
        with patch("automation.application_archive.APPLICATIONS_DIR", self.fake_apps_dir):
            # 1. Candidatura vacía
            cv, cover = get_application_attachments("99")
            self.assertIsNone(cv)
            self.assertIsNone(cover)

            # 2. Con CV pero sin cover
            app_dir = self.fake_apps_dir / "99"
            app_dir.mkdir(parents=True)
            (app_dir / "cv.pdf").write_bytes(b"cv")
            cv, cover = get_application_attachments("99")
            self.assertIsNotNone(cv)
            self.assertIsNone(cover)

            # 3. Con ambos
            (app_dir / "cover.pdf").write_bytes(b"cover")
            cv, cover = get_application_attachments("99")
            self.assertEqual(cv, app_dir / "cv.pdf")
            self.assertEqual(cover, app_dir / "cover.pdf")

    def test_save_interview_prep(self):
        with patch("automation.application_archive.APPLICATIONS_DIR", self.fake_apps_dir):
            app_dir = self.fake_apps_dir / "50"
            app_dir.mkdir(parents=True)
            (app_dir / "metadata.json").write_text('{"application_id": "50"}', encoding="utf-8")

            prep_path = save_interview_prep("50", "# Prep inicial", stage="technical")
            self.assertTrue(prep_path.is_file())
            self.assertEqual(prep_path.name, "interview_prep_technical.md")

            # Verifica actualización de metadata
            meta = json.loads((app_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("technical", meta.get("interview_preps", {}))

    def test_application_engine_uses_archived_attachments(self):
        from automation import application_engine

        with patch("automation.application_archive.APPLICATIONS_DIR", self.fake_apps_dir):
            app_dir = self.fake_apps_dir / "app_1"
            app_dir.mkdir(parents=True)
            archived_cv = app_dir / "cv.pdf"
            archived_cv.write_bytes(b"%PDF cv archived")
            archived_cover = app_dir / "cover.pdf"
            archived_cover.write_bytes(b"%PDF cover archived")

            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = {
                "id": "app_1",
                "status": "pending_approval",
                "contact_value": "hr@acme.com",
                "job_title": "Python Dev",
                "company_name": "Acme",
                "cv_profile": "general",
                "track_tag": "general",
                "cover_letter_edited": "Carta de prueba",
            }

            with patch("automation.application_engine._emails_sent_today", return_value=0), \
                 patch("automation.application_engine.send_email", return_value=(True, "msg_123")) as mock_send, \
                 patch("automation.application_engine._load_profile", return_value={"personal": {"name": "Test"}}):

                success = application_engine._send_approved(mock_conn, "app_1")
                self.assertTrue(success)

                # Verificar que los adjuntos pasados a send_email corresponden a los del archivo
                call_kwargs = mock_send.call_args[1]
                self.assertEqual(call_kwargs["cv_path"], str(archived_cv))
                self.assertEqual(call_kwargs["cover_letter_path"], str(archived_cover))


if __name__ == "__main__":
    unittest.main()
