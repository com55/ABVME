import unittest
from types import SimpleNamespace

from models.packers import (
    BLOCKS_INFO_AT_THE_END,
    data_flag_has_blocks_info_at_end,
    resolve_packer,
)


class ResolvePackerTests(unittest.TestCase):
    def test_lz4_tuple_is_data_flag_then_block_info(self) -> None:
        self.assertEqual(resolve_packer("lz4"), (0x42, 2))
        self.assertEqual(resolve_packer("lz4hc"), (0x243, 3))
        self.assertEqual(resolve_packer("none"), "none")
        self.assertEqual(resolve_packer("lzma"), "lzma")
        self.assertEqual(resolve_packer("original"), "original")
        self.assertFalse(resolve_packer("lz4")[0] & BLOCKS_INFO_AT_THE_END)
        self.assertFalse(resolve_packer("lz4hc")[0] & BLOCKS_INFO_AT_THE_END)

    def test_unknown_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_packer("lz4_string_preset")

    def test_original_reads_file_dataflags(self) -> None:
        obj = SimpleNamespace(dataflags=0xC2)
        self.assertTrue(data_flag_has_blocks_info_at_end(obj, "original"))
        self.assertFalse(data_flag_has_blocks_info_at_end(obj, (0x42, 2)))
