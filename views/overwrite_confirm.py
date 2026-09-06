"""Confirm overwriting existing files when saving or exporting to a folder."""

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_overwrite_existing(parent: QWidget | None, names: list[str]) -> bool:
    if not names:
        return True
    shown = names[:10]
    extra = len(names) - 10
    listing = "\n".join(f"\u2022 {name}" for name in shown)
    if extra > 0:
        listing += f"\n... and {extra} more"
    reply = QMessageBox.question(
        parent,
        "Files already exist",
        (
            "These files already exist in the destination folder:\n\n"
            f"{listing}\n\nOverwrite them?"
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes
