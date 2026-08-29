import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from models.crc import (
    compute_crc32,
    crc_corrector,
    crc_should_run,
    decimal_crc_from_stem,
    get_build_target_name,
)


class CrcCorrectorTests(unittest.TestCase):
    def test_append_matches_desired_crc(self) -> None:
        payload = b"UnityFS\x00fake-bundle"
        desired = compute_crc32(b"original-bytes")
        out = crc_corrector(payload, desired)
        self.assertEqual(compute_crc32(out), desired)
        self.assertEqual(len(out), len(payload) + 4)

    def test_rejects_str_desired_crc(self) -> None:
        with self.assertRaises(TypeError):
            crc_corrector(b"abc", "00ABCDEF")  # type: ignore[arg-type]

    def test_overwrite_nonzero_trailer_matches_desired_crc(self) -> None:
        payload = b"UnityFS\x00fake-bundle" + b"\x12\x34\x56\x78"
        desired = compute_crc32(b"corrected-payload")
        out = crc_corrector(payload, desired, append=False)
        self.assertEqual(compute_crc32(out), desired)
        self.assertEqual(len(out), len(payload))

    def test_overwrite_zero_trailer_matches_desired_crc(self) -> None:
        payload = b"UnityFS\x00fake-bundle" + b"\x00\x00\x00\x00"
        desired = compute_crc32(b"corrected-payload")
        out = crc_corrector(payload, desired, append=False)
        self.assertEqual(compute_crc32(out), desired)
        self.assertEqual(len(out), len(payload))


class StemCrcTests(unittest.TestCase):
    def test_decimal_suffix(self) -> None:
        self.assertEqual(decimal_crc_from_stem("icon_123456"), 123456)

    def test_non_decimal_is_none(self) -> None:
        self.assertEqual(decimal_crc_from_stem("icon_2"), 2)
        self.assertIsNone(decimal_crc_from_stem("icon"))
        self.assertIsNone(decimal_crc_from_stem("icon_00ABCDEF"))


class BuildTargetTests(unittest.TestCase):
    def test_skips_unknown_and_non_serialized(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import SerializedFile

        ress = SimpleNamespace()  # not SerializedFile
        unknown = MagicMock(spec=SerializedFile)
        unknown.target_platform = BuildTarget.UnknownPlatform
        windows = MagicMock(spec=SerializedFile)
        windows.target_platform = BuildTarget.StandaloneWindows64
        bundle = SimpleNamespace(files={"a.resS": ress, "cab": unknown, "assets": windows})
        self.assertEqual(get_build_target_name(bundle), "StandaloneWindows64")

    def test_root_serialized_file_windows(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import SerializedFile

        sf = MagicMock(spec=SerializedFile)
        sf.target_platform = BuildTarget.StandaloneWindows64
        self.assertEqual(get_build_target_name(sf), "StandaloneWindows64")
        self.assertTrue(crc_should_run("auto", sf))

    def test_root_serialized_file_android(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import SerializedFile

        sf = MagicMock(spec=SerializedFile)
        sf.target_platform = BuildTarget.Android
        self.assertEqual(get_build_target_name(sf), "Android")
        self.assertFalse(crc_should_run("auto", sf))

    def test_nested_bundle_with_serialized_child(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import BundleFile, SerializedFile

        windows = MagicMock(spec=SerializedFile)
        windows.target_platform = BuildTarget.StandaloneWindows64
        inner = MagicMock(spec=BundleFile)
        inner.files = {"assets": windows}
        outer = SimpleNamespace(files={"nested": inner})
        self.assertEqual(get_build_target_name(outer), "StandaloneWindows64")

    def test_auto_windows_only(self) -> None:
        from UnityPy.enums import BuildTarget
        from UnityPy.files import SerializedFile

        win = MagicMock(spec=SerializedFile)
        win.target_platform = BuildTarget.StandaloneWindows
        android = MagicMock(spec=SerializedFile)
        android.target_platform = BuildTarget.Android
        self.assertTrue(crc_should_run("auto", SimpleNamespace(files={"c": win})))
        self.assertFalse(crc_should_run("auto", SimpleNamespace(files={"c": android})))
        self.assertTrue(crc_should_run("on", SimpleNamespace(files={"c": android})))
        self.assertFalse(crc_should_run("off", SimpleNamespace(files={"c": win})))
        self.assertFalse(
            crc_should_run(
                "auto",
                SimpleNamespace(files={"c": MagicMock(spec=SerializedFile, target_platform=BuildTarget.UnknownPlatform)}),
            )
        )


if __name__ == "__main__":
    unittest.main()
