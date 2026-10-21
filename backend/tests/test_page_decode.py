"""Tests portados de MadsLorentzen/ai-job-search @ e16acee (tests/test_page_decode.py, MIT,
Copyright (c) 2026 Mads Lorentzen).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from automation.page_decode import decode_page, declared_codec  # noqa: E402


def page(body: str, head: str = "") -> str:
    return f"<!doctype html><html><head>{head}<title>Posting</title></head><body>{body}</body></html>"


class LegacyCharsets(unittest.TestCase):
    def test_http_equiv_euc_kr_is_read_as_cp949(self):
        # 똠 is outside strict EUC-KR; browsers read the euc-kr label as CP949.
        text = page("<h1>백엔드 개발자 채용</h1><p>똠방각하 우대</p>",
                    '<meta http-equiv="Content-Type" content="text/html; charset=euc-kr">')
        decoded = decode_page(text.encode("cp949"))
        self.assertIn("백엔드 개발자 채용", decoded)
        self.assertIn("똠방각하", decoded)
        self.assertNotIn("\ufffd", decoded)

    def test_meta_charset_shift_jis(self):
        text = page("<h1>データエンジニア募集</h1>", '<meta charset="Shift_JIS">')
        self.assertIn("データエンジニア募集", decode_page(text.encode("cp932")))

    def test_iso_8859_1_label_is_read_as_windows_1252(self):
        text = page("<p>Løn: 50.000 € om måneden</p>", "<meta charset=iso-8859-1>")
        self.assertIn("Løn: 50.000 € om måneden", decode_page(text.encode("cp1252")))

    def test_windows_1251_cyrillic(self):
        text = page("<p>Инженер данных</p>", '<meta charset="windows-1251">')
        self.assertIn("Инженер данных", decode_page(text.encode("cp1251")))

    def test_utf16_byte_order_mark(self):
        text = page("<p>Ingeniør</p>")
        self.assertIn("Ingeniør", decode_page(text.encode("utf-16")))


class UnchangedBehaviour(unittest.TestCase):
    def test_valid_utf8_is_unchanged(self):
        raw = page("<p>Ingeniør søges, 백엔드, データ</p>").encode("utf-8")
        self.assertEqual(decode_page(raw), raw.decode("utf-8", errors="replace"))

    def test_valid_utf8_wins_over_a_wrong_meta_label(self):
        # Browsers would follow a utf-8 HTTP header here; the saved file does not
        # keep headers, so valid UTF-8 has to win over a stale <meta>.
        raw = page("<p>Café</p>", '<meta charset="iso-8859-1">').encode("utf-8")
        self.assertIn("Café", decode_page(raw))

    def test_utf8_bom_is_kept_for_the_invisible_character_count(self):
        raw = b"\xef\xbb\xbf" + page("<p>Plain posting.</p>").encode("utf-8")
        self.assertTrue(decode_page(raw).startswith("﻿"))

    def test_undeclared_legacy_bytes_fall_back_to_utf8_with_replacement(self):
        raw = page("<p>Café</p>").encode("latin-1")
        self.assertEqual(decode_page(raw), raw.decode("utf-8", errors="replace"))

    def test_unknown_and_unsafe_labels_are_ignored(self):
        for label in ("x-unknown", "utf-7", "utf-16"):
            raw = page("<p>Café</p>", f'<meta charset="{label}">').encode("latin-1")
            with self.subTest(label=label):
                self.assertIsNone(declared_codec(raw))
                self.assertEqual(decode_page(raw), raw.decode("utf-8", errors="replace"))

    def test_meta_after_the_prescan_window_is_ignored(self):
        raw = (" " * 1100 + page("<p>Café</p>", '<meta charset="windows-1252">')).encode("cp1252")
        self.assertIsNone(declared_codec(raw))


if __name__ == "__main__":
    unittest.main()
