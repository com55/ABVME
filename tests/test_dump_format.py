import unittest

from models.asset_model import format_object_dump


class FormatObjectDumpTests(unittest.TestCase):
    def test_caps_long_sequences(self) -> None:
        payload = {"curve": list(range(200))}
        text = format_object_dump(payload)
        self.assertIn("<+120 more>", text)
        self.assertNotIn("199", text)

    def test_truncates_total_length(self) -> None:
        payload = {f"block{i}": "x" * 50_000 for i in range(20)}
        text = format_object_dump(payload, max_chars=1000)
        self.assertLessEqual(len(text), 1020)
        self.assertTrue(text.endswith("<truncated>") or "<truncated>" in text)


if __name__ == "__main__":
    unittest.main()
