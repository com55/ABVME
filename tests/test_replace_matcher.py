import unittest

from utilities.replace_matcher import (
    MatchStatus,
    ReplaceTarget,
    file_kind,
    match_files,
)


def _target(index, name, kind="TextAsset", container="", path_id=None):
    return ReplaceTarget(
        index=index,
        name=name,
        kind=kind,
        container=container,
        path_id=path_id or str(index),
    )


class FileKindTests(unittest.TestCase):
    def test_image_suffix_is_texture(self):
        self.assertEqual(file_kind("a/hero.PNG"), "Texture2D")

    def test_other_suffix_is_textasset(self):
        self.assertEqual(file_kind("a/hero.skel"), "TextAsset")


class MatchFilesTests(unittest.TestCase):
    def test_stem_matches_texture_name(self):
        targets = [_target(0, "hero", "Texture2D")]
        [m] = match_files(["d/hero.png"], targets)
        self.assertEqual((m.status, m.target_index), (MatchStatus.MATCHED, 0))

    def test_name_match_ignores_case(self):
        targets = [_target(0, "Hero", "Texture2D")]
        [m] = match_files(["d/hero.png"], targets)
        self.assertEqual(m.target_index, 0)

    def test_full_filename_beats_stem(self):
        targets = [
            _target(0, "config"),
            _target(1, "config.json"),
        ]
        [m] = match_files(["d/config.json"], targets)
        self.assertEqual(m.target_index, 1)

    def test_image_never_matches_textasset(self):
        targets = [_target(0, "hero", "TextAsset")]
        [m] = match_files(["d/hero.png"], targets)
        self.assertEqual((m.status, m.target_index), (MatchStatus.NO_MATCH, None))

    def test_non_image_never_matches_texture(self):
        targets = [_target(0, "hero", "Texture2D")]
        [m] = match_files(["d/hero.skel"], targets)
        self.assertEqual(m.status, MatchStatus.NO_MATCH)

    def test_same_name_different_kind_is_not_ambiguous(self):
        targets = [
            _target(0, "hero", "Texture2D"),
            _target(1, "hero", "TextAsset"),
        ]
        results = match_files(["d/hero.png", "d/hero.skel"], targets)
        self.assertEqual([r.target_index for r in results], [0, 1])

    def test_container_contains_filename_resolves_duplicates(self):
        targets = [
            _target(0, "abcde", container="assets/spine/abcde.atlas.bytes"),
            _target(1, "abcde", container="assets/spine/abcde.skel.bytes"),
        ]
        [m] = match_files(["d/abcde.skel"], targets)
        self.assertEqual((m.status, m.target_index), (MatchStatus.MATCHED, 1))

    def test_container_suffix_resolves_when_filename_not_contained(self):
        targets = [
            _target(0, "abcde", container="assets/x/one.atlas.bytes"),
            _target(1, "abcde", container="assets/x/two.skel.bytes"),
        ]
        [m] = match_files(["d/abcde.skel"], targets)
        self.assertEqual(m.target_index, 1)

    def test_unresolved_duplicates_are_ambiguous(self):
        targets = [
            _target(0, "abcde", container="a/abcde.skel.bytes"),
            _target(1, "abcde", container="b/abcde.skel.bytes"),
        ]
        [m] = match_files(["d/abcde.skel"], targets)
        self.assertEqual((m.status, m.target_index), (MatchStatus.AMBIGUOUS, None))

    def test_single_name_hit_ignores_container(self):
        targets = [_target(0, "hero", container="x/unrelated.bytes")]
        [m] = match_files(["d/hero.json"], targets)
        self.assertEqual(m.status, MatchStatus.MATCHED)

    def test_unknown_name_is_no_match(self):
        targets = [_target(0, "hero")]
        [m] = match_files(["d/other.json"], targets)
        self.assertEqual((m.status, m.target_index), (MatchStatus.NO_MATCH, None))

    def test_results_keep_file_order(self):
        targets = [_target(0, "b"), _target(1, "a")]
        results = match_files(["d/a.json", "d/b.json"], targets)
        self.assertEqual([r.file_path for r in results], ["d/a.json", "d/b.json"])
        self.assertEqual([r.target_index for r in results], [1, 0])


if __name__ == "__main__":
    unittest.main()
