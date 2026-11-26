"""Plain text / code editor dialog for remote files."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets import human_size, mono_font


class EditorDialog(QDialog):
    def __init__(self, path: str, text: str, charset: str = "utf-8", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"编辑 — {path}")
        self.resize(920, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        label = QLabel(path)
        label.setFont(mono_font(11))
        label.setObjectName("hint")
        header.addWidget(label, 1)
        self.wrap = QCheckBox("自动换行")
        self.wrap.toggled.connect(self._toggle_wrap)
        header.addWidget(self.wrap)
        self.size_label = QLabel(human_size(len(text.encode(charset or "utf-8", "replace"))))
        self.size_label.setObjectName("hint")
        header.addWidget(self.size_label)
        layout.addLayout(header)

        self.editor = QPlainTextEdit()
        self.editor.setFont(mono_font(12))
        self.editor.setPlainText(text)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabChangesFocus(False)
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.accept)
        layout.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_wrap(self, enabled: bool) -> None:
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def text(self) -> str:
        return self.editor.toPlainText()
