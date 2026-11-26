"""Main window: shell list, connection management, workspaces."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QInputDialog,
    QLineEdit,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import secure
from ..config import ShellConfig, ShellStore
from .dialogs.generate_dialog import GenerateDialog
from .dialogs.shell_dialog import ShellDialog
from .session import ShellSession
from .tabs import ShellWorkspace
from .widgets import mono_font


def dot_icon(color: str, size: int = 12) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pixmap)


ICON_IDLE = None
ICON_ONLINE = None
ICON_OFFLINE = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        global ICON_IDLE, ICON_ONLINE, ICON_OFFLINE
        ICON_IDLE = dot_icon("#6b7280")
        ICON_ONLINE = dot_icon("#22c55e")
        ICON_OFFLINE = dot_icon("#ef4444")

        self.setWindowTitle("webshell-mag — SM4 加密 WebShell 管理端")
        self.resize(1280, 820)

        import os as _os

        self.passphrase = _os.environ.get("WEBSHELL_MAG_PASSPHRASE") or None
        self.store = ShellStore(passphrase=self.passphrase)
        self.shells: dict[str, ShellConfig] = {}
        self.sessions: dict[str, ShellSession] = {}
        self.workspaces: dict[str, ShellWorkspace] = {}
        self.items: dict[str, QTreeWidgetItem] = {}

        self._build_ui()
        self._build_actions()
        self._load_shells()

    # ------------------------------------------------------------------- ui
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["会话", "地址"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 170)
        self.tree.itemDoubleClicked.connect(self._tree_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        left_layout.addWidget(self.tree, 1)

        self.hint_label = QLabel("双击会话即可连接\n右键查看更多操作")
        self.hint_label.setObjectName("hint")
        left_layout.addWidget(self.hint_label)

        splitter.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        splitter.addWidget(self.tabs)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 980])
        self.setCentralWidget(splitter)

        status = QStatusBar()
        self.status_label = QLabel("就绪")
        status.addWidget(self.status_label, 1)
        self.latency_label = QLabel("")
        self.latency_label.setFont(mono_font(10))
        status.addPermanentWidget(self.latency_label)
        self.setStatusBar(status)

    def _build_actions(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        act_generate = QAction("生成 Shell", self)
        act_generate.setShortcut(QKeySequence("Ctrl+G"))
        act_generate.triggered.connect(self.open_generator)
        toolbar.addAction(act_generate)

        toolbar.addSeparator()

        act_add = QAction("添加会话", self)
        act_add.setShortcut(QKeySequence.StandardKey.New)
        act_add.triggered.connect(self.add_shell)
        toolbar.addAction(act_add)

        act_edit = QAction("编辑", self)
        act_edit.triggered.connect(lambda: self.edit_shell(self._selected_config()))
        toolbar.addAction(act_edit)

        act_delete = QAction("删除", self)
        act_delete.triggered.connect(lambda: self.delete_shell(self._selected_config()))
        toolbar.addAction(act_delete)

        toolbar.addSeparator()

        act_connect = QAction("连接", self)
        act_connect.setShortcut(QKeySequence("Ctrl+Enter"))
        act_connect.triggered.connect(self._connect_selected)
        toolbar.addAction(act_connect)

        act_disconnect = QAction("断开", self)
        act_disconnect.triggered.connect(self._disconnect_selected)
        toolbar.addAction(act_disconnect)

        menu_file = self.menuBar().addMenu("文件")
        menu_file.addAction(act_generate)
        menu_file.addAction(act_add)
        encrypt = QAction("启用/更换主密码…", self)
        encrypt.triggered.connect(self._set_passphrase)
        menu_file.addAction(encrypt)
        decrypt = QAction("取消加密…", self)
        decrypt.triggered.connect(self._clear_passphrase)
        menu_file.addAction(decrypt)
        menu_file.addSeparator()

        export = QAction("导出会话配置…", self)
        export.triggered.connect(self.export_config)
        menu_file.addAction(export)
        import_action = QAction("导入会话配置…", self)
        import_action.triggered.connect(self.import_config)
        menu_file.addAction(import_action)
        menu_file.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu_file.addAction(quit_action)

        menu_session = self.menuBar().addMenu("会话")
        menu_session.addAction(act_connect)
        menu_session.addAction(act_disconnect)
        menu_session.addAction(act_edit)
        menu_session.addAction(act_delete)

        menu_help = self.menuBar().addMenu("帮助")
        about = QAction("关于", self)
        about.triggered.connect(self._about)
        menu_help.addAction(about)

    # --------------------------------------------------------------- configs
    def _load_shells(self) -> None:
        try:
            shells = self.store.load()
        except secure.StoreLocked:
            if not self._unlock_store():
                QMessageBox.information(self, "会话库已加密", "未解锁，本次以空会话库启动。")
                shells = []
            else:
                shells = self.store.load()
        except secure.StoreError as exc:
            QMessageBox.warning(self, "会话库读取失败", str(exc))
            shells = []
        for config in shells:
            self.shells[config.id] = config
        self._rebuild_tree()
        if self.store.is_encrypted():
            self.status_label.setText("会话库已加密（主密码已解锁）")

    def _unlock_store(self) -> bool:
        while True:
            pwd, ok = QInputDialog.getText(
                self, "解锁会话库", "主密码：", QLineEdit.EchoMode.Password
            )
            if not ok:
                return False
            try:
                self.store.set_passphrase(pwd)
                self.store.load()
                return True
            except secure.StoreLocked:
                QMessageBox.warning(self, "密码错误", "主密码不正确，请重试。")

    def _set_passphrase(self) -> None:
        first, ok = QInputDialog.getText(
            self, "启用/更换主密码", "新主密码（留空取消）：", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if not first.strip():
            return
        second, ok = QInputDialog.getText(
            self, "确认主密码", "再次输入：", QLineEdit.EchoMode.Password
        )
        if not ok or second != first:
            QMessageBox.warning(self, "不一致", "两次输入的密码不一致。")
            return
        self.store.set_passphrase(first)
        self.passphrase = first
        self._save_shells()
        self.status_label.setText("会话库已启用加密（SM4-CBC + HMAC-SHA256, PBKDF2）")

    def _clear_passphrase(self) -> None:
        if not self.store.is_encrypted():
            QMessageBox.information(self, "提示", "当前会话库未加密。")
            return
        reply = QMessageBox.question(
            self, "取消加密", "将把会话库改回明文存储，继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.store.set_passphrase(None)
        self.passphrase = None
        self._save_shells()
        self.status_label.setText("会话库已改为明文存储")

    def _save_shells(self) -> None:
        self.store.save(list(self.shells.values()))

    def _rebuild_tree(self) -> None:
        self.tree.clear()
        self.items.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for config in sorted(self.shells.values(), key=lambda c: (c.group, c.name)):
            group_name = config.group or "default"
            if group_name not in groups:
                node = QTreeWidgetItem([group_name, ""])
                node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                font = node.font(0)
                font.setBold(True)
                node.setFont(0, font)
                node.setForeground(0, QColor("#8f96a3"))
                self.tree.addTopLevelItem(node)
                node.setExpanded(True)
                groups[group_name] = node
            item = QTreeWidgetItem([config.name, config.url])
            item.setData(0, Qt.ItemDataRole.UserRole, config.id)
            item.setIcon(0, ICON_ONLINE if config.id in self.sessions else ICON_IDLE)
            item.setToolTip(0, f"{config.name}\n{config.url}\nKey: {config.key[:8]}…\n备注: {config.remark}")
            item.setToolTip(1, config.url)
            groups[group_name].addChild(item)
            self.items[config.id] = item
        for group_index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(group_index).setExpanded(True)

    def _selected_config(self) -> ShellConfig | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        config_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        return self.shells.get(config_id) if config_id else None

    # ---------------------------------------------------------------- actions
    def open_generator(self) -> None:
        dialog = GenerateDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created is not None:
            config = dialog.created
            self.shells[config.id] = config
            self._save_shells()
            self._rebuild_tree()
            self.status_label.setText(f"已生成会话 {config.name}，填写 URL 后即可连接")
            self.edit_shell(config)

    def add_shell(self) -> None:
        dialog = ShellDialog(None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.result_config()
            self.shells[config.id] = config
            self._save_shells()
            self._rebuild_tree()
            self.status_label.setText(f"已添加会话 {config.name}")

    def edit_shell(self, config: ShellConfig | None) -> None:
        if config is None:
            QMessageBox.information(self, "提示", "请先在左侧选择一个会话。")
            return
        dialog = ShellDialog(config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = dialog.result_config()
            self.shells[updated.id] = updated
            self._save_shells()
            self._rebuild_tree()
            if updated.id in self.sessions:
                self.sessions[updated.id].config = updated
                self.sessions[updated.id].client.config = updated
            self.status_label.setText(f"已更新会话 {updated.name}")

    def delete_shell(self, config: ShellConfig | None) -> None:
        if config is None:
            return
        reply = QMessageBox.question(
            self,
            "删除会话",
            f"确定删除会话 “{config.name}” ？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._disconnect(config.id)
        self.shells.pop(config.id, None)
        self._save_shells()
        self._rebuild_tree()

    def _connect_selected(self) -> None:
        config = self._selected_config()
        if config is not None:
            self.connect_shell(config)

    def connect_shell(self, config: ShellConfig) -> None:
        if config.id in self.sessions:
            workspace = self.workspaces.get(config.id)
            if workspace is not None:
                self.tabs.setCurrentWidget(workspace)
            return
        session = ShellSession(config)
        workspace = ShellWorkspace(session)
        workspace.statusMessage.connect(self.status_label.setText)
        session.traces.connect(lambda *_: self._update_latency(config.id))
        index = self.tabs.addTab(workspace, config.name)
        self.tabs.setTabToolTip(index, config.url)
        self.tabs.setCurrentIndex(index)
        self.sessions[config.id] = session
        self.workspaces[config.id] = workspace
        self._set_item_state(config.id, "connecting")
        self.status_label.setText(f"连接 {config.url} …")

        def ok(info: dict[str, Any]) -> None:
            self._set_item_state(config.id, "online")
            self.status_label.setText(
                f"已连接 {config.name} | {info.get('os_name', '')} {info.get('os_release', '')} "
                f"| {info.get('user', '')}"
            )
            workspace.start()

        def fail(message: str) -> None:
            self._set_item_state(config.id, "offline")
            self.status_label.setText(f"连接失败: {message}")
            QMessageBox.warning(self, "连接失败", message)

        session.connect_shell(ok, fail)

    def _disconnect(self, config_id: str) -> None:
        session = self.sessions.pop(config_id, None)
        if session is not None:
            session.shutdown()
        workspace = self.workspaces.pop(config_id, None)
        if workspace is not None:
            index = self.tabs.indexOf(workspace)
            if index >= 0:
                self.tabs.removeTab(index)
            workspace.deleteLater()
        self._set_item_state(config_id, "idle")

    def _disconnect_selected(self) -> None:
        config = self._selected_config()
        if config is not None:
            self._disconnect(config.id)
            self.status_label.setText(f"已断开 {config.name}")

    def close_tab(self, index: int) -> None:
        workspace = self.tabs.widget(index)
        for config_id, candidate in list(self.workspaces.items()):
            if candidate is workspace:
                self._disconnect(config_id)
                return
        self.tabs.removeTab(index)

    def _set_item_state(self, config_id: str, state: str) -> None:
        item = self.items.get(config_id)
        if item is None:
            return
        icon = {"online": ICON_ONLINE, "offline": ICON_OFFLINE}.get(state, ICON_IDLE)
        item.setIcon(0, icon)

    def _update_latency(self, config_id: str) -> None:
        workspace = self.workspaces.get(config_id)
        if workspace is not None and self.tabs.currentWidget() is workspace:
            self.latency_label.setText(f"{workspace.session.latency_ms:.0f} ms")

    def _tab_changed(self, index: int) -> None:
        workspace = self.tabs.widget(index)
        if isinstance(workspace, ShellWorkspace):
            self.latency_label.setText(f"{workspace.session.latency_ms:.0f} ms")
        else:
            self.latency_label.setText("")

    # ----------------------------------------------------------------- events
    def _tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        config_id = item.data(0, Qt.ItemDataRole.UserRole)
        config = self.shells.get(config_id) if config_id else None
        if config is not None:
            self.connect_shell(config)

    def _tree_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is not None:
            self.tree.setCurrentItem(item)
        config = self._selected_config()
        menu = QMenu(self)
        if config is not None:
            menu.addAction("连接", lambda: self.connect_shell(config))
            menu.addAction("断开", lambda: self._disconnect(config.id))
            menu.addSeparator()
            menu.addAction("编辑", lambda: self.edit_shell(config))
            menu.addAction("复制 URL", lambda: QMessageBox.information(self, "URL", config.url))
            menu.addAction("删除", lambda: self.delete_shell(config))
            menu.addSeparator()
        menu.addAction("添加会话", self.add_shell)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def export_config(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, "导出会话", "shells.json", "JSON (*.json)")
        if not target:
            return
        import json
        from pathlib import Path

        Path(target).write_text(
            json.dumps({"version": 1, "shells": [s.to_dict() for s in self.shells.values()]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.status_label.setText(f"已导出到 {target}")

    def import_config(self) -> None:
        import json
        from pathlib import Path

        source, _ = QFileDialog.getOpenFileName(self, "导入会话", "", "JSON (*.json)")
        if not source:
            return
        try:
            raw = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        added = 0
        for item in raw.get("shells", []):
            try:
                config = ShellConfig.from_dict(item)
            except (TypeError, ValueError):
                continue
            if config.id in self.shells:
                config.id = ShellConfig().id
            self.shells[config.id] = config
            added += 1
        self._save_shells()
        self._rebuild_tree()
        self.status_label.setText(f"已导入 {added} 个会话")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "关于 webshell-mag",
            "webshell-mag 1.6.3\n\n"
            "参考 Behinder / Godzilla / AntSword 的 SM4 WebShell 管理端。\n"
            "v2：HKDF-SHA256 派生密钥 → SM4-CBC + HMAC-SHA256（encrypt-then-MAC）\n"
            "     + 随机 IV / 时间窗 / Nonce 防重放 / 6 种载体 / 填充与节流\n"
            "传输：requests 或 curl_cffi（浏览器 TLS/JA3 指纹，可选）\n"
            "载荷：PHP（v1 / v2，按次随机化标识/参数）\n"
            "终端：一次性/流式，ANSI/CJK/COLUMNS-LINES\n"
            
            "v1：SM4-CBC + Base64（兼容旧 Shell）\n"
            "功能：虚拟终端、文件管理、上传下载、在线编辑、命令执行、数据库、流量审计。\n\n"
            "仅用于自有资产与授权测试环境。",
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        for config_id in list(self.sessions):
            self._disconnect(config_id)
        self._save_shells()
        super().closeEvent(event)
