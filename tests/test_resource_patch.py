import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image as PILImage
from UnityPy.enums import ClassIDType
from UnityPy.streams.EndianBinaryReader import EndianBinaryReader

from models.asset_model import AssetInfo, ResultStatus
from models.core_model import ABVMECore
from models.save_options import ResourcePatchMode, StreamCapture


class _Bundle:
    """Hashable stand-in for BundleFile (SimpleNamespace is not)."""

    def __init__(self, files: dict | None = None) -> None:
        self.files = files if files is not None else {}
        self.save = MagicMock(return_value=b"SAVED")


def _image(size: tuple[int, int] = (8, 8)) -> PILImage.Image:
    return PILImage.new("RGBA", size, (255, 0, 0, 255))


def _ress_reader(
    payload: bytes, *, flags: int = 1, endian: str = "<"
) -> EndianBinaryReader:
    reader = EndianBinaryReader(payload, endian=endian)
    reader.flags = flags
    return reader


def _ress_bytes(reader) -> bytes:
    view = getattr(reader, "view", None)
    if view is not None:
        return bytes(view)
    reader.Position = 0
    return reader.read_bytes(reader.Length)


class _AssetsFile:
    def __init__(self, parent) -> None:
        self.parent = parent


def _texture_reader(*, path_id: int, parent, state: dict):
    """ObjectReader stand-in: each read() returns a new MagicMock Texture2D."""
    obj = MagicMock()
    obj.path_id = path_id
    obj.type = ClassIDType.Texture2D
    obj.assets_file = _AssetsFile(parent)
    obj.peek_name.return_value = f"tex{path_id}"
    obj.container = ""

    def read(_check: bool = True):
        tex = MagicMock()
        tex.m_StreamData = SimpleNamespace(
            path=state["path"],
            offset=state["offset"],
            size=state["size"],
        )
        tex.image_data = state["image_data"]
        tex.m_Width = state.get("width", 8)
        tex.m_Height = state.get("height", 8)
        tex.m_TextureFormat = state.get("format", 4)

        def set_image(img) -> None:
            width, height = img.size
            tex.image_data = state.get("inlined_bytes", b"INLINED-IMG")
            tex.m_Width = width
            tex.m_Height = height
            tex.m_StreamData.path = ""
            tex.m_StreamData.offset = 0
            tex.m_StreamData.size = 0

        def save() -> None:
            state["path"] = tex.m_StreamData.path
            state["offset"] = int(tex.m_StreamData.offset)
            state["size"] = int(tex.m_StreamData.size)
            state["image_data"] = tex.image_data
            state["width"] = tex.m_Width
            state["height"] = tex.m_Height
            state["format"] = int(tex.m_TextureFormat)

        tex.set_image.side_effect = set_image
        tex.save.side_effect = save
        return tex

    obj.read.side_effect = read
    return obj


def _unitypy_texture_reader(*, path_id: int, parent, disk: dict, inlined_bytes: bytes):
    """ObjectReader stand-in matching UnityPy 1.23: read() always parses disk bytes.

    set_image mutates the returned instance only. save() does not change the next
    read() (ObjectReader.data is separate from reader.byte_start).
    """
    obj = MagicMock()
    obj.path_id = path_id
    obj.type = ClassIDType.Texture2D
    obj.assets_file = _AssetsFile(parent)
    obj.peek_name.return_value = f"tex{path_id}"
    obj.container = ""

    def read(_check: bool = True):
        stream = SimpleNamespace(
            path=disk["path"],
            offset=disk["offset"],
            size=disk["size"],
        )
        tex = MagicMock()
        tex.m_StreamData = stream
        tex.image_data = disk["image_data"]
        tex.m_Width = disk.get("width", 8)
        tex.m_Height = disk.get("height", 8)
        tex.m_TextureFormat = disk.get("format", 4)

        def set_image(img) -> None:
            width, height = img.size
            tex.image_data = inlined_bytes
            tex.m_Width = width
            tex.m_Height = height
            stream.path = ""
            stream.offset = 0
            stream.size = 0

        def save() -> None:
            return None

        tex.set_image.side_effect = set_image
        tex.save.side_effect = save
        return tex

    obj.read.side_effect = read
    return obj


