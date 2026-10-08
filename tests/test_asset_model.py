import unittest

from types import SimpleNamespace

from models.asset_model import EMPTY_CELL_TEXT, AssetInfo, format_byte_size, streamed_size


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


class StreamedSizeTests(unittest.TestCase):
    def test_texture_and_mesh_stream_data(self) -> None:
        data = SimpleNamespace(m_StreamData=SimpleNamespace(offset=0, size=1998848, path="archive:/CAB-1/CAB-1.resS"))
        self.assertEqual(streamed_size(data), 1998848)

    def test_audio_and_video_resources(self) -> None:
        audio = SimpleNamespace(m_Resource=SimpleNamespace(m_Offset=0, m_Size=4096, m_Source="archive:/CAB-1/CAB-1.resource"))
        video = SimpleNamespace(m_ExternalResources=SimpleNamespace(m_Offset=0, m_Size=777, m_Source="archive:/CAB-1/CAB-1.resource"))
        self.assertEqual(streamed_size(audio), 4096)
        self.assertEqual(streamed_size(video), 777)

    def test_inline_data_has_no_stream_size(self) -> None:
        inline = SimpleNamespace(m_StreamData=SimpleNamespace(offset=0, size=0, path=""))
        self.assertEqual(streamed_size(inline), 0)
        self.assertEqual(streamed_size(SimpleNamespace()), 0)


class _FakeReader:
    """Just enough of UnityPy's ObjectReader for AssetInfo."""

    def __init__(self, type_name: str, byte_size: int, data: object) -> None:
        self.type = SimpleNamespace(name=type_name)
        self.byte_size = byte_size
        self.container = ""
        self.path_id = 1
        self.reads = 0
        self._data = data

    def peek_name(self) -> str:
        return "asset"

    def read(self) -> object:
        self.reads += 1
        return self._data


class AssetTotalSizeTests(unittest.TestCase):
    def test_total_size_adds_streamed_data_once_without_keeping_it(self) -> None:
        data = SimpleNamespace(m_StreamData=SimpleNamespace(offset=0, size=5000, path="archive:/CAB-1/CAB-1.resS"))
        reader = _FakeReader("Texture2D", 192, data)
        asset = AssetInfo(reader)
        self.assertEqual(asset.total_size, 5192)
        self.assertEqual(asset.total_size, 5192)
        self.assertEqual(reader.reads, 1)
        self.assertIsNone(asset._readed_data)

    def test_other_types_are_not_read(self) -> None:
        reader = _FakeReader("MonoBehaviour", 300, None)
        asset = AssetInfo(reader)
        self.assertEqual(asset.total_size, 300)
        self.assertEqual(reader.reads, 0)


if __name__ == "__main__":
    unittest.main()
