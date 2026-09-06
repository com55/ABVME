import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QHeaderView

from models.asset_model import EMPTY_CELL_TEXT
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
        byte_size: int = 0,
    ) -> None:
        self.name = name
        self.container = container
        self.path_id = path_id
        self.obj_type = SimpleNamespace(name=type_name)
        self.source_path = source_path
        self.is_changed = is_changed
        self.byte_size = byte_size


class AssetTableWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.widget = AssetTableWidget()
        self.widget.setFixedSize(480, 180)

    def _flush(self) -> None:
        self.app.processEvents()

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
        self._flush()
        self.assertLessEqual(self.widget.table.columnWidth(0), MAX_COLUMN_WIDTH)

    def test_auto_fit_scopes_to_visible_rows(self) -> None:
        short_rows = [FakeAsset(name="ab") for _ in range(40)]
        long_row = FakeAsset(name="n" * 400)
        self.widget.resize(480, 180)
        self.widget.show()
        self.app.processEvents()

        self.widget.load_assets(short_rows, auto_fit=True)
        self._flush()
        short_width = self.widget.table.columnWidth(0)

        self.widget.load_assets(short_rows + [long_row], auto_fit=True)
        self._flush()

        self.assertEqual(self.widget.table.columnWidth(0), short_width)
        self.assertLess(short_width, MAX_COLUMN_WIDTH)

    def test_auto_fit_ignores_offscreen_rows_before_show(self) -> None:
        short_rows = [FakeAsset(name="ab") for _ in range(40)]
        long_row = FakeAsset(name="n" * 400)
        self.widget.load_assets(short_rows + [long_row], auto_fit=True)
        self._flush()

        self.assertLess(self.widget.table.columnWidth(0), MAX_COLUMN_WIDTH)

    def test_auto_fit_fits_visible_pathid_text(self) -> None:
        long_path_id = "8156803549656132905"
        visible = [
            FakeAsset(name="aaa_splash", path_id=long_path_id) for _ in range(8)
        ]
        offscreen = [
            FakeAsset(name="zzz_" + ("n" * 400), path_id="1") for _ in range(40)
        ]
        self.widget.resize(480, 220)
        self.widget.show()
        self._flush()
        self.widget.load_assets(visible + offscreen, auto_fit=True)
        self._flush()

        path_width = self.widget.table.columnWidth(2)
        name_width = self.widget.table.columnWidth(0)
        metrics = self.widget.table.fontMetrics()
        self.assertGreaterEqual(
            path_width,
            metrics.horizontalAdvance(long_path_id),
        )
        self.assertLess(name_width, MAX_COLUMN_WIDTH)

    def test_row_heights_use_fixed_mode(self) -> None:
        self.widget.load_assets([FakeAsset()])
        self.assertEqual(
            self.widget.table.verticalHeader().sectionResizeMode(0),
            QHeaderView.ResizeMode.Fixed,
        )

    def test_reload_without_auto_fit_keeps_column_width(self) -> None:
        self.widget.load_assets([FakeAsset(name="a")], auto_fit=True)
        self._flush()
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
        for col in range(self.widget.table.columnCount()):
            item = self.widget.table.item(0, col)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.foreground().color(), expected)

    def test_unchanged_row_clears_foreground(self) -> None:
        asset = FakeAsset(name="hero", is_changed=True)
        self.widget.load_assets([asset])
        asset.is_changed = False
        self.widget.refresh_asset_display(asset)
        for col in range(self.widget.table.columnCount()):
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

    def test_headers_include_size_before_sourcefile(self) -> None:
        labels = [
            self.widget.table.horizontalHeaderItem(i).text()
            for i in range(self.widget.table.columnCount())
        ]
        self.assertEqual(
            labels,
            ["Name", "Type", "PathID", "Container", "Size", "SourceFile"],
        )
        self.assertEqual(self.widget.table.columnCount(), 6)

    def test_size_cell_is_human_readable_with_raw_tooltip(self) -> None:
        self.widget.load_assets([FakeAsset(byte_size=1536)])
        item = self.widget.table.item(0, 4)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.text(), "1.5 KB")
        self.assertEqual(item.toolTip(), "1536")
        self.assertIsNone(item.data(Qt.ItemDataRole.UserRole))

    def test_zero_size_is_bytes_not_none(self) -> None:
        self.widget.load_assets([FakeAsset(byte_size=0)])
        item = self.widget.table.item(0, 4)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.text(), "0 B")
        self.assertEqual(item.toolTip(), "0")

    def test_size_column_sorts_numerically(self) -> None:
        self.widget.load_assets(
            [
                FakeAsset(name="big", byte_size=2000),
                FakeAsset(name="mid", byte_size=1024),
                FakeAsset(name="tiny", byte_size=10),
            ]
        )
        self.widget.table.sortItems(4, Qt.SortOrder.AscendingOrder)
        names = [
            self.widget.table.item(row, 0).data(Qt.ItemDataRole.UserRole).name
            for row in range(3)
        ]
        self.assertEqual(names, ["tiny", "mid", "big"])

    def test_empty_name_shows_dim_none(self) -> None:
        self.widget.load_assets([FakeAsset(name="")])
        item = self.widget.table.item(0, 0)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.text(), EMPTY_CELL_TEXT)
        self.assertEqual(item.foreground().color(), QColor("#808080"))

    def test_empty_changed_name_is_dim_none_star(self) -> None:
        self.widget.load_assets([FakeAsset(name="", is_changed=True)])
        name_item = self.widget.table.item(0, 0)
        type_item = self.widget.table.item(0, 1)
        self.assertIsNotNone(name_item)
        self.assertIsNotNone(type_item)
        assert name_item is not None
        assert type_item is not None
        self.assertEqual(name_item.text(), f"{EMPTY_CELL_TEXT} *")
        self.assertEqual(name_item.foreground().color(), QColor("#808080"))
        self.assertEqual(type_item.foreground().color(), QColor("#7DCEA0"))

    def test_refresh_keeps_empty_name_placeholder(self) -> None:
        asset = FakeAsset(name="")
        self.widget.load_assets([asset])
        asset.is_changed = True
        self.widget.refresh_asset_display(asset)
        item = self.widget.table.item(0, 0)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.text(), f"{EMPTY_CELL_TEXT} *")
        self.assertEqual(item.foreground().color(), QColor("#808080"))

    def test_empty_container_and_source_show_none(self) -> None:
        self.widget.load_assets(
            [FakeAsset(container="", source_path="")]
        )
        container = self.widget.table.item(0, 3)
        source = self.widget.table.item(0, 5)
        self.assertIsNotNone(container)
        self.assertIsNotNone(source)
        assert container is not None
        assert source is not None
        self.assertEqual(container.text(), EMPTY_CELL_TEXT)
        self.assertEqual(source.text(), EMPTY_CELL_TEXT)
        self.assertEqual(source.data(Qt.ItemDataRole.UserRole), "")
        self.assertEqual(container.foreground().color(), QColor("#808080"))
        self.assertEqual(source.foreground().color(), QColor("#808080"))

    def test_unchanged_named_row_keeps_space_suffix(self) -> None:
        self.widget.load_assets([FakeAsset(name="hero")])
        item = self.widget.table.item(0, 0)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.text(), "hero   ")

    def test_sourcefile_filter_index_is_five(self) -> None:
        self.widget.load_assets(
            [FakeAsset(source_path="/bundles/main.bundle")]
        )
        self.assertIn(5, self.widget.header._unique_values)
        self.assertNotIn(4, self.widget.header._unique_values)
        self.assertEqual(
            self.widget.header._unique_values[5],
            ["/bundles/main.bundle"],
        )

    def test_empty_source_filter_checkbox_keeps_empty_value(self) -> None:
        from views.components.custom_filter_header import (
            filter_checkbox_label,
            selected_checkbox_filter_values,
        )

        self.assertEqual(filter_checkbox_label(""), EMPTY_CELL_TEXT)
        self.assertEqual(filter_checkbox_label("/bundles/main.bundle"), "/bundles/main.bundle")

        box = QCheckBox(filter_checkbox_label(""))
        box.setProperty("filter_value", "")
        box.setChecked(True)
        self.assertEqual(selected_checkbox_filter_values([box]), [""])

        self.widget.load_assets(
            [
                FakeAsset(name="blank", source_path=""),
                FakeAsset(name="file", source_path="/bundles/main.bundle"),
            ]
        )
        self.assertIn("", self.widget.header._unique_values[5])
        self.widget.header.active_filters[5] = [""]
        self.widget.apply_filter()
        rows = {
            self.widget.table.item(row, 0).data(Qt.ItemDataRole.UserRole).name: row
            for row in range(self.widget.table.rowCount())
        }
        self.assertFalse(self.widget.table.isRowHidden(rows["blank"]))
        self.assertTrue(self.widget.table.isRowHidden(rows["file"]))


if __name__ == "__main__":
    unittest.main()
