import unittest

from models.asset_model import EMPTY_CELL_TEXT, format_byte_size


class FormatByteSizeTests(unittest.TestCase):
    def test_examples_from_spec(self) -> None:
        self.assertEqual(format_byte_size(0), "0 B")
        self.assertEqual(format_byte_size(1023), "1023 B")
        self.assertEqual(format_byte_size(1024), "1.0 KB")
        self.assertEqual(format_byte_size(1536), "1.5 KB")
        self.assertEqual(format_byte_size(1048576), "1.0 MB")
        self.assertEqual(format_byte_size(1048575), "1.0 MB")

    def test_negative_stays_bytes(self) -> None:
        self.assertEqual(format_byte_size(-1), "-1 B")

    def test_empty_cell_text(self) -> None:
        self.assertEqual(EMPTY_CELL_TEXT, "(none)")


if __name__ == "__main__":
    unittest.main()
