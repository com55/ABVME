import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from utilities.drop_classifier import DropAction, DropDecision
from views.drop_overlay import DropOverlay, _style_action


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


class DropOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.overlay = DropOverlay()
        self.overlay.resize(400, 300)

    def tearDown(self) -> None:
        self.overlay.close()
        self.overlay.deleteLater()

    def test_style_action_maps_confirm_to_replace(self) -> None:
        self.assertEqual(_style_action(DropAction.REPLACE_CONFIRM), DropAction.REPLACE)
        self.assertEqual(_style_action(DropAction.REPLACE), DropAction.REPLACE)
        self.assertEqual(_style_action(DropAction.OPEN), DropAction.OPEN)

    def test_replace_and_confirm_share_panel_stylesheet(self) -> None:
        replace = DropDecision(
            action=DropAction.REPLACE,
            file_paths=("icon.png",),
            title="Replace",
            detail="icon.png → hero",
        )
        confirm = DropDecision(
            action=DropAction.REPLACE_CONFIRM,
            file_paths=("icon.png",),
            title="Replace",
            detail="icon.png → hero",
        )
        self.overlay.show_decision(replace, target_name="hero")
        replace_style = self.overlay.styleSheet()
        self.overlay.clear()
        self.overlay.show_decision(confirm, target_name="hero")
        self.assertEqual(self.overlay.styleSheet(), replace_style)

    def test_long_open_names_elide_against_overlay_width(self) -> None:
        long_name = ("spine-character-" * 8) + "yuuka.bundle"
        decision = DropDecision(
            action=DropAction.OPEN,
            file_paths=(f"bundles/{long_name}",),
            title="Open Asset Bundles",
            detail="",
        )
        self.overlay.show_decision(decision)
        self.app.processEvents()
        self.overlay._apply_elide()

        self.assertEqual(len(self.overlay._line_labels), 1)
        label, original = self.overlay._line_labels[0]
        self.assertEqual(original, long_name)
        self.assertIn("…", label.text())
        self.assertLess(label.fontMetrics().horizontalAdvance(label.text()), 400)
        self.assertEqual(label.toolTip(), long_name)

    def test_title_and_body_have_text_glow(self) -> None:
        decision = DropDecision(
            action=DropAction.OPEN,
            file_paths=("a.bundle",),
            title="Open Asset Bundles",
            detail="",
        )
        self.overlay.show_decision(decision)
        self.app.processEvents()
        self.assertIsNotNone(self.overlay._title.graphicsEffect())
        self.assertEqual(len(self.overlay._line_labels), 1)
        self.assertIsNotNone(self.overlay._line_labels[0][0].graphicsEffect())
