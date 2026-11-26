"""Batch command execution panel (one-shot commands, explicit cwd)."""

from __future__ import annotations

import time
from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from ...client import CommandResult
from ..session import ShellSession
from ..widgets import OutputView, mono_font, terminal_metrics


class ExecTab(QWidget):
    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel("工作目录:"))
        self.cwd_label = QLabel(session.cwd or "-")
        self.cwd_label.setObjectName("hint")
        self.cwd_label.setFont(mono_font(11))
        top.addWidget(self.cwd_label, 1)
        top.addWidget(QLabel("超时(秒):"))
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 3600)
        self.timeout.setValue(30)
        self.timeout.setFixedWidth(80)
        top.addWidget(self.timeout)
        top.addWidget(QLabel("输出编码:"))
        self.charset = QComboBox()
        self.charset.addItems(["utf-8", "gbk", "gb18030", "latin-1"])
        top.addWidget(self.charset)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.command = QPlainTextEdit()
        self.command.setFont(mono_font(12))
        self.command.setPlaceholderText("id; whoami; uname -a")
        self.command.setFixedHeight(110)
        splitter.addWidget(self.command)

        self.output = OutputView()
        splitter.addWidget(self.output)
        splitter.setSizes([120, 380])
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.run_button = QPushButton("执行 (Ctrl+Enter)")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run)
        bottom.addWidget(self.run_button)
        clear = QPushButton("清空输出")
        clear.clicked.connect(self.output.clear)
        bottom.addWidget(clear)
        bottom.addStretch(1)
        self.status = QLabel("就绪")
        self.status.setObjectName("hint")
        bottom.addWidget(self.status)
        layout.addLayout(bottom)

    # --------------------------------------------------------------- actions
    def run(self) -> None:
        text = self.command.toPlainText().strip()
        if not text:
            return
        cwd = self.session.cwd
        try:
            self.session.client.set_terminal_size(*terminal_metrics(self.output))
        except Exception:
            pass
        self.status.setText("执行中…")
        self.run_button.setEnabled(False)
        started = time.time()

        def ok(result: CommandResult) -> None:
            self.run_button.setEnabled(True)
            elapsed = time.time() - started
            if isinstance(result, CommandResult):
                self.output.append_text(f"$ {text}", color="#7dd3fc")
                if result.output:
                    charset = self.charset.currentText()
                    self.output.append_ansi_text(result.output, charset)
                self.status.setText(f"完成 | exit={result.exit_code} | {elapsed*1000:.0f} ms")

        def fail(message: str) -> None:
            self.run_button.setEnabled(True)
            self.output.append_text(f"错误: {message}", color="#f87171")
            self.status.setText("失败")

        self.session.run_async(
            lambda: self.session.client.run(text, cwd, self.timeout.value()),
            ok,
            fail,
        )