def _bundle_env(file_obj, objects: list, source_path: str = "bundle-a"):
    env = SimpleNamespace(
        files={source_path: file_obj},
        objects=objects,
        register_cab=MagicMock(),
    )
    return env


class ApplyResourcePatchTests(unittest.TestCase):
    def test_resource_patch_rebuilds_patched_and_copies_sibling(self) -> None:
        from models.resource_patch import apply_resource_patch

        original = b"SIB1PATCHD"
        ress_name = "CAB-x.resS"
        reader = _ress_reader(original, flags=7, endian="<")
        file_obj = _Bundle({ress_name: reader})
        patched_state = {
            "path": "",
            "offset": 0,
            "size": 0,
            "image_data": b"NEWIMG!!",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        sibling_state = {
            "path": ress_name,
            "offset": 0,
            "size": 4,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        patched = _texture_reader(path_id=11, parent=file_obj, state=patched_state)
        sibling = _texture_reader(path_id=22, parent=file_obj, state=sibling_state)
        other_parent = SimpleNamespace(files={})
        other_state = dict(patched_state)
        other = _texture_reader(path_id=11, parent=other_parent, state=other_state)
        env = _bundle_env(file_obj, [patched, sibling, other])
        captures = {
            ("bundle-a", 11): StreamCapture(path=ress_name, offset=4, size=6),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )

        self.assertEqual(warnings, [])
        rebuilt = file_obj.files[ress_name]
        self.assertIsInstance(rebuilt, EndianBinaryReader)
        self.assertIsNot(rebuilt, reader)
        self.assertEqual(_ress_bytes(rebuilt), b"SIB1NEWIMG!!")
        self.assertEqual(getattr(rebuilt, "flags", None), 7)
        self.assertEqual(rebuilt.endian, "<")
        self.assertEqual(sibling_state["offset"], 0)
        self.assertEqual(sibling_state["size"], 4)
        self.assertEqual(sibling_state["path"], ress_name)
        self.assertEqual(sibling_state["image_data"], b"")
        self.assertEqual(patched_state["offset"], 4)
        self.assertEqual(patched_state["size"], 8)
        self.assertEqual(patched_state["path"], ress_name)
        self.assertEqual(patched_state["image_data"], b"")
        self.assertEqual(other_state["image_data"], b"NEWIMG!!")
        env.register_cab.assert_called()
        cab_names = [call.args[0] for call in env.register_cab.call_args_list]
        self.assertTrue(
            any(
                name.lower().endswith("cab-x.ress") or name == ress_name
                for name in cab_names
            )
        )

    def test_archive_stream_path_matches_bare_directory_key(self) -> None:
        from models.resource_patch import apply_resource_patch

        original = b"AAAA"
        reader = _ress_reader(original)
        file_obj = _Bundle({"CAB-x.resS": reader})
        patched_state = {
            "path": "",
            "offset": 0,
            "size": 0,
            "image_data": b"BBBB",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        patched = _texture_reader(path_id=1, parent=file_obj, state=patched_state)
        env = _bundle_env(file_obj, [patched])
        captures = {
            ("bundle-a", 1): StreamCapture(
                path="archive:/CAB-x.resS", offset=0, size=4
            ),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(_ress_bytes(file_obj.files["CAB-x.resS"]), b"BBBB")
        self.assertEqual(patched_state["path"], "archive:/CAB-x.resS")
        self.assertEqual(patched_state["offset"], 0)
        self.assertEqual(patched_state["size"], 4)

    def test_missing_reader_inlines_and_warns(self) -> None:
        from models.resource_patch import apply_resource_patch

        file_obj = _Bundle()
        patched_state = {
            "path": "",
            "offset": 0,
            "size": 0,
            "image_data": b"KEEP-ME",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        patched = _texture_reader(path_id=3, parent=file_obj, state=patched_state)
        env = _bundle_env(file_obj, [patched])
        captures = {
            ("bundle-a", 3): StreamCapture(path="CAB-missing.resS", offset=0, size=4),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )

        self.assertTrue(warnings)
        self.assertEqual(patched_state["path"], "")
        self.assertEqual(patched_state["offset"], 0)
        self.assertEqual(patched_state["size"], 0)
        self.assertEqual(patched_state["image_data"], b"KEEP-ME")

    def test_orphan_cleanup_keeps_non_texture_ress(self) -> None:
        from models.resource_patch import apply_resource_patch

        tex_reader = _ress_reader(b"TEX!")
        audio_reader = _ress_reader(b"AUD!")
        mesh_reader = _ress_reader(b"MSH!")
        file_obj = _Bundle(
            {
                "CAB-tex.resS": tex_reader,
                "CAB-audio.resS": audio_reader,
                "CAB-mesh.resS": mesh_reader,
            }
        )
        tex_state = {
            "path": "",
            "offset": 0,
            "size": 0,
            "image_data": b"INLINED",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        texture = _texture_reader(path_id=5, parent=file_obj, state=tex_state)

        audio = MagicMock()
        audio.path_id = 6
        audio.type = ClassIDType.AudioClip
        audio.assets_file = SimpleNamespace(parent=file_obj)
        audio.read.return_value = SimpleNamespace(
            m_Resource=SimpleNamespace(m_Source="CAB-audio.resS"),
            m_StreamData=None,
        )

        mesh = MagicMock()
        mesh.path_id = 7
        mesh.type = ClassIDType.Mesh
        mesh.assets_file = SimpleNamespace(parent=file_obj)
        mesh.read.return_value = SimpleNamespace(
            m_StreamData=SimpleNamespace(path="CAB-mesh.resS", offset=0, size=4),
            m_Resource=None,
        )

        env = _bundle_env(file_obj, [texture, audio, mesh])
        captures = {
            ("bundle-a", 5): StreamCapture(path="CAB-tex.resS", offset=0, size=4),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.ORPHAN_CLEANUP,
            env=env,
        )

        self.assertEqual(warnings, [])
        self.assertNotIn("CAB-tex.resS", file_obj.files)
        self.assertIn("CAB-audio.resS", file_obj.files)
        self.assertIn("CAB-mesh.resS", file_obj.files)
        self.assertIs(file_obj.files["CAB-audio.resS"], audio_reader)
        self.assertIs(file_obj.files["CAB-mesh.resS"], mesh_reader)

    def test_bc_dxt_2x2_patched_inlines_unpatched_sibling_stays(self) -> None:
        from models.resource_patch import apply_resource_patch

        original = b"SIB1BAD!"
        ress_name = "CAB-x.resS"
        reader = _ress_reader(original)
        file_obj = _Bundle({ress_name: reader})
        patched_state = {
            "path": "",
            "offset": 0,
            "size": 0,
            "image_data": b"TINY",
            "width": 2,
            "height": 2,
            "format": 10,
        }
        sibling_state = {
            "path": ress_name,
            "offset": 0,
            "size": 4,
            "image_data": b"",
            "width": 2,
            "height": 2,
            "format": 10,
        }
        patched = _texture_reader(path_id=1, parent=file_obj, state=patched_state)
        sibling = _texture_reader(path_id=2, parent=file_obj, state=sibling_state)
        env = _bundle_env(file_obj, [patched, sibling])
        captures = {
            ("bundle-a", 1): StreamCapture(path=ress_name, offset=4, size=4),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )

        self.assertTrue(any("inline" in w.lower() or "4" in w for w in warnings))
        self.assertEqual(patched_state["path"], "")
        self.assertEqual(patched_state["image_data"], b"TINY")
        self.assertEqual(sibling_state["path"], ress_name)
        self.assertNotEqual(sibling_state["path"], "")
        self.assertEqual(_ress_bytes(file_obj.files[ress_name])[:4], b"SIB1")

    def test_empty_patched_image_data_inlines_does_not_stream(self) -> None:
        from models.resource_patch import apply_resource_patch

        original = b"SIB1XXXX"
        ress_name = "CAB-x.resS"
        reader = _ress_reader(original)
        file_obj = _Bundle({ress_name: reader})
        patched_state = {
            "path": "",
            "offset": 0,
            "size": 0,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        sibling_state = {
            "path": ress_name,
            "offset": 0,
            "size": 4,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        patched = _texture_reader(path_id=11, parent=file_obj, state=patched_state)
        sibling = _texture_reader(path_id=22, parent=file_obj, state=sibling_state)
        env = _bundle_env(file_obj, [patched, sibling])
        captures = {
            ("bundle-a", 11): StreamCapture(path=ress_name, offset=4, size=4),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )

        joined = " ".join(warnings).lower()
        self.assertIn("empty", joined)
        self.assertIn("skipping", joined)
        self.assertEqual(patched_state["path"], "")
        self.assertEqual(patched_state["offset"], 0)
        self.assertEqual(patched_state["size"], 0)
        self.assertEqual(sibling_state["path"], ress_name)
        self.assertEqual(sibling_state["offset"], 0)
        self.assertEqual(sibling_state["size"], 4)
        self.assertEqual(_ress_bytes(file_obj.files[ress_name]), b"SIB1")


class UnityPySecondReadTests(unittest.TestCase):
    def test_resource_patch_uses_replace_instance_not_second_read(self) -> None:
        """UnityPy read() after save() still returns original empty image_data."""
        original = b"SIB1PATCHD"
        ress_name = "CAB-x.resS"
        file_obj = _Bundle({ress_name: _ress_reader(original)})
        disk_patched = {
            "path": ress_name,
            "offset": 4,
            "size": 6,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        disk_sibling = {
            "path": ress_name,
            "offset": 0,
            "size": 4,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        patched = _unitypy_texture_reader(
            path_id=1,
            parent=file_obj,
            disk=disk_patched,
            inlined_bytes=b"NEWIMG!!",
        )
        sibling = _unitypy_texture_reader(
            path_id=2,
            parent=file_obj,
            disk=disk_sibling,
            inlined_bytes=b"",
        )
        env = _bundle_env(file_obj, [patched, sibling])
        core = ABVMECore()
        core._env = env
        asset = AssetInfo(
            patched,
            "bundle-a",
            register_stream_capture=core.register_stream_capture,
        )
        core._all_assets = [asset]
        self.assertTrue(asset.edit_data(_image()).is_success)

        with tempfile.TemporaryDirectory() as td:
            warnings = core._save_fileobj(
                file_obj,
                Path(td) / "out.bundle",
                "none",
                source_path="bundle-a",
                original_crc32=None,
                crc_mode="off",
                resource_patch_mode=ResourcePatchMode.RESOURCE_PATCH,
            )

        self.assertEqual(warnings, [])
        self.assertEqual(_ress_bytes(file_obj.files[ress_name]), b"SIB1NEWIMG!!")
        live = asset._readed_data
        self.assertEqual(live.m_StreamData.path, ress_name)
        self.assertEqual(live.m_StreamData.offset, 4)
        self.assertEqual(live.m_StreamData.size, 8)
        self.assertEqual(live.image_data, b"")


class StreamCaptureRegisterTests(unittest.TestCase):
    def test_register_uses_int_obj_path_id_not_assetinfo_str(self) -> None:
        core = ABVMECore()
        obj = MagicMock()
        obj.path_id = 42
        obj.type = ClassIDType.Texture2D
        obj.peek_name.return_value = "icon"
        obj.container = ""
        tex = MagicMock()
        tex.m_StreamData = SimpleNamespace(path="CAB-x.resS", offset=8, size=16)
        tex.image_data = b""
        tex.set_image = MagicMock()
        tex.save = MagicMock()
        obj.read.return_value = tex

        asset = AssetInfo(
            obj,
            "bundle-a",
            register_stream_capture=core.register_stream_capture,
        )
        self.assertEqual(asset.path_id, "42")
        asset.path_id = "not-the-id"

        result = asset.edit_data(_image())
        self.assertTrue(result.is_success)
        self.assertIn(("bundle-a", 42), core._stream_captures)
        self.assertNotIn(("bundle-a", "42"), core._stream_captures)
        self.assertNotIn(("bundle-a", "not-the-id"), core._stream_captures)
        capture = core._stream_captures[("bundle-a", 42)]
        self.assertEqual(capture.path, "CAB-x.resS")
        self.assertEqual(capture.offset, 8)
        self.assertEqual(capture.size, 16)
        tex.set_image.assert_called_once()
        tex.save.assert_called_once()

    def test_skip_register_when_source_path_empty(self) -> None:
        core = ABVMECore()
        obj = MagicMock()
        obj.path_id = 9
        obj.type = ClassIDType.Texture2D
        obj.peek_name.return_value = "icon"
        obj.container = ""
        tex = MagicMock()
        tex.m_StreamData = SimpleNamespace(path="CAB-x.resS", offset=1, size=2)
        tex.set_image = MagicMock()
        tex.save = MagicMock()
        obj.read.return_value = tex

        asset = AssetInfo(
            obj,
            "",
            register_stream_capture=core.register_stream_capture,
        )
        result = asset.edit_data(_image())
        self.assertTrue(result.is_success)
        self.assertEqual(core._stream_captures, {})

    def test_set_image_raises_does_not_register_capture(self) -> None:
        core = ABVMECore()
        obj = MagicMock()
        obj.path_id = 7
        obj.type = ClassIDType.Texture2D
        obj.peek_name.return_value = "icon"
        obj.container = ""
        tex = MagicMock()
        tex.m_StreamData = SimpleNamespace(path="CAB-x.resS", offset=4, size=8)
        tex.set_image.side_effect = RuntimeError("set_image failed")
        tex.save = MagicMock()
        obj.read.return_value = tex

        asset = AssetInfo(
            obj,
            "bundle-a",
            register_stream_capture=core.register_stream_capture,
        )
        result = asset.edit_data(_image())
        self.assertFalse(result.is_success)
        self.assertEqual(result.status, ResultStatus.ERROR)
        self.assertEqual(core._stream_captures, {})
        self.assertFalse(asset.is_changed)
        tex.save.assert_not_called()

    def test_save_raises_does_not_register_capture(self) -> None:
        core = ABVMECore()
        obj = MagicMock()
        obj.path_id = 7
        obj.type = ClassIDType.Texture2D
        obj.peek_name.return_value = "icon"
        obj.container = ""
        tex = MagicMock()
        tex.m_StreamData = SimpleNamespace(path="CAB-x.resS", offset=4, size=8)
        tex.set_image = MagicMock()
        tex.save.side_effect = RuntimeError("save failed")
        obj.read.return_value = tex

        asset = AssetInfo(
            obj,
            "bundle-a",
            register_stream_capture=core.register_stream_capture,
        )
        result = asset.edit_data(_image())
        self.assertFalse(result.is_success)
        self.assertEqual(result.status, ResultStatus.ERROR)
        self.assertEqual(core._stream_captures, {})
        self.assertFalse(asset.is_changed)


class EditDataCaptureTests(unittest.TestCase):
    def test_second_replace_before_save_keeps_first_capture_then_consume(self) -> None:
        core = ABVMECore()
        original = b"SIB1PATCHD"
        ress_name = "CAB-x.resS"
        reader = _ress_reader(original)
        file_obj = _Bundle({ress_name: reader})
        patched_state = {
            "path": ress_name,
            "offset": 4,
            "size": 6,
            "image_data": b"",
            "inlined_bytes": b"NEWIMG!!",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        sibling_state = {
            "path": ress_name,
            "offset": 0,
            "size": 4,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        patched = _texture_reader(path_id=1, parent=file_obj, state=patched_state)
        sibling = _texture_reader(path_id=2, parent=file_obj, state=sibling_state)
        env = _bundle_env(file_obj, [patched, sibling])
        core._env = env

        read_n = [0]
        orig_read = patched.read.side_effect

        def read_with_shifted_offset(_check: bool = True):
            read_n[0] += 1
            tex = orig_read()
            if read_n[0] >= 2 and tex.m_StreamData.path:
                tex.m_StreamData.offset = 999
            return tex

        patched.read.side_effect = read_with_shifted_offset

        asset = AssetInfo(
            patched,
            "bundle-a",
            register_stream_capture=core.register_stream_capture,
        )
        self.assertTrue(asset.edit_data(_image()).is_success)
        self.assertEqual(core._stream_captures[("bundle-a", 1)].offset, 4)

        self.assertTrue(asset.edit_data(_image()).is_success)
        self.assertEqual(core._stream_captures[("bundle-a", 1)].offset, 4)
        self.assertEqual(core._stream_captures[("bundle-a", 1)].size, 6)

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.bundle"
            warnings = core._save_fileobj(
                file_obj,
                out,
                "none",
                source_path="bundle-a",
                original_crc32=None,
                crc_mode="off",
                resource_patch_mode=ResourcePatchMode.RESOURCE_PATCH,
            )
            self.assertEqual(warnings, [])
            self.assertEqual(core._stream_captures, {})
            after_first = _ress_bytes(file_obj.files[ress_name])
            self.assertEqual(after_first, b"SIB1NEWIMG!!")

            patched_state["image_data"] = b""
            warnings2 = core._save_fileobj(
                file_obj,
                out,
                "none",
                source_path="bundle-a",
                original_crc32=None,
                crc_mode="off",
                resource_patch_mode=ResourcePatchMode.RESOURCE_PATCH,
            )
            self.assertEqual(warnings2, [])
            self.assertEqual(_ress_bytes(file_obj.files[ress_name]), after_first)

    def test_edit_data_after_resource_patch_sees_live_stream(self) -> None:
        core = ABVMECore()
        original = b"OLD!"
        ress_name = "CAB-x.resS"
        file_obj = _Bundle({ress_name: _ress_reader(original)})
        state = {
            "path": ress_name,
            "offset": 0,
            "size": 4,
            "image_data": b"",
            "inlined_bytes": b"LIVE",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        obj = _texture_reader(path_id=8, parent=file_obj, state=state)
        env = _bundle_env(file_obj, [obj])
        core._env = env

        asset = AssetInfo(
            obj,
            "bundle-a",
            register_stream_capture=core.register_stream_capture,
        )
        self.assertTrue(asset.edit_data(_image()).is_success)
        self.assertEqual(core._stream_captures[("bundle-a", 8)].offset, 0)
        self.assertEqual(state["path"], "")

        from models.resource_patch import apply_resource_patch

        apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=core._stream_captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )
        self.assertEqual(state["path"], ress_name)
        self.assertEqual(state["offset"], 0)
        self.assertEqual(state["size"], 4)
        self.assertEqual(state["image_data"], b"")

        core._stream_captures.clear()
        self.assertTrue(asset.edit_data(_image()).is_success)
        self.assertIn(("bundle-a", 8), core._stream_captures)
        self.assertEqual(core._stream_captures[("bundle-a", 8)].path, ress_name)
        self.assertEqual(core._stream_captures[("bundle-a", 8)].offset, 0)

    def test_get_available_assets_wires_register_callback(self) -> None:
        core = ABVMECore()
        file_obj = _Bundle()
        state = {
            "path": "CAB-x.resS",
            "offset": 2,
            "size": 3,
            "image_data": b"",
            "width": 8,
            "height": 8,
            "format": 4,
        }
        obj = _texture_reader(path_id=4, parent=file_obj, state=state)
        core._env = SimpleNamespace(files={"bundle-a": file_obj}, objects=[obj])

        assets = core.get_available_assets(show_all=True)
        self.assertEqual(len(assets), 1)
        self.assertTrue(assets[0].edit_data(_image()).is_success)
        self.assertIn(("bundle-a", 4), core._stream_captures)

    def test_inline_save_does_not_consume_captures(self) -> None:
        core = ABVMECore()
        file_obj = _Bundle({"CAB-x.resS": _ress_reader(b"DATA")})
        core._env = _bundle_env(file_obj, [])
        core.register_stream_capture(
            "bundle-a", 1, StreamCapture(path="CAB-x.resS", offset=0, size=4)
        )
        with tempfile.TemporaryDirectory() as td:
            core._save_fileobj(
                file_obj,
                Path(td) / "out.bundle",
                "none",
                source_path="bundle-a",
                original_crc32=None,
                crc_mode="off",
                resource_patch_mode=ResourcePatchMode.INLINE,
            )
        self.assertIn(("bundle-a", 1), core._stream_captures)
        self.assertEqual(_ress_bytes(file_obj.files["CAB-x.resS"]), b"DATA")


class SkipWhenNoCapturesTests(unittest.TestCase):
    def test_skip_apply_when_source_has_no_captures(self) -> None:
        from models.resource_patch import apply_resource_patch

        reader = _ress_reader(b"KEEP")
        file_obj = _Bundle({"CAB-x.resS": reader})
        env = _bundle_env(file_obj, [])
        captures = {
            ("other-bundle", 1): StreamCapture(path="CAB-x.resS", offset=0, size=4),
        }

        warnings = apply_resource_patch(
            file_obj=file_obj,
            source_path="bundle-a",
            captures=captures,
            mode=ResourcePatchMode.RESOURCE_PATCH,
            env=env,
        )

        self.assertEqual(warnings, [])
        self.assertIs(file_obj.files["CAB-x.resS"], reader)


if __name__ == "__main__":
    unittest.main()
