import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QHeaderView

from views.asset_table_widget import MAX_COLUMN_WIDTH, AssetTableWidget


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

    def test_auto_fit_caps_column_width(self) -> None:
        long_name = "n" * 400
        self.widget.load_assets(
            [FakeAsset(name=long_name)],
            auto_fit=True,
        )
        self.assertLessEqual(self.widget.table.columnWidth(0), MAX_COLUMN_WIDTH)

    def test_auto_fit_scopes_to_visible_rows(self) -> None:
        short_rows = [FakeAsset(name="ab") for _ in range(40)]
        assets = short_rows + [FakeAsset(name="n" * 400)]
        self.widget.resize(480, 180)
        self.widget.show()
        self.app.processEvents()
        self.widget.load_assets(assets, auto_fit=True)
        self.app.processEvents()
        self.assertLess(self.widget.table.columnWidth(0), MAX_COLUMN_WIDTH)
        self.assertEqual(
            self.widget.table.horizontalHeader().resizeContentsPrecision(),
            0,
        )

    def test_row_heights_use_fixed_mode(self) -> None:
        self.widget.load_assets([FakeAsset()])
        self.assertEqual(
            self.widget.table.verticalHeader().sectionResizeMode(0),
            QHeaderView.ResizeMode.Fixed,
        )

    def test_reload_without_auto_fit_keeps_column_width(self) -> None:
        self.widget.load_assets([FakeAsset(name="a")], auto_fit=True)
        self.widget.table.setColumnWidth(0, 42)
        self.widget.load_assets(
            [FakeAsset(name="very_long_asset_name_for_width")],
            auto_fit=False,
        )
        self.assertEqual(self.widget.table.columnWidth(0), 42)

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
