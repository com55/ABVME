import unittest
from datetime import datetime, timedelta, timezone

from utilities.updater import (
    WINDOWS_SETUP_ASSET_NAME,
    find_windows_setup_asset,
    is_newer,
    should_check_for_updates,
    version_tuple,
    ReleaseAsset,
)


class VersionTests(unittest.TestCase):
    def test_version_tuple_strips_v(self):
        self.assertEqual(version_tuple("v1.2.3"), (1, 2, 3))

    def test_is_newer(self):
        self.assertTrue(is_newer("0.2.0", "0.1.9"))
        self.assertFalse(is_newer("0.1.9", "0.1.9"))
        self.assertFalse(is_newer("0.1.8", "0.1.9"))

    def test_status_message_includes_release_name(self):
        from utilities.updater import format_update_status_message

        msg = format_update_status_message("ABVME v0.2.0")
        self.assertIn("ABVME v0.2.0", msg)
        self.assertIn("About", msg)

    def test_update_info_json_roundtrip(self):
        from utilities.updater import (
            ReleaseAsset,
            UpdateInfo,
            update_info_from_json,
            update_info_to_json,
        )

        info = UpdateInfo(
            current_version="0.1.9",
            latest_version="0.2.0",
            release_name="ABVME v0.2.0",
            release_url="https://github.com/com55/ABVME/releases/tag/v0.2.0",
            tag_name="v0.2.0",
            body="notes",
            assets=[
                ReleaseAsset(
                    "ABVME-Windows-x64-Setup.exe", "https://example.invalid/s", 1
                )
            ],
        )
        restored = update_info_from_json(update_info_to_json(info))
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.latest_version, "0.2.0")
        self.assertEqual(restored.release_name, "ABVME v0.2.0")
        self.assertEqual(len(restored.assets), 1)
        self.assertEqual(restored.assets[0].name, "ABVME-Windows-x64-Setup.exe")

    def test_update_info_from_json_empty(self):
        from utilities.updater import update_info_from_json

        self.assertIsNone(update_info_from_json(""))
        self.assertIsNone(update_info_from_json("{not-json"))


class GateTests(unittest.TestCase):
    def test_missing_last_check_should_check(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.assertTrue(should_check_for_updates(None, now=now))

    def test_within_seven_days_skips(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        last = now - timedelta(days=3)
        self.assertFalse(should_check_for_updates(last, now=now))

    def test_seven_days_or_more_checks(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        last = now - timedelta(days=7)
        self.assertTrue(should_check_for_updates(last, now=now))


class AssetTests(unittest.TestCase):
    def test_find_setup_asset(self):
        assets = [
            ReleaseAsset("other.zip", "https://example.invalid/a", 1),
            ReleaseAsset(WINDOWS_SETUP_ASSET_NAME, "https://example.invalid/setup", 2),
        ]
        self.assertEqual(find_windows_setup_asset(assets).name, WINDOWS_SETUP_ASSET_NAME)
        self.assertEqual(WINDOWS_SETUP_ASSET_NAME, "ABVME-Windows-x64-Setup.exe")

    def test_find_setup_asset_missing(self):
        with self.assertRaises(FileNotFoundError):
            find_windows_setup_asset([])


if __name__ == "__main__":
    unittest.main()
