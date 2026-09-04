import os
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import QApplication, QDialog, QGridLayout, QTabWidget, QWidget

from utilities.app_info import (
    APP_DESCRIPTION,
    APP_NAME,
    AUTHOR_GITHUB_URL,
    AUTHOR_NAME,
    RELEASES_URL,
    app_version,
    window_title,
)
from views.about_dialog import AboutDialog
from views.main_window import ABVMEMainWindow


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _pyproject() -> dict:
    path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


class AppInfoTests(unittest.TestCase):
    def test_reads_name_version_description_from_pyproject(self) -> None:
        project = _pyproject()
        self.assertEqual(APP_NAME, project["name"])
        self.assertEqual(app_version(), project["version"])
        self.assertEqual(APP_DESCRIPTION, project["description"])

    def test_window_title_is_name_v_version(self) -> None:
        self.assertEqual(window_title(), f"{APP_NAME} v{app_version()}")

    def test_releases_url_matches_readme_latest(self) -> None:
        self.assertEqual(RELEASES_URL, "https://github.com/com55/ABVME/releases/latest")
        self.assertEqual(AUTHOR_GITHUB_URL, "https://github.com/com55")


class AboutMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.window = ABVMEMainWindow(settings=self.settings)

    def tearDown(self) -> None:
        self.window.close()
        self.settings.clear()

    def test_window_title_includes_version(self) -> None:
        self.assertEqual(self.window.windowTitle(), window_title())

    def test_default_window_size_is_1200_by_700(self) -> None:
        self.assertEqual(self.window.size(), QSize(1200, 700))

    def test_about_is_top_level_action_without_submenu(self) -> None:
        titles = [action.text() for action in self.window.menuBar().actions()]
        self.assertEqual(titles, ["&File", "&Asset", "&Options", "About"])
        about = self.window.about_action
        self.assertEqual(about.text(), "About")
        self.assertIsNone(about.menu())
        self.assertFalse(about.isCheckable())

    def test_about_action_opens_dialog(self) -> None:
        with patch("views.main_window.AboutDialog.exec", return_value=0) as exec_mock:
            self.window.about_action.trigger()
        exec_mock.assert_called_once()


class AboutDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.dialog = AboutDialog()
        self.addCleanup(self.dialog.close)

    def test_header_shows_name_version_and_icon(self) -> None:
        self.assertEqual(self.dialog.windowTitle(), f"About {APP_NAME}")
        self.assertEqual(self.dialog.product_title_label.text(), APP_NAME)
        self.assertEqual(self.dialog.product_version_label.text(), f"v{app_version()}")
        pixmap = self.dialog.icon_label.pixmap()
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())

    def test_info_and_license_tabs(self) -> None:
        tabs = self.dialog.tabs
        self.assertIsInstance(tabs, QTabWidget)
        self.assertEqual(
            [tabs.tabText(i) for i in range(tabs.count())],
            ["Info", "License"],
        )
        self.assertIn(APP_DESCRIPTION, self.dialog.description_label.text())
        self.assertEqual(self.dialog.product_name_value.text(), APP_NAME)
        self.assertEqual(self.dialog.version_value.text(), app_version())
        self.assertEqual(self.dialog.author_name_label.text(), AUTHOR_NAME)
        self.assertIn("Check for Updates", self.dialog.updates_link.text())
        self.assertIn(RELEASES_URL, self.dialog.updates_link.text())
        self.assertIn(AUTHOR_GITHUB_URL, self.dialog.author_link.text())
        self.assertIn("Unity Technologies", self.dialog.disclaimer_label.text())
        self.assertTrue(self.dialog.updates_link.openExternalLinks())

    def test_info_tables_are_three_columns_with_links_on_the_right(self) -> None:
        version_grid = self.dialog.info_grid
        authors_grid = self.dialog.authors_grid
        self.assertIsInstance(version_grid, QGridLayout)
        self.assertEqual(version_grid.columnCount(), 3)
        self.assertEqual(authors_grid.columnCount(), 3)

        _row, column, _rs, _cs = version_grid.getItemPosition(
            version_grid.indexOf(self.dialog.updates_link)
        )
        self.assertEqual(column, 2)
        self.assertTrue(
            bool(self.dialog.updates_link.alignment() & Qt.AlignmentFlag.AlignRight)
        )

        _row, column, _rs, _cs = authors_grid.getItemPosition(
            authors_grid.indexOf(self.dialog.author_link)
        )
        self.assertEqual(column, 2)

        _row, name_col, _rs, _cs = version_grid.getItemPosition(
            version_grid.indexOf(self.dialog.product_name_value)
        )
        _row, author_col, _rs, _cs = authors_grid.getItemPosition(
            authors_grid.indexOf(self.dialog.author_name_label)
        )
        self.assertEqual(name_col, author_col)
        self.assertEqual(name_col, 1)

    def test_info_panels_use_gray_background(self) -> None:
        panels = [
            widget
            for widget in self.dialog.findChildren(QWidget)
            if widget.objectName() == "aboutInfoPanel"
        ]
        self.assertEqual(len(panels), 2)
        for panel in panels:
            self.assertIn("#323232", panel.styleSheet())
        for label in (
            self.dialog.product_name_value,
            self.dialog.version_value,
            self.dialog.author_name_label,
        ):
            self.assertIn("#323232", label.styleSheet())

    def test_license_tab_shows_mit_text(self) -> None:
        text = self.dialog.license_view.toPlainText()
        self.assertIn("MIT License", text)
        self.assertIn("Permission is hereby granted", text)

    def test_close_button_rejects(self) -> None:
        self.dialog.close_button.click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)
