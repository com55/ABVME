"""Dialog showing GitHub release notes and update actions."""

from __future__ import annotations

import os
import sys
import threading

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from utilities.app_info import app_version
from utilities.update_install import (
    get_running_executable_path,
    install_dir,
    is_installed_build,
    launch_setup_and_prepare_relaunch,
    update_cache_dir,
)
from utilities.updater import (
    WINDOWS_SETUP_ASSET_NAME,
    UpdateInfo,
    download_file,
    find_windows_setup_asset,
)


class UpdateDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        update: UpdateInfo,
        current_version: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._update = update
        self._current = current_version or update.current_version or app_version()
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)
        self.summary_label = QLabel(f"{self._current} → {update.latest_version}")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.release_name_label = QLabel(update.release_name)
        self.release_name_label.setWordWrap(True)
        self.release_name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.release_name_label.setStyleSheet(
            "font-size: 14pt; font-weight: bold; background-color: transparent;"
        )
        layout.addWidget(self.release_name_label)

        self.body_view = QTextBrowser()
        self.body_view.setReadOnly(True)
        self.body_view.setOpenExternalLinks(True)
        body = update.body.strip()
        if body:
            self.body_view.setMarkdown(body)
        else:
            self.body_view.setPlainText("(No release notes)")
        layout.addWidget(self.body_view, stretch=1)

        buttons = QHBoxLayout()
        self.update_now_button = QPushButton("Update Now")
        self.view_github_button = QPushButton("View on GitHub")
        self._buttons_spacer = QWidget()
        self._buttons_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.progress_bar.setMinimumWidth(120)
        self.progress_bar.setMinimumHeight(22)
        # Global QWidget background matches the dialog, which hides the empty
        # track — only the filled chunk would look like a tiny square.
        self.progress_bar.setStyleSheet(
            "QProgressBar {"
            "  background-color: #2d2d30;"
            "  border: 1px solid #555555;"
            "  border-radius: 4px;"
            "  text-align: center;"
            "  color: #cccccc;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #007acc;"
            "  border-radius: 3px;"
            "}"
        )
        self.progress_bar.setVisible(False)
        self.close_button = QPushButton("Close")
        self.close_button.setDefault(True)
        buttons.addWidget(self.update_now_button)
        buttons.addWidget(self.view_github_button)
        buttons.addWidget(self._buttons_spacer, stretch=1)
        buttons.addWidget(self.progress_bar, stretch=1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.update_now_button.clicked.connect(self._on_update_now)
        self.view_github_button.clicked.connect(self._on_view_github)
        self.close_button.clicked.connect(self.reject)

    def _set_progress_visible(self, visible: bool) -> None:
        self.progress_bar.setVisible(visible)
        self._buttons_spacer.setVisible(not visible)

    def _on_view_github(self) -> None:
        QDesktopServices.openUrl(QUrl(self._update.release_url))

    def _on_update_now(self) -> None:
        if not is_installed_build():
            QDesktopServices.openUrl(QUrl(self._update.release_url))
            return

        self.update_now_button.setEnabled(False)
        self._set_progress_visible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("Downloading update…")
        try:
            asset = find_windows_setup_asset(list(self._update.assets))
            dest = update_cache_dir() / WINDOWS_SETUP_ASSET_NAME

            def _progress(done: int, total: int | None) -> None:
                if total and total > 0:
                    self.progress_bar.setRange(0, total)
                    self.progress_bar.setValue(done)
                    # Keep label short so it fits on the stretched bar.
                    self.progress_bar.setFormat("Downloading… %p%")
                else:
                    self.progress_bar.setFormat(f"Downloading… {done:,} bytes")

            download_file(asset.browser_download_url, dest, progress_cb=_progress)
            target = install_dir() / "ABVME.exe"
            if not target.exists():
                target = get_running_executable_path()
            self.progress_bar.setFormat("Installer started. Closing…")
            QApplication.processEvents()
            launch_setup_and_prepare_relaunch(
                dest,
                target,
                list(sys.argv[1:]),
            )
            # Hide immediately so Setup is not stacked on a live ABVME window,
            # then hard-exit so Inno can replace files without waiting on us.
            # Relaunch is handled by the detached PowerShell watcher.
            for widget in QApplication.topLevelWidgets():
                widget.hide()
            QApplication.processEvents()
            threading.Timer(0.25, lambda: os._exit(0)).start()
        except Exception as exc:
            self._set_progress_visible(False)
            self.update_now_button.setEnabled(True)
            QMessageBox.warning(self, "Update failed", str(exc))
