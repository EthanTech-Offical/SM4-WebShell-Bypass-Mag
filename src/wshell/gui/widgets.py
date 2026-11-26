"""Shared Qt widgets and formatting helpers."""

from __future__ import annotations

import time
from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QStyle,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ..encoding import decode_bytes
from .ansi import DEFAULT_FG, AnsiParser, Style

MONO_FAMILIES = (
    "JetBrains Mono",
    "SF Mono",
    "Menlo",
    "Cascadia Mono",
    "Consolas",
    "DejaVu Sans Mono",
    "Courier New",
)


def mono_font(size: int = 12) -> QFont:
    available = set(QFontDatabase.families())
    for name in MONO_FAMILIES:
        if name in available:
            font = QFont(name, size)
            font.setStyleHint(QFont.StyleHint.Monospace)
            return font
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size)
    return font


def terminal_metrics(view: QPlainTextEdit) -> tuple[int, int]:
    """Visible columns/rows of a monospace view (ANSI-aware layout).

    Uses the width of 'M' rather than a fixed 8px so the numbers match what the
    widget actually draws; CJK glyphs are double width, which the terminal
    itself handles — here we only care about the grid we can fit.
    """
    metrics = QFontMetrics(view.font())
    char_width = max(1, metrics.horizontalAdvance("M"))
    line_height = max(1, metrics.lineSpacing())
    viewport = view.viewport()
    cols = max(20, min(500, viewport.width() // char_width))
    rows = max(5, min(200, viewport.height() // line_height))
    return cols, rows


def human_size(size: int | float | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def human_time(ts: int | float | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    if not ts:
        return "-"
    try:
        return time.strftime(fmt, time.localtime(int(ts)))
    except (OverflowError, OSError, ValueError):
        return "-"


def mode_to_rwx(mode: int) -> str:
    if not mode:
        return "---------"
    parts = []
    for shift in (6, 3, 0):
        bits = (mode >> shift) & 0b111
        parts.append("r" if bits & 4 else "-")
        parts.append("w" if bits & 2 else "-")
        parts.append("x" if bits & 1 else "-")
    return "".join(parts)


class OutputView(QPlainTextEdit):
    """Read-only monospace console with a bounded scrollback.

    ANSI output is rendered with ``QTextCharFormat`` runs; a line without a
    trailing newline stays "open" so ``\r`` progress bars can rewrite it.
    """

    def __init__(self, parent: QWidget | None = None, max_blocks: int = 20000) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(mono_font(12))
        self.setMaximumBlockCount(max_blocks)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setUndoRedoEnabled(False)
        self.setPlaceholderText("等待输出…")
        self._ansi = AnsiParser()
        self._line_open = False
        self._line_pos = 0

    # ------------------------------------------------------------- ANSI render
    def append_ansi_text(self, text: str, charset: str = "utf-8") -> None:
        if not text:
            return
        # fast path: plain text with no control characters, complete lines only
        if (
            "\x1b" not in text
            and "\r" not in text
            and "\b" not in text
            and not self._line_open
            and text.endswith("\n")
        ):
            for line in text[:-1].split("\n"):
                self.appendPlainText(line)
            return
        lines, partial = self._ansi.feed(text)
        for runs in lines:
            self._append_runs(runs, finalize=True)
        if partial is not None:
            self._append_runs(partial, finalize=False)

    def append_ansi_bytes(self, data: bytes, charset: str = "utf-8") -> None:
        if not data:
            return
        self.append_ansi_text(decode_bytes(data, charset or "utf-8"))

    def close_ansi_line(self) -> None:
        """Stop treating the last block as a rewritable line."""
        self._line_open = False

    def _ensure_line(self) -> None:
        if self._line_open:
            return
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.document().characterCount() > 1:
            cursor.insertBlock()
        self._line_pos = cursor.position()
        self._line_open = True

    def _append_runs(self, runs, finalize: bool) -> None:
        self._ensure_line()
        cursor = QTextCursor(self.document())
        cursor.setPosition(self._line_pos)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.setPosition(self._line_pos)
        for text, style in runs:
            if text:
                cursor.insertText(text, self._char_format(style))
        self.setTextCursor(cursor)
        if finalize:
            self._line_open = False
            self.ensureCursorVisible()

    @staticmethod
    def _char_format(style: Style) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fg = style.fg or DEFAULT_FG
        bg = style.bg
        if style.inverse:
            fg, bg = (style.bg or "#1a1d23"), (style.fg or DEFAULT_FG)
        color = QColor(fg)
        if style.dim:
            color.setAlpha(170)
        fmt.setForeground(color)
        if bg:
            fmt.setBackground(QColor(bg))
        if style.bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if style.italic:
            fmt.setFontItalic(True)
        if style.underline:
            fmt.setFontUnderline(True)
        return fmt

    def append_text(self, text: str, color: str | None = None) -> None:
        if text is None:
            return
        self.close_ansi_line()
        if color:
            self.appendHtml(
                f'<pre style="margin:0;color:{color};white-space:pre-wrap;">'
                f"{escape(text)}</pre>"
            )
            return
        self.appendPlainText(text.rstrip("\n") if text.endswith("\n") else text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def append_bytes(self, data: bytes, charset: str = "utf-8") -> None:
        self.append_ansi_bytes(data, charset)


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace(" ", "&nbsp;")
        .replace("\n", "<br>")
    )


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionTitle")


class Separator(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setObjectName("separator")


class PathBar(QWidget):
    """Address bar + up/refresh buttons."""

    submitted = pyqtSignal(str)
    upRequested = pyqtSignal()
    refreshRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.up_button = QPushButton()
        self.up_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        )
        self.up_button.setFixedWidth(32)
        self.up_button.setToolTip("上级目录")
        self.up_button.clicked.connect(self.upRequested.emit)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("/var/www")
        self.edit.setFont(mono_font(12))
        self.edit.returnPressed.connect(self._submit)

        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.refresh_button.setFixedWidth(32)
        self.refresh_button.setToolTip("刷新")
        self.refresh_button.clicked.connect(self.refreshRequested.emit)

        layout.addWidget(self.up_button)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.refresh_button)

    def _submit(self) -> None:
        self.submitted.emit(self.edit.text().strip())

    def set_path(self, path: str) -> None:
        self.edit.setText(path)

    def path(self) -> str:
        return self.edit.text().strip()


class ToolbarRow(QWidget):
    """A horizontal row of buttons that keeps alignment."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def add_button(self, text: str, slot, tooltip: str = "") -> QPushButton:
        button = QPushButton(text)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(slot)
        self.layout_.addWidget(button)
        return button

    def add_widget(self, widget: QWidget) -> QWidget:
        self.layout_.addWidget(widget)
        return widget

    def add_stretch(self) -> None:
        self.layout_.addStretch(1)


def set_dark_palette_widget(widget: QWidget) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
