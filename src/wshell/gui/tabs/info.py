"""Basic information panel."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...client import ShellError
from ..session import ShellSession
from ..widgets import human_size, mono_font


FIELD_LABELS = {
    "os": "系统类型",
    "os_name": "内核",
    "os_release": "内核版本",
    "arch": "架构",
    "hostname": "主机名",
    "ip": "服务器 IP",
    "user": "运行用户",
    "cwd": "当前目录",
    "shell": "Shell",
    "php_version": "PHP 版本",
    "sapi": "运行方式",
    "sys_temp": "临时目录",
    "server_software": "Web 服务器",
    "document_root": "站点根目录",
    "script": "Shell 路径",
    "open_basedir": "open_basedir",
    "safe_mode": "safe_mode",
    "file_uploads": "文件上传",
    "upload_max_filesize": "上传上限",
    "max_execution_time": "脚本超时",
    "memory_limit": "内存限制",
    "disk_free": "剩余磁盘",
    "disk_total": "磁盘总量",
    "whoami": "whoami",
    "uname": "uname -a",
    "time": "服务器时间",
}


class InfoTab(QWidget):
    loaded = pyqtSignal(dict)

    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("服务器信息")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.reload)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["项目", "值"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setFont(mono_font(11))
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 150)
        layout.addWidget(self.tree, 1)

        self.status = QLabel("等待加载…")
        self.status.setObjectName("hint")
        layout.addWidget(self.status)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self.status.setText("正在获取信息…")
        self.refresh_button.setEnabled(False)

        def ok(data: dict[str, Any]) -> None:
            self._loaded = True
            self.refresh_button.setEnabled(True)
            self._fill(data)
            self.status.setText("已更新")
            self.loaded.emit(data)

        def fail(message: str) -> None:
            self.refresh_button.setEnabled(True)
            self.status.setText(f"获取失败: {message}")

        self.session.run_async(self.session.client.info, ok, fail)

    def _fill(self, data: dict[str, Any]) -> None:
        self.tree.clear()
        if not isinstance(data, dict):
            return
        for key, label in FIELD_LABELS.items():
            if key not in data:
                continue
            value = data.get(key)
            if key in {"disk_free", "disk_total"} and isinstance(value, (int, float)):
                text = human_size(value)
            elif isinstance(value, bool):
                text = "是" if value else "否"
            elif isinstance(value, list):
                text = ", ".join(str(v) for v in value) if value else "（无）"
            elif isinstance(value, dict):
                text = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in value.items())
            elif key == "time" and isinstance(value, (int, float)):
                import time

                text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
            else:
                text = str(value)
            item = QTreeWidgetItem([label, text])
            item.setToolTip(1, text)
            self.tree.addTopLevelItem(item)

        functions = data.get("functions") or {}
        if functions:
            node = QTreeWidgetItem(["命令执行函数", ""])
            for name, enabled in functions.items():
                node.addChild(QTreeWidgetItem([name, "可用" if enabled else "已禁用"]))
            self.tree.addTopLevelItem(node)
            node.setExpanded(True)

        extensions = data.get("extensions") or []
        if extensions:
            item = QTreeWidgetItem(["PHP 扩展", ", ".join(extensions)])
            item.setToolTip(1, ", ".join(extensions))
            self.tree.addTopLevelItem(item)

        disabled = data.get("disable_functions") or []
        if disabled:
            item = QTreeWidgetItem(["disable_functions", ", ".join(disabled)])
            item.setToolTip(1, ", ".join(disabled))
            self.tree.addTopLevelItem(item)

        self.tree.resizeColumnToContents(0)
