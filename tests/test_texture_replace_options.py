import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from models.texture_replace_options import (
    DESTINATION_FORMAT_LABEL,
    TEXTURE_FORMAT_CHOICES,
    TextureReplaceOptions,
    mipmap_count_for,
)
from viewmodels.main_viewmodel import MainViewModel
from views.main_window import ABVMEMainWindow
from views.texture_replace_dialog import (
    TextureReplaceDialog,
    _FIELD_WIDTH,
    _OPTIONS_WIDTH,
)


def _app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _texture(**overrides: object) -> SimpleNamespace:
    settings = SimpleNamespace(
        m_FilterMode=1,
        m_Aniso=1,
        m_MipBias=0.0,
        m_WrapMode=1,
        m_WrapU=1,
        m_WrapV=1,
        m_WrapW=None,
    )
    data = SimpleNamespace(
        m_TextureFormat=4,
        m_MipMap=False,
        m_MipCount=1,
        m_LightmapFormat=0,
        m_ColorSpace=1,
        m_TextureSettings=settings,
        m_Width=64,
        m_Height=64,
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


class TextureReplaceOptionsTests(unittest.TestCase):
    def test_format_choices_start_with_destination_and_include_astc(self) -> None:
        labels = [label for label, _value in TEXTURE_FORMAT_CHOICES]
        self.assertEqual(labels[0], DESTINATION_FORMAT_LABEL)
        self.assertIsNone(TEXTURE_FORMAT_CHOICES[0][1])
        self.assertIn("BC7", labels)
        self.assertIn("ASTC_RGB_6x6", labels)
        self.assertIn("ASTC_RGBA_4x4", labels)
        self.assertNotIn("ASTC_HDR_6x6", labels)
        self.assertNotIn("DXT3", labels)

    def test_from_texture_copies_object_fields(self) -> None:
        data = _texture(
            m_TextureFormat=25,
            m_MipMap=True,
            m_MipCount=4,
            m_LightmapFormat=2,
            m_ColorSpace=0,
        )
        data.m_TextureSettings.m_FilterMode = 2
        data.m_TextureSettings.m_Aniso = 8
        data.m_TextureSettings.m_MipBias = -0.5
        data.m_TextureSettings.m_WrapU = 0
        data.m_TextureSettings.m_WrapV = 2

        options = TextureReplaceOptions.from_texture(data)

        self.assertIsNone(options.target_format)
        self.assertTrue(options.has_mip_maps)
        self.assertEqual(options.mipmap_count, 4)
        self.assertEqual(options.filter_mode, 2)
        self.assertEqual(options.aniso, 8)
        self.assertEqual(options.mip_bias, -0.5)
        self.assertEqual(options.wrap_u, 0)
        self.assertEqual(options.wrap_v, 2)
        self.assertEqual(options.lightmap_format, 2)
        self.assertEqual(options.color_space, 0)

    def test_resolve_target_format_uses_object_when_destination(self) -> None:
        data = _texture(m_TextureFormat=10)
        options = TextureReplaceOptions.from_texture(data)
        self.assertEqual(options.resolve_target_format(data), 10)

        options.target_format = 25
        self.assertEqual(options.resolve_target_format(data), 25)

    def test_mipmap_count_for_respects_checkbox_and_original(self) -> None:
        self.assertEqual(
            mipmap_count_for(64, 64, has_mip_maps=False, stored_count=8), 1
        )
        self.assertEqual(mipmap_count_for(64, 64, has_mip_maps=True, stored_count=4), 4)
        generated = mipmap_count_for(64, 64, has_mip_maps=True, stored_count=1)
        self.assertGreater(generated, 1)

    def test_apply_settings_writes_texture_fields(self) -> None:
        data = _texture()
        options = TextureReplaceOptions(
            target_format=25,
            has_mip_maps=True,
            mipmap_count=3,
            filter_mode=0,
            aniso=4,
            mip_bias=1.5,
            wrap_u=2,
            wrap_v=0,
            lightmap_format=3,
            color_space=0,
        )

        options.apply_settings(data)

        self.assertEqual(data.m_TextureSettings.m_FilterMode, 0)
        self.assertEqual(data.m_TextureSettings.m_Aniso, 4)
        self.assertEqual(data.m_TextureSettings.m_MipBias, 1.5)
        self.assertEqual(data.m_TextureSettings.m_WrapU, 2)
        self.assertEqual(data.m_TextureSettings.m_WrapV, 0)
        self.assertEqual(data.m_LightmapFormat, 3)
        self.assertEqual(data.m_ColorSpace, 0)


class AlwaysShowTextureOptionsSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.settings = QSettings("ABVMETest", "ABVME")
        self.settings.clear()
        self.vm = MainViewModel(settings=self.settings)

    def tearDown(self) -> None:
        self.settings.clear()

    def test_always_show_texture_options_defaults_false(self) -> None:
        self.assertFalse(self.vm.always_show_texture_options)

    def test_set_always_show_texture_options_persists(self) -> None:
        self.vm.set_always_show_texture_options(True)
        self.assertTrue(self.vm.always_show_texture_options)
        other = MainViewModel(settings=self.settings)
        self.assertTrue(other.always_show_texture_options)


class TextureReplaceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_dialog_defaults_from_options_and_has_replace_cancel(self) -> None:
        options = TextureReplaceOptions.from_texture(_texture(m_TextureFormat=25))
        dialog = TextureReplaceDialog(
            options,
            texture_name="CH0158_spr",
            file_name="icon.png",
            always_show=False,
        )

        self.assertEqual(dialog.windowTitle(), "Texture Replace Options")
        self.assertEqual(dialog.format_combo.currentText(), DESTINATION_FORMAT_LABEL)
        self.assertEqual(dialog.texture_name_label.text(), "CH0158_spr")
        self.assertEqual(dialog.old_preview_label.text(), "Old image")
        self.assertIn("New image", dialog.new_preview_label.text())
        self.assertIn("icon.png", dialog.new_preview_label.text())
        self.assertFalse(dialog.has_mip_maps_check.isChecked())
        self.assertFalse(dialog.always_show_check.isChecked())
        self.assertEqual(dialog.cancel_button.text(), "Cancel")
        self.assertEqual(dialog.replace_button.text(), "Replace")
        dialog.show()
        dialog.adjustSize()
        _app().processEvents()
        self.assertLess(
            dialog.old_image_label.mapTo(dialog, dialog.old_image_label.pos()).x(),
            dialog.format_combo.mapTo(dialog, dialog.format_combo.pos()).x(),
        )
        self.assertLess(
            dialog.format_combo.mapTo(dialog, dialog.format_combo.pos()).y(),
            dialog.always_show_check.mapTo(dialog, dialog.always_show_check.pos()).y(),
        )
        self.assertEqual(
            dialog.replace_button.pos().y(),
            dialog.cancel_button.pos().y(),
        )
        self.assertLess(
            dialog.cancel_button.pos().x(),
            dialog.replace_button.pos().x(),
        )
        field_widths = {
            dialog.format_combo.width(),
            dialog.filter_combo.width(),
            dialog.wrap_u_combo.width(),
            dialog.wrap_v_combo.width(),
            dialog.color_combo.width(),
            dialog.aniso_spin.width(),
            dialog.mip_bias_spin.width(),
            dialog.lightmap_spin.width(),
        }
        self.assertEqual(field_widths, {_FIELD_WIDTH})
        left_edges = {
            dialog.format_combo.mapTo(dialog, dialog.format_combo.pos()).x(),
            dialog.filter_combo.mapTo(dialog, dialog.filter_combo.pos()).x(),
            dialog.aniso_spin.mapTo(dialog, dialog.aniso_spin.pos()).x(),
            dialog.color_combo.mapTo(dialog, dialog.color_combo.pos()).x(),
        }
        self.assertEqual(len(left_edges), 1)
        dialog.hide()

    def test_options_panel_fixed_preview_expands_on_resize(self) -> None:
        options = TextureReplaceOptions.from_texture(_texture())
        dialog = TextureReplaceDialog(
            options,
            texture_name="tex",
            file_name="icon.png",
        )
        dialog.show()
        dialog.resize(720, 520)
        _app().processEvents()
        options_w = dialog.options_panel.width()
        preview_w = dialog.old_image_label.width()
        self.assertEqual(options_w, _OPTIONS_WIDTH)

        dialog.resize(1000, 520)
        _app().processEvents()
        self.assertEqual(dialog.options_panel.width(), _OPTIONS_WIDTH)
        self.assertGreater(dialog.old_image_label.width(), preview_w)
        dialog.hide()

    def test_dialog_always_show_checkbox_reflects_argument(self) -> None:
        options = TextureReplaceOptions.from_texture(_texture())
        dialog = TextureReplaceDialog(
            options,
            texture_name="tex",
            file_name="icon.png",
            always_show=True,
        )
        self.assertTrue(dialog.always_show_check.isChecked())

    def test_collect_options_reads_explicit_format(self) -> None:
        options = TextureReplaceOptions.from_texture(_texture())
        dialog = TextureReplaceDialog(
            options,
            texture_name="tex",
            file_name="icon.png",
        )
        index = dialog.format_combo.findData(25)
        self.assertGreater(index, 0)
        dialog.format_combo.setCurrentIndex(index)
        dialog.has_mip_maps_check.setChecked(True)

        collected = dialog.collect_options()
        self.assertEqual(collected.target_format, 25)
        self.assertTrue(collected.has_mip_maps)


class TextureReplaceConfirmFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = ABVMEMainWindow()

    def test_options_menu_does_not_list_always_show_texture_options(self) -> None:
        labels = []
        for item in self.window._options_menu.actions():
            if item.isSeparator():
                labels.append("---")
            else:
                labels.append(item.text().replace("&", ""))
        self.assertEqual(labels, ["Display all assets", "---", "Save Options"])
        self.assertFalse(hasattr(self.window, "always_show_texture_options_action"))

    def test_ask_replace_with_options_is_qmessagebox_like_textasset(self) -> None:
        boxes: list[QMessageBox] = []

        def fake_exec(box: QMessageBox) -> int:
            boxes.append(box)
            return QMessageBox.StandardButton.Yes

        with patch.object(QMessageBox, "exec", fake_exec):
            result = self.window._ask_replace_with_options(
                "Confirm Replace",
                "Replace 'Icon' with 'icon.png'?",
            )

        self.assertEqual(result, "yes")
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        self.assertEqual(box.icon(), QMessageBox.Icon.Question)
        self.assertGreaterEqual(box.minimumWidth(), 450)
        self.assertGreaterEqual(box.minimumHeight(), 140)
        options_btn = next(btn for btn in box.buttons() if btn.text() == "Options...")
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        no_btn = box.button(QMessageBox.StandardButton.No)
        self.assertIsNotNone(yes_btn)
        self.assertIsNotNone(no_btn)
        self.assertEqual(
            box.buttonRole(options_btn),
            QMessageBox.ButtonRole.ActionRole,
        )
        self.assertTrue(options_btn.isFlat())
        box.show()
        box.adjustSize()
        _app().processEvents()
        self.assertLess(options_btn.pos().x(), yes_btn.pos().x())
        self.assertLess(yes_btn.pos().x(), no_btn.pos().x())
        box.hide()


class FakeAsset:
    def __init__(self, type_name: str = "Texture2D") -> None:
        self.name = "Icon"
        self.container = "assets/icon.png"
        self.obj_type = SimpleNamespace(name=type_name)


class TextureReplaceEditPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = ABVMEMainWindow()

    @patch.object(ABVMEMainWindow, "_confirm_texture_replace")
    @patch(
        "views.main_window.QFileDialog.getOpenFileName",
        return_value=("icon.png", ""),
    )
    def test_texture_replace_passes_options_to_edit_asset(
        self,
        _get_open: MagicMock,
        confirm: MagicMock,
    ) -> None:
        options = TextureReplaceOptions(target_format=25)
        confirm.return_value = options
        asset = FakeAsset()
        self.window.viewmodel.get_single_selected_asset = MagicMock(return_value=asset)
        self.window.viewmodel.is_editing_supported = MagicMock(return_value=True)
        self.window.viewmodel.get_edit_file_filter = MagicMock(
            return_value="All Files (*.*)"
        )
        self.window.viewmodel.edit_asset = MagicMock(return_value=True)

        self.window._on_edit_button_clicked()

        confirm.assert_called_once()
        kwargs = self.window.viewmodel.edit_asset.call_args.kwargs
        self.assertIs(kwargs.get("texture_options"), options)

    @patch.object(ABVMEMainWindow, "_show_texture_replace_dialog")
    @patch.object(ABVMEMainWindow, "_ask_replace_with_options", return_value="options")
    def test_options_button_opens_full_dialog(
        self,
        _ask: MagicMock,
        show: MagicMock,
    ) -> None:
        expected = TextureReplaceOptions(target_format=10)
        show.return_value = expected
        asset = FakeAsset()
        self.window.viewmodel.always_show_texture_options = False

        result = self.window._confirm_texture_replace(asset, "icon.png")

        show.assert_called_once()
        self.assertIs(result, expected)

    @patch.object(ABVMEMainWindow, "_show_texture_replace_dialog")
    @patch.object(ABVMEMainWindow, "_ask_replace_with_options")
    def test_always_show_skips_simple_confirm(
        self,
        ask: MagicMock,
        show: MagicMock,
    ) -> None:
        show.return_value = TextureReplaceOptions()
        asset = FakeAsset()
        self.window.viewmodel.always_show_texture_options = True

        self.window._confirm_texture_replace(asset, "icon.png")

        ask.assert_not_called()
        show.assert_called_once()
