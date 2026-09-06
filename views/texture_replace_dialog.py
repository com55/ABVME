"""Dialog for Texture2D replace options."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.texture_replace_options import (
    COLOR_SPACE_LABELS,
    FILTER_MODE_LABELS,
    TEXTURE_FORMAT_CHOICES,
    WRAP_MODE_LABELS,
    TextureReplaceOptions,
)

_PREVIEW_MIN = 200
# Fixed B+C width: label column + gap + field column.
_OPTIONS_WIDTH = 300
_FIELD_WIDTH = 175
_PREVIEW_STYLE = (
    "QLabel#texturePreviewImage {"
    " background-color: #252526;"
    " border: 1px solid #555555;"
    " border-radius: 4px;"
    "}"
)
_NEW_FILE_STYLE = "color: #888888; font-size: 10px;"


class _PreviewLabel(QLabel):
    """QLabel that keeps a source pixmap scaled to fit the widget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source = QPixmap()
        self.setObjectName("texturePreviewImage")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(_PREVIEW_MIN, _PREVIEW_MIN)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setText("(none)")

    def set_source(self, pixmap: QPixmap | None) -> None:
        self._source = (
            QPixmap() if pixmap is None or pixmap.isNull() else QPixmap(pixmap)
        )
        self._refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._source.isNull():
            self.setText("(none)")
            self.setPixmap(QPixmap())
            return
        self.setText("")
        size = self.contentsRect().size()
        if size.width() < 1 or size.height() < 1:
            return
        self.setPixmap(
            self._source.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class TextureReplaceDialog(QDialog):
    """A: flexible previews. B+C: fixed-width options (C left-aligned)."""

    def __init__(
        self,
        options: TextureReplaceOptions,
        *,
        texture_name: str,
        file_name: str,
        old_pixmap: QPixmap | None = None,
        new_pixmap: QPixmap | None = None,
        always_show: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._original = options
        self.setWindowTitle("Texture Replace Options")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(720, 520)
        self.setStyleSheet(_PREVIEW_STYLE)

        root = QHBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(12, 12, 12, 12)

        # A — expands with the window.
        preview_host = QWidget()
        preview_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        previews = QVBoxLayout(preview_host)
        previews.setContentsMargins(0, 0, 0, 0)
        previews.setSpacing(12)
        self.old_preview_label = QLabel("Old image")
        self.old_image_label = _PreviewLabel()
        self.old_image_label.set_source(old_pixmap)

        self.new_preview_label = QLabel()
        self.new_preview_label.setTextFormat(Qt.TextFormat.RichText)
        self.new_preview_label.setText(_new_image_caption(file_name))
        self.new_image_label = _PreviewLabel()
        self.new_image_label.set_source(new_pixmap)

        previews.addWidget(self.old_preview_label)
        previews.addWidget(self.old_image_label, stretch=1)
        previews.addWidget(self.new_preview_label)
        previews.addWidget(self.new_image_label, stretch=1)
        root.addWidget(preview_host, stretch=1)

        # B+C — fixed width; does not grow on resize.
        self.options_panel = QWidget()
        self.options_panel.setFixedWidth(_OPTIONS_WIDTH)
        self.options_panel.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        right = QVBoxLayout(self.options_panel)
        right.setSpacing(10)
        right.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setHorizontalSpacing(12)
        form.setSpacing(8)

        self.texture_name_label = QLabel(texture_name)
        form.addRow("Texture", _field_cell(self.texture_name_label))

        self.format_combo = QComboBox()
        for label, value in TEXTURE_FORMAT_CHOICES:
            self.format_combo.addItem(label, value)
        self.format_combo.setCurrentIndex(0)
        if options.target_format is not None:
            index = self.format_combo.findData(options.target_format)
            if index >= 0:
                self.format_combo.setCurrentIndex(index)
        form.addRow("Texture format", _field_cell(self.format_combo))

        self.has_mip_maps_check = QCheckBox()
        self.has_mip_maps_check.setChecked(options.has_mip_maps)
        form.addRow("Has mip maps", _field_cell(self.has_mip_maps_check))

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(list(FILTER_MODE_LABELS))
        self.filter_combo.setCurrentIndex(
            _clamp_index(options.filter_mode, FILTER_MODE_LABELS)
        )
        form.addRow("Filter mode", _field_cell(self.filter_combo))

        self.aniso_spin = QSpinBox()
        self.aniso_spin.setRange(0, 16)
        self.aniso_spin.setValue(_clamp(options.aniso, 0, 16))
        form.addRow("Anisotropic filtering", _field_cell(self.aniso_spin))

        self.mip_bias_spin = QDoubleSpinBox()
        self.mip_bias_spin.setRange(-16.0, 16.0)
        self.mip_bias_spin.setDecimals(2)
        self.mip_bias_spin.setSingleStep(0.1)
        self.mip_bias_spin.setValue(options.mip_bias)
        form.addRow("Mip map bias", _field_cell(self.mip_bias_spin))

        self.wrap_u_combo = QComboBox()
        self.wrap_u_combo.addItems(list(WRAP_MODE_LABELS))
        self.wrap_u_combo.setCurrentIndex(
            _clamp_index(options.wrap_u, WRAP_MODE_LABELS)
        )
        form.addRow("Wrap mode (U)", _field_cell(self.wrap_u_combo))

        self.wrap_v_combo = QComboBox()
        self.wrap_v_combo.addItems(list(WRAP_MODE_LABELS))
        self.wrap_v_combo.setCurrentIndex(
            _clamp_index(options.wrap_v, WRAP_MODE_LABELS)
        )
        form.addRow("Wrap mode (V)", _field_cell(self.wrap_v_combo))

        self.lightmap_spin = QSpinBox()
        lightmap_max = max(255, options.lightmap_format)
        self.lightmap_spin.setRange(0, lightmap_max)
        self.lightmap_spin.setDisplayIntegerBase(16)
        self.lightmap_spin.setPrefix("0x")
        self.lightmap_spin.setValue(options.lightmap_format)
        form.addRow("Lightmap format", _field_cell(self.lightmap_spin))

        self.color_combo = QComboBox()
        self.color_combo.addItems(list(COLOR_SPACE_LABELS))
        if options.color_space is None:
            self.color_combo.setEnabled(False)
        else:
            self.color_combo.setCurrentIndex(
                _clamp_index(options.color_space, COLOR_SPACE_LABELS)
            )
        form.addRow("Color space", _field_cell(self.color_combo))
        right.addLayout(form)
        right.addStretch(1)

        right.addSpacing(8)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        right.addWidget(separator)

        self.always_show_check = QCheckBox("Always show this texture options")
        self.always_show_check.setChecked(always_show)
        right.addWidget(self.always_show_check)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.cancel_button = QPushButton("Cancel")
        self.replace_button = QPushButton("Replace")
        self.replace_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.replace_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.replace_button)
        right.addLayout(buttons)

        root.addWidget(self.options_panel, stretch=0)

    def always_show_checked(self) -> bool:
        return self.always_show_check.isChecked()

    def collect_options(self) -> TextureReplaceOptions:
        color_space = self._original.color_space
        if self.color_combo.isEnabled():
            color_space = self.color_combo.currentIndex()
        return TextureReplaceOptions(
            target_format=self.format_combo.currentData(),
            has_mip_maps=self.has_mip_maps_check.isChecked(),
            mipmap_count=self._original.mipmap_count,
            filter_mode=self.filter_combo.currentIndex(),
            aniso=self.aniso_spin.value(),
            mip_bias=self.mip_bias_spin.value(),
            wrap_u=self.wrap_u_combo.currentIndex(),
            wrap_v=self.wrap_v_combo.currentIndex(),
            lightmap_format=self.lightmap_spin.value(),
            color_space=color_space,
        )


def pixmap_from_path(path: str) -> QPixmap | None:
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap


def _new_image_caption(file_name: str) -> str:
    safe = file_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'New image  <span style="{_NEW_FILE_STYLE}">[ {safe} ]</span>'
        if safe
        else "New image"
    )


def _field_cell(widget: QWidget) -> QWidget:
    """Column C cell: fixed width, control left-aligned (QSS-safe)."""
    host = QWidget()
    host.setFixedWidth(_FIELD_WIDTH)
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row.addWidget(widget)
    return host


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _clamp_index(value: int, labels: tuple[str, ...]) -> int:
    if not labels:
        return 0
    return _clamp(value, 0, len(labels) - 1)
