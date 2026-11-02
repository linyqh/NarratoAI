import codecs
import tempfile
import unittest
from pathlib import Path

from app.services.subtitle_text import (
    decode_subtitle_bytes,
    normalize_subtitle_text,
    read_subtitle_text,
)


class SubtitleTextTests(unittest.TestCase):
    source = "1\n00:00:01,000 --> 00:00:02,000\n你好\n"

    def test_bomless_utf16_preserves_chinese(self):
        for encoding in ("utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                result = decode_subtitle_bytes(self.source.encode(encoding))
                self.assertEqual(result.text, self.source.strip())
                self.assertIn(result.encoding, ("utf-16", encoding))

    def test_bomless_utf16_preserves_ascii_subtitles(self):
        source = self.source.replace("你好", "Hello")
        for encoding in ("utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                result = decode_subtitle_bytes(source.encode(encoding))
                self.assertEqual(result.text, source.strip())
                self.assertIn(result.encoding, ("utf-16", encoding))

    def test_existing_encodings_preserve_chinese(self):
        cases = {
            "utf-8": self.source.encode("utf-8"),
            "utf-8-sig": self.source.encode("utf-8-sig"),
            "utf-16-le-bom": codecs.BOM_UTF16_LE + self.source.encode("utf-16-le"),
            "utf-16-be-bom": codecs.BOM_UTF16_BE + self.source.encode("utf-16-be"),
            "gbk": self.source.encode("gbk"),
        }
        for name, data in cases.items():
            with self.subTest(encoding=name):
                self.assertEqual(decode_subtitle_bytes(data).text, self.source.strip())

    def test_utf16_keeps_newline_and_millisecond_normalization(self):
        source = self.source.replace(",000", ".000").replace("\n", "\r\n")
        for encoding in ("utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                self.assertEqual(
                    decode_subtitle_bytes(source.encode(encoding)).text,
                    self.source.strip(),
                )

    def test_explicit_encoding_order_is_preserved(self):
        data = self.source.encode("utf-16-be")
        result = decode_subtitle_bytes(data, encodings=("utf-8", "utf-16-be"))
        self.assertEqual(result.encoding, "utf-8")
        self.assertEqual(result.text, normalize_subtitle_text(data.decode("utf-8")))
        self.assertEqual(
            decode_subtitle_bytes(data, encodings=("utf-16-be",)).text,
            self.source.strip(),
        )

    def test_non_srt_utf8_keeps_first_successful_fallback(self):
        result = decode_subtitle_bytes("普通文字".encode())
        self.assertEqual((result.text, result.encoding), ("普通文字", "utf-8"))

    def test_nul_cleanup_is_still_available(self):
        source = self.source.replace("00:00:01,000", "00:\x0000:01,000")
        self.assertEqual(
            decode_subtitle_bytes(source.encode("utf-8")).text,
            self.source.strip(),
        )

    def test_empty_and_none_inputs(self):
        for data in (None, b""):
            with self.subTest(data=data):
                result = decode_subtitle_bytes(data)
                self.assertEqual((result.text, result.encoding), ("", "utf-8"))

    def test_disk_read_preserves_bomless_utf16(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subtitles.srt"
            path.write_bytes(self.source.encode("utf-16-be"))
            self.assertEqual(read_subtitle_text(str(path)).text, self.source.strip())


if __name__ == "__main__":
    unittest.main()
