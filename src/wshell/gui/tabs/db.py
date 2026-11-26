"""Database console (runs SQL through the shell's PHP runtime)."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...client import ShellError
from ..session import ShellSession
from ..widgets import mono_font


class DbTab(QWidget):
    def __init__(self, session: ShellSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        box = QGroupBox("连接")
        form = QFormLayout(box)
        form.setSpacing(6)

        self.driver = QComboBox()
        self.driver.addItems(["mysql", "pgsql", "sqlite"])
        form.addRow("驱动", self.driver)

        self.host = QLineEdit("127.0.0.1")
        form.addRow("主机", self.host)

        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(3306)
        form.addRow("端口", self.port)

        self.user = QLineEdit("root")
        form.addRow("用户", self.user)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("密码", self.password)

        self.dbname = QLineEdit()
        form.addRow("数据库", self.dbname)

        self.charset = QLineEdit("utf8mb4")
        form.addRow("字符集", self.charset)

        layout.addWidget(box)

        splitter = QSplitter(Qt.Orientation.Vertical)

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.sql = QPlainTextEdit()
        self.sql.setFont(mono_font(12))
        self.sql.setPlaceholderText("select * from users limit 10;")
        self.sql.setFixedHeight(120)
        editor_layout.addWidget(self.sql)
        buttons = QHBoxLayout()
        self.run_button = QPushButton("执行 SQL")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.execute)
        buttons.addWidget(self.run_button)
        clear = QPushButton("清空")
        clear.clicked.connect(self.sql.clear)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        self.status = QLabel("未执行")
        self.status.setObjectName("hint")
        buttons.addWidget(self.status)
        editor_layout.addLayout(buttons)
        splitter.addWidget(editor_widget)

        self.result = QTableWidget(0, 0)
        self.result.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result.setAlternatingRowColors(True)
        self.result.verticalHeader().setVisible(False)
        self.result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        splitter.addWidget(self.result)
        splitter.setSizes([180, 380])
        layout.addWidget(splitter, 1)

    def execute(self) -> None:
        sql = self.sql.toPlainText().strip()
        if not sql or self._busy:
            return
        self._busy = True
        self.run_button.setEnabled(False)
        self.status.setText("执行中…")
        driver = self.driver.currentText()
        port = self.port.value()

        def ok(data: dict[str, Any]) -> None:
            self._busy = False
            self.run_button.setEnabled(True)
            self._render(data)
            self.status.setText(f"完成 | 行数 {len(data.get('rows', []))} | 影响 {data.get('affected', 0)}")

        def fail(message: str) -> None:
            self._busy = False
            self.run_button.setEnabled(True)
            self.status.setText(f"失败: {message}")

        self.session.run_async(
            lambda: self.session.client.db_query(
                sql,
                host=self.host.text().strip(),
                port=port,
                user=self.user.text().strip(),
                password=self.password.text(),
                dbname=self.dbname.text().strip(),
                driver=driver,
                charset=self.charset.text().strip() or "utf8mb4",
            ),
            ok,
            fail,
        )

    def _render(self, data: dict[str, Any]) -> None:
        columns = data.get("columns") or []
        rows = data.get("rows") or []
        self.result.setColumnCount(len(columns))
        self.result.setHorizontalHeaderLabels([str(c) for c in columns])
        self.result.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                if value is None:
                    item.setForeground(Qt.GlobalColor.gray)
                self.result.setItem(r, c, item)
        self.result.resizeColumnsToContents()
