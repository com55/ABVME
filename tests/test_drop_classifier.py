import tempfile
import unittest
from pathlib import Path

from utilities.drop_classifier import (
    DropAction,
    classify_drop,
    suffix_in_container,
)


class SuffixInContainerTests(unittest.TestCase):
    def test_skel_matches_skel_bytes_container(self):
        self.assertTrue(
            suffix_in_container("hero.skel", "assets/hero.skel.bytes")
        )

    def test_bytes_matches_skel_bytes_container(self):
        self.assertTrue(
            suffix_in_container("hero.bytes", "assets/hero.skel.bytes")
        )

    def test_json_does_not_match_skel_bytes(self):
        self.assertFalse(
            suffix_in_container("hero.json", "assets/hero.skel.bytes")
        )

    def test_byte_does_not_match_bytes_suffix(self):
        self.assertFalse(
            suffix_in_container("hero.byte", "assets/hero.skel.bytes")
        )

    def test_empty_container_never_matches(self):
        self.assertFalse(suffix_in_container("hero.skel", ""))


class ClassifyDropTests(unittest.TestCase):
    def test_all_bundles_are_open(self):
        d = classify_drop(
            ["a.bundle", "b.unity3d"],
            selected_type="TextAsset",
            selected_name="x",
            selected_container="a.skel.bytes",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.OPEN)

    def test_mixed_open_and_replace_rejects(self):
        d = classify_drop(
            ["a.bundle", "tex.png"],
            selected_type="Texture2D",
            selected_name="Icon",
            selected_container="",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.REJECT)

    def test_png_on_texture_is_replace(self):
        d = classify_drop(
            ["icon.png"],
            selected_type="Texture2D",
            selected_name="Icon",
            selected_container="assets/icon.png",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.REPLACE)

    def test_txt_on_texture_rejects(self):
        d = classify_drop(
            ["note.txt"],
            selected_type="Texture2D",
            selected_name="Icon",
            selected_container="",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.REJECT)

    def test_textasset_matching_suffix_replaces_without_confirm(self):
        d = classify_drop(
            ["hero.skel"],
            selected_type="TextAsset",
            selected_name="hero",
            selected_container="assets/hero.skel.bytes",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.REPLACE)

    def test_textasset_unknown_suffix_needs_confirm(self):
        d = classify_drop(
            ["hero.json"],
            selected_type="TextAsset",
            selected_name="hero",
            selected_container="assets/hero.skel.bytes",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.REPLACE_CONFIRM)

    def test_textasset_without_selection_rejects(self):
        d = classify_drop(
            ["hero.json"],
            selected_type=None,
            selected_name=None,
            selected_container=None,
            can_replace=False,
        )
        self.assertEqual(d.action, DropAction.REJECT)

    def test_open_suffix_wins_over_selected_textasset(self):
        d = classify_drop(
            ["data.bundle"],
            selected_type="TextAsset",
            selected_name="hero",
            selected_container="assets/hero.skel.bytes",
            can_replace=True,
        )
        self.assertEqual(d.action, DropAction.OPEN)

    def test_unityfs_without_open_suffix_is_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "something.dat"
            path.write_bytes(b"UnityFSX")
            d = classify_drop(
                [str(path)],
                selected_type="TextAsset",
                selected_name="hero",
                selected_container="assets/hero.skel.bytes",
                can_replace=True,
            )
            self.assertEqual(d.action, DropAction.OPEN)

    def test_dat_without_unityfs_header_is_not_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "something.dat"
            path.write_bytes(b"notunity")
            d = classify_drop(
                [str(path)],
                selected_type="TextAsset",
                selected_name="hero",
                selected_container="assets/hero.skel.bytes",
                can_replace=True,
            )
            self.assertEqual(d.action, DropAction.REPLACE_CONFIRM)


if __name__ == "__main__":
    unittest.main()
