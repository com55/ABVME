import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from viewmodels.main_viewmodel import MainViewModel
from views.components.custom_filter_header import FilterHeader
from views.main_window import ABVMEMainWindow


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class ShowAllViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def test_default_reads_false_from_settings(self) -> None:
        self.assertFalse(self.vm.show_all_objects)

    def test_set_show_all_objects_writes_settings(self) -> None:
        self.vm.set_show_all_objects(True)

        self.assertTrue(self.vm.show_all_objects)
        self.assertTrue(self.settings.value("show_all_objects", False, type=bool))

        self.vm.set_show_all_objects(False)

        self.assertFalse(self.vm.show_all_objects)
        self.assertFalse(self.settings.value("show_all_objects", True, type=bool))


class MenubarShowAllActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_show_all_action_exists_and_is_checkable(self) -> None:
        window = ABVMEMainWindow()
        action = window.show_all_action

        self.assertEqual(action.text(), "Show all objects")
        self.assertTrue(action.isCheckable())
        self.assertEqual(action.isChecked(), window.viewmodel.show_all_objects)


class FilterBoxExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_new_types_are_selected_when_previous_filter_was_all(self) -> None:
        header = FilterHeader()
        header.set_filter_boxes(1, ["TextAsset", "Texture2D"])

        header.set_filter_boxes(1, ["Mesh", "TextAsset", "Texture2D"])

        self.assertEqual(
            header.active_filters[1],
            ["Mesh", "TextAsset", "Texture2D"],
        )

    def test_narrowed_type_filter_is_kept(self) -> None:
        header = FilterHeader()
        header.set_filter_boxes(1, ["TextAsset", "Texture2D"])
        header.active_filters[1] = ["TextAsset"]

        header.set_filter_boxes(1, ["Mesh", "TextAsset", "Texture2D"])

        self.assertEqual(header.active_filters[1], ["TextAsset"])


if __name__ == "__main__":
    unittest.main()
