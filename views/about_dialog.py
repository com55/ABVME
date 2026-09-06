"""About dialog — app name, version, authors, and license."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from utilities.app_info import (
    APP_DESCRIPTION,
    APP_NAME,
    AUTHOR_GITHUB_URL,
    AUTHOR_NAME,
    REPO_URL,
    app_version,
    license_text,
)
from utilities.resource_path import get_resource_str
from utilities.updater import (
    UpdateInfo,
    fetch_latest_release,
    is_newer,
)
from views.update_dialog import UpdateDialog

_ICON_SIZE = 48
_PANEL_BG = "#323232"
_PAGE_BG = "#252526"
_UNITY_DISCLAIMER = (
    "Neither this tool nor its author is affiliated with, sponsored, "
    "or authorized by Unity Technologies or its affiliates."
)
_CHECK_LABEL = "Check for Updates"
_READY_LABEL = "New version ready"


class AboutDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pending_update: UpdateInfo | None = None,
        on_update_found: Callable[[UpdateInfo], None] | None = None,
        on_update_cleared: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._pending_update = pending_update
        self._on_update_found = on_update_found
        self._on_update_cleared = on_update_cleared
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.icon_label.setStyleSheet("background-color: transparent;")
        pixmap = QPixmap(get_resource_str("assets/icon.ico"))
        if not pixmap.isNull():
            self.icon_label.setPixmap(
                pixmap.scaled(
                    _ICON_SIZE,
                    _ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(self.icon_label)

        self.product_title_label = QLabel(APP_NAME)
        self.product_title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.product_title_label.setStyleSheet(
            "font-size: 18pt; font-weight: bold; background-color: transparent;"
        )
        layout.addWidget(self.product_title_label)

        self.product_version_label = QLabel(f"v{app_version()}")
        self.product_version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.product_version_label.setStyleSheet(
            "color: #888888; background-color: transparent;"
        )
        layout.addWidget(self.product_version_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_info_tab(), "Info")
        self.tabs.addTab(self._build_license_tab(), "License")
        layout.addWidget(self.tabs)

        self.close_button = QPushButton("Close")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)

        self._sync_updates_link_label()

    def set_pending_update(self, update: UpdateInfo | None) -> None:
        self._pending_update = update
        self._sync_updates_link_label()

    def _sync_updates_link_label(self) -> None:
        text = _READY_LABEL if self._pending_update is not None else _CHECK_LABEL
        self.updates_link.setText(f'<a href="#updates">{text}</a>')

    def _build_info_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("aboutInfoPage")
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)

        self.description_label = self._page_label(APP_DESCRIPTION)
        self.description_label.setWordWrap(True)
        page_layout.addWidget(self.description_label)

        self.product_name_value = self._panel_label(APP_NAME)
        self.repo_link = self._panel_label(f'<a href="{REPO_URL}">Repository</a>')
        self.repo_link.setOpenExternalLinks(True)
        self.version_value = self._panel_label(app_version())
        self.updates_link = self._panel_label(f'<a href="#updates">{_CHECK_LABEL}</a>')
        self.updates_link.setOpenExternalLinks(False)
        self.updates_link.linkActivated.connect(self._on_updates_clicked)
        self.author_name_label = self._panel_label(AUTHOR_NAME)
        self.author_link = self._panel_label(
            f'<a href="{AUTHOR_GITHUB_URL}">GitHub page</a>'
        )
        self.author_link.setOpenExternalLinks(True)

        page_layout.addWidget(self._page_label("Version", heading=True))
        self.info_grid = self._info_grid()
        self._add_info_row(
            self.info_grid, 0, "Product name:", self.product_name_value, self.repo_link
        )
        self._add_info_row(
            self.info_grid, 1, "Version:", self.version_value, self.updates_link
        )
        page_layout.addWidget(self._info_panel(self.info_grid))

        page_layout.addWidget(self._page_label("Authors", heading=True))
        self.authors_grid = self._info_grid()
        self._add_info_row(
            self.authors_grid, 0, "Author:", self.author_name_label, self.author_link
        )
        page_layout.addWidget(self._info_panel(self.authors_grid))

        self.disclaimer_label = self._page_label(_UNITY_DISCLAIMER)
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setStyleSheet(
            f"font-style: italic; color: #888888; "
            f"background-color: {_PAGE_BG}; border: none;"
        )
        page_layout.addWidget(self.disclaimer_label)
        page_layout.addStretch()
        return page

    def _on_updates_clicked(self, _link: str) -> None:
        if self._pending_update is not None:
            self._open_update_dialog(self._pending_update)
            return

        try:
            latest = fetch_latest_release()
        except Exception:
            QMessageBox.warning(
                self,
                "Check for Updates",
                "Could not check for updates.\nCheck your network connection.",
            )
            return

        current = app_version()
        if not is_newer(latest.latest_version, current):
            self._pending_update = None
            if self._on_update_cleared is not None:
                self._on_update_cleared()
            self._sync_updates_link_label()
            QMessageBox.information(
                self,
                "Check for Updates",
                f"You are up to date (v{current}).",
            )
            return

        info = UpdateInfo(
            current_version=current.lstrip("v"),
            latest_version=latest.latest_version,
            release_name=latest.release_name,
            release_url=latest.release_url,
            tag_name=latest.tag_name,
            body=latest.body,
            assets=latest.assets,
        )
        self._pending_update = info
        if self._on_update_found is not None:
            self._on_update_found(info)
        self._sync_updates_link_label()
        self._open_update_dialog(info)

    def _open_update_dialog(self, update: UpdateInfo) -> None:
        dialog = UpdateDialog(self, update=update, current_version=app_version())
        dialog.exec()

    def _info_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(12)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)
        return grid

    def _info_panel(self, grid: QGridLayout) -> QWidget:
        panel = QWidget()
        panel.setObjectName("aboutInfoPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setStyleSheet(f"background-color: {_PANEL_BG}; border-radius: 4px;")
        panel.setLayout(grid)
        return panel

    def _page_label(self, text: str, heading: bool = False) -> QLabel:
        label = QLabel(text)
        label.setFrameShape(QFrame.Shape.NoFrame)
        if heading:
            label.setStyleSheet(
                f"font-weight: bold; color: #888888; "
                f"background-color: {_PAGE_BG}; border: none;"
            )
        else:
            label.setStyleSheet(f"background-color: {_PAGE_BG}; border: none;")
        return label

    def _panel_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFrameShape(QFrame.Shape.NoFrame)
        label.setStyleSheet(f"background-color: {_PANEL_BG}; border: none;")
        return label

    def _add_info_row(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        value: QLabel,
        link: QLabel | None = None,
    ) -> None:
        grid.addWidget(self._panel_label(label), row, 0)
        grid.addWidget(value, row, 1)
        if link is None:
            return
        link.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(
            link,
            row,
            2,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

    def _build_license_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.license_view = QTextEdit()
        self.license_view.setReadOnly(True)
        self.license_view.setPlainText(license_text())
        page_layout.addWidget(self.license_view)
        return page
