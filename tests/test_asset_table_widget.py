import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QHeaderView

from views.asset_table_widget import AssetTableWidget


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class FakeAsset:
    def __init__(
        self,
        name: str = "hero",
        type_name: str = "TextAsset",
        path_id: str = "123",
        container: str = "assets/hero.bytes",
        source_path: str = "/bundles/main.bundle",
        is_changed: bool = False,
    ) -> None:
        self.name = name
        self.container = container
        self.path_id = path_id
        self.obj_type = SimpleNamespace(name=type_name)
        self.source_path = source_path
        self.is_changed = is_changed


class AssetTableWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.widget = AssetTableWidget()

    def test_header_is_interactive_before_load(self) -> None:
        header = self.widget.table.horizontalHeader()
        for section in range(header.count()):
            self.assertEqual(
                header.sectionResizeMode(section),
                QHeaderView.ResizeMode.Interactive,
            )

    def test_load_assets_uses_interactive_and_resizes_columns(self) -> None:
        assets = [
            FakeAsset(name="short"),
            FakeAsset(
                name="very_long_asset_name_for_width",
                type_name="Texture2D",
                path_id="999",
                container="assets/textures/icon.png",
                source_path="/bundles/large.bundle",
            ),
        ]
        self.widget.load_assets(assets)
        header = self.widget.table.horizontalHeader()
        for section in range(header.count()):
            self.assertEqual(
                header.sectionResizeMode(section),
                QHeaderView.ResizeMode.Interactive,
            )
        self.assertTrue(self.widget.table.isSortingEnabled())

    def test_changed_row_foreground_on_all_columns(self) -> None:
        asset = FakeAsset(name="hero", is_changed=True)
        self.widget.load_assets([asset])
        expected = QColor("#7DCEA0")
        for col in range(5):
            item = self.widget.table.item(0, col)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.foreground().color(), expected)

    def test_unchanged_row_clears_foreground(self) -> None:
        asset = FakeAsset(name="hero", is_changed=True)
        self.widget.load_assets([asset])
        asset.is_changed = False
        self.widget.refresh_asset_display(asset)
        for col in range(5):
            item = self.widget.table.item(0, col)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertIsNone(item.data(Qt.ItemDataRole.ForegroundRole))

    def test_changed_name_has_asterisk_suffix(self) -> None:
        asset = FakeAsset(name="hero", is_changed=True)
        self.widget.load_assets([asset])
        item = self.widget.table.item(0, 0)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertTrue(item.text().endswith(" *"))


if __name__ == "__main__":
    unittest.main()
