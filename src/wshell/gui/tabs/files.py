"""File manager: browse, upload, download, edit, chmod, zip, search."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QStyle

from ...client import DirListing, RemoteEntry, ShellError
from ...config import config_home
from ..dialogs.editor import EditorDialog
from ..session import ShellSession
from ..widgets import PathBar, human_size, human_time, mode_to_rwx, mono_font

COLUMNS = ["名称", "大小", "权限", "所有者", "修改时间", "类型"]


class _Progress(QObject):
    changed = pyqtSignal(int, int)
    note = pyqtSignal(str)


class FilesTab(QWidget):
    openTerminalRequested = pyqtSignal(str)

    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.current_path = ""  # resolved lazily from the session on first load
        self.entries: list[RemoteEntry] = []
        self._listing: DirListing | None = None
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.path_bar = PathBar()
        self.path_bar.submitted.connect(self.open_dir)
        self.path_bar.upRequested.connect(self.go_up)
        self.path_bar.refreshRequested.connect(self.refresh)
        layout.addWidget(self.path_bar)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.upload_button = self._tool(toolbar, "上传", self.upload_files, "上传本地文件到当前目录（支持拖拽）")
        self.upload_dir_button = self._tool(toolbar, "上传目录", self.upload_directory, "递归上传整个目录（支持拖拽）")
        self.download_button = self._tool(toolbar, "下载", self.download_selected, "下载选中文件")
        self.edit_button = self._tool(toolbar, "编辑", self.edit_selected, "在线编辑文本文件")
        self.refresh_button = self._tool(toolbar, "刷新", self.refresh, "刷新目录")
        self.new_file_button = self._tool(toolbar, "新建文件", self.create_file)
        self.new_dir_button = self._tool(toolbar, "新建目录", self.create_dir)
        self.rename_button = self._tool(toolbar, "重命名", self.rename_selected)
        self.chmod_button = self._tool(toolbar, "权限", self.chmod_selected)
        self.zip_button = self._tool(toolbar, "压缩", self.zip_selected)
        self.unzip_button = self._tool(toolbar, "解压", self.unzip_selected)
        self.search_button = self._tool(toolbar, "搜索", self.search)
        self.delete_button = self._tool(toolbar, "删除", self.delete_selected, "删除选中项（目录递归）")
        self.delete_button.setObjectName("danger")
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_row)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setFont(mono_font(11))
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.status = QLabel("未连接")
        self.status.setObjectName("hint")
        footer.addWidget(self.status, 1)
        self.path_label = QLabel("")
        self.path_label.setObjectName("hint")
        self.path_label.setFont(mono_font(10))
        footer.addWidget(self.path_label)
        layout.addLayout(footer)

        self._selection_changed()

        self.setAcceptDrops(True)
        self.table.setAcceptDrops(False)
        self.table.viewport().setAcceptDrops(False)

    # ------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event):  # noqa: N802 (Qt signature)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.start_uploads(paths)
        else:
            super().dropEvent(event)

    def start_uploads(self, paths: list[str]) -> None:
        """Files go through the per-file queue, directories through upload_tree."""
        if not self.current_path:
            self.current_path = self.session.cwd
        files = [p for p in paths if Path(p).is_file()]
        dirs = [p for p in paths if Path(p).is_dir()]
        if dirs:
            self._upload_dir_queue(dirs)
        elif files:
            self._upload_queue(files)

    # ---------------------------------------------------------------- helpers
    def _tool(self, layout: QHBoxLayout, text: str, slot: Callable, tip: str = "") -> QPushButton:
        button = QPushButton(text)
        if tip:
            button.setToolTip(tip)
        button.clicked.connect(lambda: slot())
        layout.addWidget(button)
        return button

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    def _selection_changed(self) -> None:
        rows = self._selected_entries()
        for button in (
            self.download_button,
            self.edit_button,
            self.rename_button,
            self.delete_button,
            self.chmod_button,
            self.zip_button,
        ):
            button.setEnabled(bool(rows) and not self._busy)
        self.unzip_button.setEnabled(
            len(rows) == 1 and rows[0].name.lower().endswith((".zip", ".tar", ".gz", ".tgz")) and not self._busy
        )
        if rows:
            self._set_status(f"已选择 {len(rows)} 项 | 总计 {human_size(sum(r.size for r in rows))}")

    def _selected_entries(self) -> list[RemoteEntry]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        result = []
        for row in rows:
            item = self.table.item(row, 0)
            if item is None:
                continue
            entry = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(entry, RemoteEntry):
                result.append(entry)
        return result

    def _fail(self, message: str) -> None:
        self._busy = False
        self._selection_changed()
        self._set_status(f"失败: {message}")
        QMessageBox.warning(self, "操作失败", message)

    # -------------------------------------------------------------- navigation
    def ensure_loaded(self) -> None:
        if not self.entries:
            if not self.current_path:
                self.current_path = self.session.cwd or "/"
            self.refresh()

    def refresh(self) -> None:
        self.open_dir(self.current_path)

    def open_dir(self, path: str) -> None:
        if self._busy:
            return
        path = (path or "").strip() or self.session.cwd or self.current_path or "/"
        self._busy = True
        self._set_status(f"读取 {path} …")
        self.upload_button.setEnabled(False)

        def ok(listing: DirListing) -> None:
            self._busy = False
            self.upload_button.setEnabled(True)
            self._listing = listing
            self.current_path = listing.path
            self.entries = listing.entries
            self.path_bar.set_path(listing.path)
            self.session.cwd = listing.path
            self._render(listing)
            free = human_size(listing.free) if listing.free else "-"
            self._set_status(f"{len(listing.entries)} 项 | 剩余空间 {free}")
            self._selection_changed()

        def fail(message: str) -> None:
            self._busy = False
            self.upload_button.setEnabled(True)
            self._set_status(f"读取失败: {message}")
            QMessageBox.warning(self, "无法打开目录", f"{path}\n{message}")

        self.session.run_async(lambda: self.session.client.ls(path), ok, fail)

    def go_up(self) -> None:
        parent = self._listing.parent if self._listing else os.path.dirname(self.current_path)
        self.open_dir(parent or self.current_path)

    def _render(self, listing: DirListing) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(listing.entries))
        style = self.style()
        for row, entry in enumerate(listing.entries):
            name_item = QTableWidgetItem(entry.name)
            icon = QStyle.StandardPixmap.SP_DirIcon if entry.type == "dir" else QStyle.StandardPixmap.SP_FileIcon
            if entry.type == "link":
                icon = QStyle.StandardPixmap.SP_FileLinkIcon
            name_item.setIcon(style.standardIcon(icon))
            name_item.setData(Qt.ItemDataRole.UserRole, entry)
            name_item.setToolTip(entry.path + (f" -> {entry.target}" if entry.target else ""))
            if not entry.writable:
                name_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 0, name_item)

            size_text = "-" if entry.type == "dir" else human_size(entry.size)
            values = [
                size_text,
                entry.perm,
                entry.owner,
                human_time(entry.mtime),
                {"dir": "目录", "file": "文件", "link": "链接"}.get(entry.type, entry.type),
            ]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                if col == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
        self.table.setUpdatesEnabled(True)

    def _open_row(self, index) -> None:
        item = self.table.item(index.row(), 0)
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, RemoteEntry):
            return
        if entry.type == "dir":
            self.open_dir(entry.path)
        else:
            self.edit_path(entry.path)

    # ----------------------------------------------------------- context/menu
    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_open_terminal = QAction("在此打开终端", self)
        act_open_terminal.triggered.connect(lambda: self.openTerminalRequested.emit(self.current_path))
        menu.addAction(act_open_terminal)
        menu.addSeparator()
        entries = self._selected_entries()
        if entries and entries[0].type != "dir":
            act_edit = menu.addAction("编辑")
            act_edit.triggered.connect(self.edit_selected)
            act_download = menu.addAction("下载")
            act_download.triggered.connect(self.download_selected)
        act_upload = menu.addAction("上传文件到此处")
        act_upload.triggered.connect(self.upload_files)
        act_upload_dir = menu.addAction("上传目录到此处")
        act_upload_dir.triggered.connect(self.upload_directory)
        menu.addSeparator()
        act_mkdir = menu.addAction("新建目录")
        act_mkdir.triggered.connect(self.create_dir)
        act_touch = menu.addAction("新建文件")
        act_touch.triggered.connect(self.create_file)
        if entries:
            menu.addSeparator()
            act_rename = menu.addAction("重命名")
            act_rename.triggered.connect(self.rename_selected)
            act_chmod = menu.addAction("修改权限")
            act_chmod.triggered.connect(self.chmod_selected)
            act_copy_path = menu.addAction("复制路径")
            act_copy_path.triggered.connect(
                lambda: QGuiApplication.clipboard().setText("\n".join(e.path for e in entries))
            )
            act_delete = menu.addAction("删除")
            act_delete.triggered.connect(self.delete_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ---------------------------------------------------------------- editing
    def edit_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        self.edit_path(entries[0].path)

    def edit_path(self, path: str) -> None:
        entry = next((e for e in self.entries if e.path == path), None)
        if entry is not None and entry.size > 4 * 1024 * 1024:
            QMessageBox.information(self, "文件过大", "超过 4 MB 的文件请先下载后编辑。")
            return
        self._set_status(f"读取 {path} …")

        def ok(text: str) -> None:
            self._set_status("已加载")
            dialog = EditorDialog(path, text, self.session.config.charset, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_text = dialog.text()
                self._set_status(f"保存 {path} …")
                self.session.run_async(
                    lambda: self.session.client.write_text(path, new_text),
                    lambda _n: (self._set_status(f"已保存 {path}"), self.refresh()),
                    self._fail,
                )

        self.session.run_async(lambda: self.session.client.read_text(path), ok, self._fail)

    def create_file(self) -> None:
        name, ok = QInputDialog.getText(self, "新建文件", "文件名：")
        if not ok or not name.strip():
            return
        path = self._join(name.strip())

        def done(_data: Any) -> None:
            self._set_status(f"已创建 {path}")
            self.refresh()

        self.session.run_async(lambda: self.session.client.touch(path), done, self._fail)

    def create_dir(self) -> None:
        name, ok = QInputDialog.getText(self, "新建目录", "目录名：")
        if not ok or not name.strip():
            return
        path = self._join(name.strip())

        def done(_data: Any) -> None:
            self._set_status(f"已创建 {path}")
            self.refresh()

        self.session.run_async(lambda: self.session.client.mkdir(path), done, self._fail)

    def rename_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        entry = entries[0]
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=entry.name)
        if not ok or not new_name.strip() or new_name == entry.name:
            return
        dst = self._join(new_name.strip())

        def done(_data: Any) -> None:
            self._set_status(f"已重命名 {entry.name} -> {new_name}")
            self.refresh()

        self.session.run_async(lambda: self.session.client.rename(entry.path, dst), done, self._fail)

    def chmod_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        entry = entries[0]
        current = entry.perm or "0644"
        text, ok = QInputDialog.getText(self, "修改权限", f"{entry.path}\n八进制权限：", text=current)
        if not ok or not text.strip():
            return
        try:
            mode = int(text.strip(), 8)
        except ValueError:
            QMessageBox.warning(self, "格式错误", "请输入八进制权限，例如 0644 / 0755")
            return

        def done(_data: Any) -> None:
            self._set_status(f"权限已修改: {text.strip()}")
            self.refresh()

        self.session.run_async(lambda: self.session.client.chmod(entry.path, mode), done, self._fail)

    def delete_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        names = "\n".join(e.path for e in entries[:10])
        if len(entries) > 10:
            names += f"\n… 共 {len(entries)} 项"
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定永久删除以下内容？\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def done(results: list[dict[str, Any]]) -> None:
            failed = [r for r in results if not r.get("ok")]
            if failed:
                QMessageBox.warning(self, "部分失败", "\n".join(f"{r['path']}: {r.get('error','')}" for r in failed))
            self._set_status(f"已删除 {len(results) - len(failed)} 项")
            self.refresh()

        self.session.run_async(
            lambda: self.session.client.delete([e.path for e in entries], recursive=True), done, self._fail
        )

    # --------------------------------------------------------------- transfer
    def _join(self, name: str) -> str:
        base = self.current_path.rstrip("/")
        if name.startswith("/"):
            return name
        return f"{base}/{name}" if base else f"/{name}"

    def upload_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要上传的文件")
        if not paths:
            return
        self._upload_queue(list(paths))

    def upload_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择要上传的目录")
        if directory:
            self._upload_dir_queue([directory])

    def _upload_dir_queue(self, dirs: list[str]) -> None:
        if not dirs:
            self.refresh()
            return
        local = Path(dirs[0])
        total = sum(f.stat().st_size for f in local.rglob("*") if f.is_file())
        dialog = QProgressDialog(f"上传目录 {local.name} …", "取消", 0, 100, self)
        dialog.setWindowTitle("上传目录")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setValue(0)

        # Worker thread writes plain numbers; the dialog is only touched from
        # the GUI thread via a timer (no cross-thread widget access).
        state: dict[str, Any] = {"done": 0, "total": max(1, total), "cancelled": False}
        timer = QTimer(self)
        timer.setInterval(120)

        def tick() -> None:
            dialog.setLabelText(
                f"上传 {local.name}\n{human_size(state['done'])} / {human_size(state['total'])}"
            )
            dialog.setValue(int(state["done"] * 100 / max(1, state["total"])))
            if dialog.wasCanceled():
                state["cancelled"] = True

        timer.timeout.connect(tick)
        timer.start()

        def on_progress(done: int, total_bytes: int) -> bool:
            state["done"] = done
            state["total"] = max(1, total_bytes)
            return not state["cancelled"]

        base = self.current_path or self.session.cwd

        def stop() -> None:
            timer.stop()
            dialog.close()

        def ok(result: Any) -> None:
            stop()
            self._set_status(
                f"目录 {local.name}: {result.get('files', 0)} 个文件, "
                f"{human_size(result.get('bytes', 0))} → {result.get('root', '')}"
            )
            self._upload_dir_queue(dirs[1:])

        def fail(message: str) -> None:
            stop()
            if "cancel" not in message.lower():
                QMessageBox.warning(self, "上传目录失败", message)
            self._upload_dir_queue(dirs[1:])

        self.session.run_async(
            lambda: self.session.client.upload_tree(
                local, base, progress=on_progress, cancel=lambda: state["cancelled"]
            ),
            ok,
            fail,
        )

    def _upload_queue(self, paths: list[str]) -> None:
        if not paths:
            self.refresh()
            return
        local = Path(paths[0])
        remote = self._join(local.name)
        progress = QProgressDialog(f"上传 {local.name} …", "取消", 0, 100, self)
        progress.setWindowTitle("上传")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)

        bridge = _Progress()
        state = {"value": 0, "total": 1, "cancelled": False}
        bridge.changed.connect(self._on_progress(progress, state, local.name))

        def on_progress(done: int, total: int) -> bool:
            state["value"], state["total"] = done, total
            bridge.changed.emit(done, total)
            state["cancelled"] = progress.wasCanceled()
            return not state["cancelled"]

        def ok(stats: Any) -> None:
            progress.close()
            resumed = getattr(stats, "resumed_from", 0)
            suffix = f" | 续传自 {human_size(resumed)}" if resumed else ""
            if getattr(stats, "skipped", False):
                suffix = " | 已存在且完整，跳过"
            self._set_status(
                f"已上传 {local.name} ({human_size(getattr(stats, 'bytes_done', 0))}, "
                f"{getattr(stats, 'rate', 0)/1024:.0f} KB/s){suffix}"
            )
            self._upload_queue(paths[1:])

        def fail(message: str) -> None:
            progress.close()
            if "cancel" in message.lower():
                self._set_status("上传已取消")
            else:
                QMessageBox.warning(self, "上传失败", message)
            self._upload_queue(paths[1:])

        self.session.run_async(
            lambda: self.session.client.upload_file(local, remote, progress=on_progress, cancel=lambda: state["cancelled"]),
            ok,
            fail,
        )

    def _on_progress(self, dialog: QProgressDialog, state: dict[str, Any], name: str):
        def update(done: int, total: int) -> None:
            dialog.setLabelText(f"上传 {name}\n{human_size(done)} / {human_size(total)}")
            if total > 0:
                dialog.setValue(int(done * 100 / total))

        return update

    def download_selected(self) -> None:
        entries = [e for e in self._selected_entries() if e.type != "dir"]
        if not entries:
            return
        target_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not target_dir:
            return
        self._download_queue(entries, Path(target_dir))

    def _download_queue(self, entries: list[RemoteEntry], target_dir: Path) -> None:
        if not entries:
            self.refresh()
            return
        entry = entries[0]
        local = target_dir / entry.name
        progress = QProgressDialog(f"下载 {entry.name} …", "取消", 0, 100, self)
        progress.setWindowTitle("下载")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        bridge = _Progress()
        bridge.changed.connect(self._on_progress(progress, {}, entry.name))

        def on_progress(done: int, total: int) -> bool:
            bridge.changed.emit(done, total)
            return not progress.wasCanceled()

        def ok(stats: Any) -> None:
            progress.close()
            resumed = getattr(stats, "resumed_from", 0)
            suffix = f" | 续传自 {human_size(resumed)}" if resumed else ""
            if getattr(stats, "skipped", False):
                suffix = " | 本地已完整，跳过"
            self._set_status(
                f"已下载 {entry.name} -> {local} ({human_size(getattr(stats, 'bytes_done', 0))}){suffix}"
            )
            self._download_queue(entries[1:], target_dir)

        def fail(message: str) -> None:
            progress.close()
            if "cancel" not in message.lower():
                QMessageBox.warning(self, "下载失败", message)
            self._download_queue(entries[1:], target_dir)

        self.session.run_async(
            lambda: self.session.client.download_file(entry.path, local, progress=on_progress),
            ok,
            fail,
        )

    # ------------------------------------------------------------------ misc
    def zip_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        default = self._join("archive.zip")
        dest, ok = QInputDialog.getText(self, "压缩", "压缩包路径：", text=default)
        if not ok or not dest.strip():
            return

        def done(data: Any) -> None:
            self._set_status(f"已压缩到 {data.get('dest', dest)}")
            self.refresh()

        self.session.run_async(lambda: self.session.client.zip([e.path for e in entries], dest.strip()), done, self._fail)

    def unzip_selected(self) -> None:
        entries = self._selected_entries()
        if len(entries) != 1:
            return
        entry = entries[0]
        default = entry.path.rsplit(".", 1)[0]
        dest, ok = QInputDialog.getText(self, "解压", "解压到目录：", text=default)
        if not ok or not dest.strip():
            return

        def done(data: Any) -> None:
            self._set_status(f"已解压到 {data.get('dest', dest)}")
            self.refresh()

        self.session.run_async(lambda: self.session.client.unzip(entry.path, dest.strip()), done, self._fail)

    def search(self) -> None:
        keyword, ok = QInputDialog.getText(self, "搜索文件", f"在 {self.current_path} 中搜索文件名：")
        if not ok:
            return
        self._set_status(f"搜索 {keyword or '*'} …")

        def done(entries: list[RemoteEntry]) -> None:
            self._set_status(f"找到 {len(entries)} 项")
            dialog = QDialog(self)
            dialog.setWindowTitle(f"搜索结果 — {len(entries)} 项")
            dialog.resize(760, 480)
            layout = QVBoxLayout(dialog)
            table = QTableWidget(len(entries), 4)
            table.setHorizontalHeaderLabels(["路径", "大小", "权限", "修改时间"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            for row, entry in enumerate(entries):
                table.setItem(row, 0, QTableWidgetItem(entry.path))
                table.setItem(row, 1, QTableWidgetItem(human_size(entry.size)))
                table.setItem(row, 2, QTableWidgetItem(entry.perm))
                table.setItem(row, 3, QTableWidgetItem(human_time(entry.mtime)))
            table.doubleClicked.connect(
                lambda index: (dialog.accept(), self.open_dir(os.path.dirname(entries[index.row()].path)))
            )
            layout.addWidget(table)
            dialog.exec()

        self.session.run_async(
            lambda: self.session.client.find(self.current_path, keyword, depth=6, limit=800), done, self._fail
        )
