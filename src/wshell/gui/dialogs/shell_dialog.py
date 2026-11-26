"""Add / edit a shell profile, with a live connection test."""

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...client import ShellClient, ShellError
from ...config import ShellConfig
from ...crypto import sm4
from ...protocol import CARRIERS
from ...transport import available_transports, impersonation_targets


class _PingThread(QThread):
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def __init__(self, config: ShellConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:  # noqa: D401
        client = ShellClient(self.config)
        try:
            info = client.ping()
            limits = client.limits(refresh=True)
            detail = (
                f"连接成功 — {info.get('os', '?')} / {info.get('cwd', '?')}"
                f" | 协议 {self.config.proto} / {self.config.carrier}"
                f" | post_max={limits.get('post_max_size', 0)}"
            )
            self.finished_ok.emit(detail)
        except ShellError as exc:
            self.finished_err.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(f"{type(exc).__name__}: {exc}")
        finally:
            client.close()


class ShellDialog(QDialog):
    def __init__(self, config: ShellConfig | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑会话" if config else "添加会话")
        self.resize(600, 760)
        self.config = config or ShellConfig()
        self._thread: _PingThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.name = QLineEdit(self.config.name)
        form.addRow("名称", self.name)

        self.url = QLineEdit(self.config.url)
        self.url.setPlaceholderText("http://target/upload/shell.php")
        form.addRow("URL", self.url)

        self.proto = QComboBox()
        self.proto.addItem("v2 — HKDF + HMAC + 多载体（推荐）", "v2")
        self.proto.addItem("v1 — SM4-CBC + Base64（兼容旧 Shell）", "v1")
        self.proto.setCurrentIndex(0 if self.config.proto == "v2" else 1)
        self.proto.currentIndexChanged.connect(self._toggle_proto)
        form.addRow("协议版本", self.proto)

        self.pass_param = QLineEdit(self.config.pass_param)
        form.addRow("参数名", self.pass_param)

        layout.addLayout(form)

        # ---- v1 credentials -------------------------------------------------
        self.v1_group = QGroupBox("v1 凭证 (SM4-CBC + Base64)")
        v1_form = QFormLayout(self.v1_group)
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        self.key = QLineEdit(self.config.key)
        self.key.setPlaceholderText("32 位十六进制 或 16 字节口令")
        key_row.addWidget(self.key, 1)
        v1_random = QPushButton("随机")
        v1_random.setFixedWidth(64)
        v1_random.clicked.connect(self._random_v1)
        key_row.addWidget(v1_random)
        key_widget = QWidget()
        key_widget.setLayout(key_row)
        v1_form.addRow("密钥 Key", key_widget)
        self.iv = QLineEdit(self.config.iv)
        self.iv.setPlaceholderText("32 位十六进制 或 16 字节口令")
        v1_form.addRow("偏移 IV", self.iv)
        self.body_mode = QComboBox()
        self.body_mode.addItems(["form", "raw"])
        self.body_mode.setCurrentText(self.config.body_mode)
        v1_form.addRow("传参方式", self.body_mode)
        layout.addWidget(self.v1_group)

        # ---- v2 credentials -------------------------------------------------
        self.v2_group = QGroupBox("v2 凭证 (HKDF-SHA256 → SM4-CBC + HMAC-SHA256)")
        v2_form = QFormLayout(self.v2_group)

        secret_row = QHBoxLayout()
        secret_row.setContentsMargins(0, 0, 0, 0)
        self.secret = QLineEdit(self.config.secret)
        self.secret.setPlaceholderText("64 位十六进制 (32 字节 secret)")
        secret_row.addWidget(self.secret, 1)
        v2_random = QPushButton("随机")
        v2_random.setFixedWidth(64)
        v2_random.clicked.connect(self._random_v2)
        secret_row.addWidget(v2_random)
        secret_widget = QWidget()
        secret_widget.setLayout(secret_row)
        v2_form.addRow("Secret", secret_widget)

        self.salt = QLineEdit(self.config.salt)
        self.salt.setPlaceholderText("32 位十六进制 (16 字节 salt)")
        v2_form.addRow("Salt", self.salt)

        self.carrier = QComboBox()
        for carrier in CARRIERS:
            self.carrier.addItem(carrier, carrier)
        self.carrier.setCurrentText(self.config.carrier)
        v2_form.addRow("载体", self.carrier)

        pad_row = QHBoxLayout()
        pad_row.setContentsMargins(0, 0, 0, 0)
        self.pad_bucket = QComboBox()
        for bucket in (0, 512, 1024, 2048, 4096, 8192, 16384):
            self.pad_bucket.addItem("关闭" if bucket == 0 else f"{bucket} B", bucket)
        idx = max(0, self.pad_bucket.findData(self.config.pad_bucket))
        self.pad_bucket.setCurrentIndex(idx)
        pad_row.addWidget(self.pad_bucket)
        self.rpad = QSpinBox()
        self.rpad.setRange(0, 1 << 20)
        self.rpad.setSingleStep(1024)
        self.rpad.setValue(self.config.rpad)
        self.rpad.setToolTip("响应填充到该长度（0=关闭）")
        pad_row.addWidget(self.rpad)
        pad_widget = QWidget()
        pad_widget.setLayout(pad_row)
        v2_form.addRow("请求/响应填充", pad_widget)

        timing_row = QHBoxLayout()
        timing_row.setContentsMargins(0, 0, 0, 0)
        self.ts_window = QSpinBox()
        self.ts_window.setRange(0, 86400)
        self.ts_window.setValue(self.config.ts_window)
        self.ts_window.setToolTip("时间戳有效期（秒），0=不校验")
        timing_row.addWidget(QLabel("时间窗"))
        timing_row.addWidget(self.ts_window)
        self.jitter = QDoubleSpinBox()
        self.jitter.setRange(0, 30)
        self.jitter.setDecimals(2)
        self.jitter.setSingleStep(0.25)
        self.jitter.setValue(self.config.jitter)
        self.jitter.setToolTip("每次请求前随机延时上限（秒）")
        timing_row.addWidget(QLabel("抖动"))
        timing_row.addWidget(self.jitter)
        self.min_interval = QDoubleSpinBox()
        self.min_interval.setRange(0, 60)
        self.min_interval.setDecimals(2)
        self.min_interval.setSingleStep(0.1)
        self.min_interval.setValue(self.config.min_interval)
        self.min_interval.setToolTip("请求最小间隔（秒）")
        timing_row.addWidget(QLabel("间隔"))
        timing_row.addWidget(self.min_interval)
        timing_widget = QWidget()
        timing_widget.setLayout(timing_row)
        v2_form.addRow("节流", timing_widget)

        layout.addWidget(self.v2_group)

        # ---- shared ---------------------------------------------------------
        form2 = QFormLayout()
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setValue(self.config.timeout)
        form2.addRow("超时(秒)", self.timeout)

        self.transport = QComboBox()
        for name in available_transports():
            label = "curl_cffi（浏览器 TLS 指纹）" if name == "curl_cffi" else "requests"
            self.transport.addItem(label, name)
        idx = self.transport.findData(self.config.transport)
        self.transport.setCurrentIndex(idx if idx >= 0 else 0)
        form2.addRow("传输后端", self.transport)

        self.impersonate = QComboBox()
        self.impersonate.setEditable(True)
        self.impersonate.addItems(impersonation_targets())
        self.impersonate.setCurrentText(self.config.impersonate or "chrome")
        form2.addRow("TLS 指纹", self.impersonate)
        self.chunk_kb = QSpinBox()
        self.chunk_kb.setRange(16, 8192)
        self.chunk_kb.setValue(self.config.chunk_kb)
        form2.addRow("分块(KB)", self.chunk_kb)
        self.charset = QLineEdit(self.config.charset)
        form2.addRow("输出编码", self.charset)
        self.proxy = QLineEdit(self.config.proxy)
        self.proxy.setPlaceholderText("http://127.0.0.1:8080（可留空）")
        form2.addRow("代理", self.proxy)
        self.group = QLineEdit(self.config.group)
        form2.addRow("分组", self.group)
        self.remark = QLineEdit(self.config.remark)
        form2.addRow("备注", self.remark)
        self.headers = QPlainTextEdit()
        self.headers.setFixedHeight(64)
        self.headers.setPlaceholderText('{"X-Forwarded-For": "127.0.0.1"}')
        self.headers.setPlainText(json.dumps(self.config.headers, ensure_ascii=False) if self.config.headers else "")
        form2.addRow("额外 Header", self.headers)
        layout.addLayout(form2)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._test)
        test_row.addWidget(self.test_button)
        self.test_label = QLabel("")
        self.test_label.setObjectName("hint")
        self.test_label.setWordWrap(True)
        test_row.addWidget(self.test_label, 1)
        layout.addLayout(test_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._toggle_proto()

    # ------------------------------------------------------------------ util
    def _toggle_proto(self) -> None:
        is_v2 = self.proto.currentData() == "v2"
        self.v1_group.setVisible(not is_v2)
        self.v2_group.setVisible(is_v2)

    def _random_v1(self) -> None:
        self.key.setText(sm4.random_key().hex())
        self.iv.setText(sm4.random_iv().hex())

    def _random_v2(self) -> None:
        self.secret.setText(os.urandom(32).hex())
        self.salt.setText(os.urandom(16).hex())

    def _collect(self) -> ShellConfig:
        config = self.config
        config.name = self.name.text().strip() or "unnamed"
        config.url = self.url.text().strip()
        config.proto = self.proto.currentData() or "v2"
        config.pass_param = self.pass_param.text().strip() or "data"
        config.key = self.key.text().strip()
        config.iv = self.iv.text().strip()
        config.body_mode = self.body_mode.currentText()
        config.secret = self.secret.text().strip()
        config.salt = self.salt.text().strip()
        config.carrier = self.carrier.currentData() or "form"
        config.pad_bucket = int(self.pad_bucket.currentData() or 0)
        config.rpad = int(self.rpad.value())
        config.ts_window = int(self.ts_window.value())
        config.jitter = float(self.jitter.value())
        config.min_interval = float(self.min_interval.value())
        config.timeout = float(self.timeout.value())
        config.transport = self.transport.currentData() or "requests"
        config.impersonate = self.impersonate.currentText().strip() or "chrome"
        config.chunk_kb = int(self.chunk_kb.value())
        config.charset = self.charset.text().strip() or "utf-8"
        config.proxy = self.proxy.text().strip()
        config.group = self.group.text().strip() or "default"
        config.remark = self.remark.text().strip()
        raw_headers = self.headers.toPlainText().strip()
        if raw_headers:
            try:
                parsed = json.loads(raw_headers)
                if isinstance(parsed, dict):
                    config.headers = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                pass
        return config

    def _test(self) -> None:
        config = self._collect()
        if not config.url:
            self.test_label.setText("请先填写 URL")
            return
        try:
            from ...protocol import normalize_secret

            if config.proto == "v1":
                normalize_secret(config.key)
                normalize_secret(config.iv)
            else:
                if len(config.secret) != 64 or len(config.salt) != 32:
                    raise ValueError("v2 需要 64 位 secret 与 32 位 salt（hex）")
                bytes.fromhex(config.secret)
                bytes.fromhex(config.salt)
        except ValueError as exc:
            self.test_label.setText(f"凭证格式错误: {exc}")
            return
        self.test_button.setEnabled(False)
        self.test_label.setText("正在连接…")
        self._thread = _PingThread(config)
        self._thread.finished_ok.connect(self._test_ok)
        self._thread.finished_err.connect(self._test_fail)
        self._thread.start()

    def _test_ok(self, message: str) -> None:
        self.test_button.setEnabled(True)
        self.test_label.setText(message)
        self.test_label.setStyleSheet("color:#4ade80;")

    def _test_fail(self, message: str) -> None:
        self.test_button.setEnabled(True)
        self.test_label.setText(f"连接失败: {message}")
        self.test_label.setStyleSheet("color:#f87171;")

    def result_config(self) -> ShellConfig:
        return self._collect()
