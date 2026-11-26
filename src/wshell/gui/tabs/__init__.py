"""Per-shell workspace: one tab holding terminal / files / exec / info / db / traffic."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from ...config import ShellConfig
from ..session import ShellSession
from ..widgets import mono_font
from .db import DbTab
from .exec import ExecTab
from .files import FilesTab
from .info import InfoTab
from .terminal import TerminalTab
from .traffic import TrafficTab


class ShellWorkspace(QWidget):
    """Everything belonging to one connected shell."""

    statusMessage = pyqtSignal(str)

    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.config: ShellConfig = session.config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.terminal = TerminalTab(session)
        self.files = FilesTab(session)
        self.exec = ExecTab(session)
        self.info = InfoTab(session)
        self.db = DbTab(session)
        self.traffic = TrafficTab(session)

        self.tabs.addTab(self.terminal, "虚拟终端")
        self.tabs.addTab(self.files, "文件管理")
        self.tabs.addTab(self.exec, "命令执行")
        self.tabs.addTab(self.info, "基本信息")
        self.tabs.addTab(self.db, "数据库")
        self.tabs.addTab(self.traffic, "流量")

        self.files.openTerminalRequested.connect(self._open_terminal_at)
        self.info.loaded.connect(self._info_loaded)
        self.tabs.currentChanged.connect(self._tab_changed)

        layout.addWidget(self.tabs, 1)

        self.session.stateChanged.connect(self._state_changed)
        self.session.busyChanged.connect(self._busy_changed)

    def start(self) -> None:
        self.terminal.begin()
        self.info.ensure_loaded()

    def _info_loaded(self, info: dict) -> None:
        self.terminal.update_identity(info)
        if not self.files.current_path and info.get("cwd"):
            self.files.current_path = str(info["cwd"])

    def _tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.files:
            self.files.ensure_loaded()
        elif widget is self.info:
            self.info.ensure_loaded()

    def _open_terminal_at(self, path: str) -> None:
        self.session.cwd = path
        self.terminal.cwd = path
        self.terminal._refresh_prompt()
        self.tabs.setCurrentWidget(self.terminal)

    def _state_changed(self, connected: bool) -> None:
        self.statusMessage.emit("已连接" if connected else "已断开")

    def _busy_changed(self, count: int) -> None:
        if count > 0:
            self.statusMessage.emit(f"请求中… ({count})")
        else:
            self.statusMessage.emit("就绪")
