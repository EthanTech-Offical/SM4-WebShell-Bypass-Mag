"""Interactive virtual terminal (per-command execution with persistent cwd)."""

from __future__ import annotations

import time
from typing import Any

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...client import CommandResult
from ..session import ShellSession
from ..widgets import OutputView, mono_font, terminal_metrics


class _StreamSink(QObject):
    chunk = pyqtSignal(bytes, bool, bool)
    failed = pyqtSignal(str)


class TerminalTab(QWidget):
    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.cwd = session.cwd
        self.history: list[str] = []
        self.history_index = 0
        self.busy = False
        self._cancelled = False
        self._user = "user"
        self._host = "host"
        self._started = False
        self._identity_printed = False
        self._stream_active = False
        self._stream_cancelled = False
        self._stream_handle: str | None = None
        self._stream_sink: _StreamSink | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        self.size_label = QLabel("-")
        self.size_label.setObjectName("hint")
        self.size_label.setFont(mono_font(10))
        bar.addWidget(self.size_label)
        self.cwd_label = QLabel("-")
        self.cwd_label.setObjectName("hint")
        self.cwd_label.setFont(mono_font(11))
        bar.addWidget(QLabel("工作目录:"))
        bar.addWidget(self.cwd_label, 1)
        clear_button = QPushButton("清屏")
        clear_button.clicked.connect(self.clear)
        bar.addWidget(clear_button)
        self.interrupt_button = QPushButton("中断")
        self.interrupt_button.clicked.connect(self.interrupt)
        bar.addWidget(self.interrupt_button)

        self.stream_mode = QCheckBox("流式执行")
        self.stream_mode.setToolTip(
            "开启后长命令走流式模式：输出边跑边回显，但会在目标机留下常驻进程"
            "（nohup/后台），任务结束或点击「中断」才会释放。默认为一次性执行。"
        )
        bar.addWidget(self.stream_mode)
        self.stream_warning = QLabel("⚠ 常驻进程")
        self.stream_warning.setStyleSheet("color:#f59e0b;")
        self.stream_warning.setToolTip("流式模式下目标机进程会持续存在，主机侧可见")
        self.stream_warning.setVisible(False)
        bar.addWidget(self.stream_warning)
        self.stream_mode.toggled.connect(self.stream_warning.setVisible)
        layout.addLayout(bar)

        self.output = OutputView()
        layout.addWidget(self.output, 1)

        input_row = QHBoxLayout()
        self.prompt_label = QLabel("$")
        self.prompt_label.setFont(mono_font(12))
        input_row.addWidget(self.prompt_label)
        self.input = QLineEdit()
        self.input.setFont(mono_font(12))
        self.input.setPlaceholderText("输入命令，回车执行（↑↓ 翻历史，ctrl+c 中断）")
        self.input.returnPressed.connect(self.submit)
        self.input.installEventFilter(self)
        input_row.addWidget(self.input, 1)
        self.run_button = QPushButton("执行")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.submit)
        input_row.addWidget(self.run_button)
        layout.addLayout(input_row)

        session.stateChanged.connect(self._refresh_prompt)

    # ------------------------------------------------------------- lifecycle
    def resizeEvent(self, event):  # noqa: N802 (Qt signature)
        super().resizeEvent(event)
        self._sync_size()

    def _sync_size(self) -> None:
        cols, rows = terminal_metrics(self.output)
        self.size_label.setText(f"{cols}×{rows}")
        try:
            self.session.client.set_terminal_size(cols, rows)
        except Exception:
            pass
        return None

    def begin(self) -> None:
        if self._started:
            return
        self._started = True
        info = self.session.info or {}
        self._user = str(info.get("user") or "user")
        self._host = str(info.get("hostname") or "host")
        self.cwd = self.session.cwd
        self.output.append_text(f"# webshell-mag 虚拟终端 — {self.session.config.url}")
        if info.get("os_name") or info.get("user"):
            self._print_identity(info)
        self.output.append_text("# 说明: 每条命令独立执行，cd 会自动保持工作目录。\n")
        self._sync_size()
        self._refresh_prompt()
        self.input.setFocus()

    def _print_identity(self, info: dict[str, Any]) -> None:
        if self._identity_printed:
            return
        parts = []
        os_name = str(info.get("os_name") or "").strip()
        os_release = str(info.get("os_release") or "").strip()
        if os_name:
            parts.append(f"{os_name} {os_release}".strip())
        user = str(info.get("user") or "").strip()
        host = str(info.get("hostname") or "").strip()
        if user or host:
            parts.append(f"{user}@{host}")
        if not parts:
            return
        self._identity_printed = True
        self.output.append_text("# " + " | ".join(parts))

    def update_identity(self, info: dict[str, Any]) -> None:
        self._user = str(info.get("user") or self._user)
        self._host = str(info.get("hostname") or self._host)
        if self._started:
            self._print_identity(info)
        if not self.cwd:
            self.cwd = str(info.get("cwd") or "")
            self.session.cwd = self.cwd
        self._refresh_prompt()

    def _refresh_prompt(self) -> None:
        self.cwd_label.setText(self.cwd or "-")
        self.prompt_label.setText(self._prompt_text())

    def _prompt_text(self) -> str:
        if str(self.session.info.get("os") or "") == "windows":
            return f"{self.cwd}>"
        return f"{self._user}@{self._host}:{self.cwd}$"

    # ---------------------------------------------------------------- actions
    def clear(self) -> None:
        self.output.clear()

    def interrupt(self) -> None:
        if self._stream_active:
            self._stream_cancelled = True
            handle = self._stream_handle
            if handle:
                self.session.run_async(
                    lambda: self.session.client.stream_stop(handle),
                    lambda _r: None,
                    lambda _e: None,
                )
            self.output.append_text("^C  已请求终止流式任务（kill）", color="#f59e0b")
            self.output.append_text("[stream] 已终止", color="#f59e0b")
            self._finish_stream()
            return
        if not self.busy:
            return
        self._cancelled = True
        self.busy = False
        self.output.append_text("^C  已放弃等待（远端命令可能仍在执行）", color="#f59e0b")
        self._set_input_enabled(True)
        self._refresh_prompt()

    def submit(self) -> None:
        line = self.input.text()
        if self.busy:
            return
        if not line.strip():
            self.input.clear()
            return
        self.history.append(line)
        self.history_index = len(self.history)
        self.input.clear()
        self._execute(line)

    def _execute(self, line: str) -> None:
        self._sync_size()
        if self.stream_mode.isChecked():
            self._execute_stream(line)
            return
        self.busy = True
        self._cancelled = False
        self.output.append_text(f"{self._prompt_text()} {line}", color="#7dd3fc")
        self._set_input_enabled(False)

        def ok(result: CommandResult) -> None:
            if self._cancelled:
                return
            self.busy = False
            self._set_input_enabled(True)
            if isinstance(result, CommandResult):
                if result.output:
                    self.output.append_ansi_text(result.output, self.session.config.charset)
                if result.exit_code:
                    self.output.append_text(f"[exit {result.exit_code}]", color="#f59e0b")
                if result.cwd and result.cwd != self.cwd:
                    self.cwd = result.cwd
                self.session.cwd = self.cwd
            self._refresh_prompt()
            self.input.setFocus()

        def fail(message: str) -> None:
            self.busy = False
            self._set_input_enabled(True)
            self.output.append_text(f"错误: {message}", color="#f87171")
            self._refresh_prompt()

        self.session.run_async(
            lambda: self.session.client.terminal(line, self.cwd),
            ok,
            fail,
        )

    def _set_input_enabled(self, enabled: bool) -> None:
        self.input.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
        if enabled:
            self.input.setFocus()
            self.input.setPlaceholderText("输入命令，回车执行（↑↓ 翻历史）")
        else:
            self.input.setPlaceholderText("执行中…")

    # -------------------------------------------------------------- streaming
    def _execute_stream(self, line: str) -> None:
        self.busy = True
        self._stream_cancelled = False
        self._stream_handle = None
        self._stream_active = True
        self.output.append_text(f"{self._prompt_text()} {line}", color="#7dd3fc")
        self.output.append_text(
            "# [stream] 目标机将保留常驻进程，任务结束或「中断」后释放；默认模式不受影响",
            color="#f59e0b",
        )
        self._set_input_enabled(False)

        sink = _StreamSink()
        sink.chunk.connect(self._on_stream_chunk)
        sink.failed.connect(self._on_stream_failed)
        self._stream_sink = sink

        client = self.session.client
        cwd = self.cwd

        def work() -> None:
            handle: str | None = None
            cursor = 0
            delay = 0.2
            reached_eof = False
            try:
                start = client.stream_start(line, cwd)
                handle = str(start.get("handle", ""))
                self._stream_handle = handle
                while not self._stream_cancelled:
                    part = client.stream_poll(handle, cursor)
                    cursor = part["cursor"]
                    sink.chunk.emit(part["data"], part["running"], part["eof"])
                    if part["eof"]:
                        reached_eof = True
                        break
                    delay = 0.2 if part["data"] else min(1.6, delay * 1.4)
                    time.sleep(delay)
                if self._stream_cancelled and handle:
                    try:
                        client.stream_stop(handle)
                    except Exception:
                        pass
            except Exception as exc:  # noqa: BLE001 - surfaced in the console
                if not self._stream_cancelled:
                    sink.failed.emit(f"{type(exc).__name__}: {exc}")
            finally:
                if not reached_eof:
                    sink.chunk.emit(b"", False, True)

        self.session.run_async(work)

    def _on_stream_chunk(self, data: bytes, running: bool, eof: bool) -> None:
        if data:
            self.output.append_ansi_bytes(data, self.session.config.charset)
        if eof:
            if self._stream_active:
                if self._stream_cancelled:
                    self.output.append_text("[stream] 已终止", color="#f59e0b")
                else:
                    self.output.append_text("[stream] 任务结束", color="#6b7280")
            self._finish_stream()

    def _on_stream_failed(self, message: str) -> None:
        self.output.append_text(f"流式执行失败: {message}", color="#f87171")
        self._finish_stream()

    def _finish_stream(self) -> None:
        if not self._stream_active:
            return
        self._stream_active = False
        self.busy = False
        self._stream_handle = None
        self._stream_sink = None
        self._set_input_enabled(True)
        self._refresh_prompt()

    # ---------------------------------------------------------------- history
    def eventFilter(self, obj, event):  # noqa: N802 (Qt signature)
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            key_event = event  # type: QKeyEvent
            if key_event.key() == Qt.Key.Key_Up:
                if self.history:
                    self.history_index = max(0, self.history_index - 1)
                    self.input.setText(self.history[self.history_index])
                return True
            if key_event.key() == Qt.Key.Key_Down:
                if self.history:
                    self.history_index = min(len(self.history), self.history_index + 1)
                    self.input.setText(
                        self.history[self.history_index] if self.history_index < len(self.history) else ""
                    )
                return True
            if key_event.key() == Qt.Key.Key_C and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if self.input.text():
                    self.input.clear()
                    self.output.append_text("^C", color="#f59e0b")
                else:
                    self.interrupt()
                return True
            if key_event.key() == Qt.Key.Key_L and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.clear()
                return True
        return super().eventFilter(obj, event)
