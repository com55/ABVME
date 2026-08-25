import unittest
from pathlib import Path


class MenuDisabledStyleTests(unittest.TestCase):
    def test_qss_defines_disabled_menu_colors(self) -> None:
        qss = (Path(__file__).resolve().parents[1] / "styles.qss").read_text(
            encoding="utf-8"
        )
        self.assertIn("QMenuBar::item:disabled", qss)
        self.assertIn("QMenu::item:disabled", qss)
        self.assertIn("QMenu::indicator", qss)
        self.assertIn("QCheckBox::indicator", qss)
        self.assertRegex(qss, r"QMenu::item\s*\{[^}]*padding:\s*2px 4px 2px 8px")
        self.assertNotRegex(qss, r"QMenu::item\s*\{[^}]*margin-left:")
        self.assertIn("menu-gutter-line.svg", qss)
        self.assertRegex(qss, r"QMenu::item:selected\s*\{[^}]*border:")
        self.assertRegex(qss, r"QMenu::icon\s*\{[^}]*width:\s*16px")
        self.assertRegex(qss, r"QCheckBox::indicator\s*\{[^}]*width:\s*11px")
        self.assertRegex(qss, r"QMenu QCheckBox\s*\{[^}]*margin-left:\s*4px")


if __name__ == "__main__":
    unittest.main()
