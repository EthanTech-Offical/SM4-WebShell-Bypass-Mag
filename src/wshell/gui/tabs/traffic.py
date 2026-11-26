"""Traffic inspector — every request/response pair, decrypted."""

from __future__ import annotations

import json
import time
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..session import ShellSession
from ..widgets import mono_font


class TrafficTab(QWidget):
    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.records: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        title = QLabel("协议流量")
        title.setObjectName("sectionTitle")
        bar.addWidget(title)
        bar.addStretch(1)
        self.show_plain = QCheckBox("显示明文")
        self.show_plain.setChecked(True)
        self.show_plain.toggled.connect(lambda _checked: self._refresh_detail())
        bar.addWidget(self.show_plain)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self.clear)
        bar.addWidget(clear_button)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["时间", "操作", "载体", "HTTP", "耗时(ms)", "状态"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for col in (0, 2, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._refresh_detail)
        splitter.addWidget(self.table)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFont(mono_font(11))
        splitter.addWidget(self.detail)
        splitter.setSizes([240, 320])
        layout.addWidget(splitter, 1)

        session.traces.connect(self.add_record)

    def add_record(self, record: dict[str, Any]) -> None:
        self.records.append(record)
        row = self.table.rowCount()
        self.table.insertRow(row)
        status = "ok" if record.get("ok") else (record.get("note") or "error")
        values = [
            record.get("time", ""),
            str(record.get("op", "")),
            f"{record.get('proto', 'v1')}/{record.get('carrier', 'form')}",
            str(record.get("status", "")),
            f"{record.get('elapsed', 0) * 1000:.0f}",
            status[:60],
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, row)
            if not record.get("ok"):
                item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, col, item)
        if self.table.rowCount() > 2000:
            self.table.removeRow(0)
            self.records.pop(0)
            row -= 1
        self.table.scrollToBottom()
        self.table.selectRow(row)
        self._refresh_detail()

    def clear(self) -> None:
        self.records.clear()
        self.table.setRowCount(0)
        self.detail.clear()

    def _refresh_detail(self) -> None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if not rows:
            return
        row = sorted(rows)[0]
        if row >= len(self.records):
            return
        record = self.records[row]
        if self.show_plain.isChecked():
            payload = json.dumps(record.get("payload", {}), indent=2, ensure_ascii=False)
            response = record.get("response")
            response_text = json.dumps(response, indent=2, ensure_ascii=False) if response else record.get("response_raw", "")
            text = (
                f"# 请求 {record.get('time','')}  op={record.get('op','')}  "
                f"proto={record.get('proto','v1')}  carrier={record.get('carrier','form')}  "
                f"status={record.get('status','')}  {record.get('elapsed',0)*1000:.1f} ms\n"
                f"## 明文负载\n{payload}\n\n"
                f"## 响应\n{response_text}\n\n"
                f"## 备注\n{record.get('note','') or '-'}\n"
            )
        else:
            text = (
                f"## 请求体\n{record.get('body','')}\n\n"
                f"## 载荷密文 (base64)\n{record.get('carrier','')}\n\n"
                f"## 原始响应\n{record.get('response_raw','')}\n"
            )
        self.detail.setPlainText(text)
