"""Dev helper: render the GUI headlessly and save screenshots.

    QT_QPA_PLATFORM=offscreen uv run python scripts/gui_shot.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("WEBSHELL_MAG_HOME", str(Path("docs/.cfg").resolve()))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from wshell import payloads  # noqa: E402
from wshell.config import ShellConfig  # noqa: E402
from wshell.gui.app import create_app  # noqa: E402
from wshell.gui.main_window import MainWindow  # noqa: E402

OUT = ROOT / "docs" / "shots"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def pump(app: QApplication, predicate, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.03)
    return False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    www = ROOT / "docs" / "demo_www"
    www.mkdir(parents=True, exist_ok=True)
    source = payloads.generate_php(proto="v2")
    (www / "shell.php").write_text(source.code, encoding="utf-8")
    (www / "index.html").write_text("<h1>demo</h1>", encoding="utf-8")
    (www / "notes.txt").write_text("webshell-mag demo file\n", encoding="utf-8")
    (www / "upload").mkdir(exist_ok=True)
    (www / "upload" / "config.php").write_text("<?php // demo\n", encoding="utf-8")
    (www / "upload" / "dump.sql").write_text("-- demo\n", encoding="utf-8")

    php = subprocess.Popen(
        ["php", "-S", f"127.0.0.1:{free_port()}", "-t", str(www)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    port = int(php.args[2].split(":")[1])
    url = f"http://127.0.0.1:{port}/shell.php"
    time.sleep(0.7)

    app = create_app([])
    import shutil

    cfg_dir = ROOT / "docs" / ".cfg"
    if cfg_dir.exists():
        shutil.rmtree(cfg_dir)
    window = MainWindow()
    window.resize(1360, 860)
    window.show()

    live = ShellConfig(
        name="demo-web-01",
        url=url,
        proto="v2",
        secret=source.secret_hex,
        salt=source.salt_hex,
        carrier="form",
        pad_bucket=4096,
        rpad=1024,
        group="演示",
    )
    standby = ShellConfig(
        name="demo-web-02",
        url="http://127.0.0.1:9/shell.php",
        proto="v1",
        key="00" * 16,
        iv="00" * 16,
        group="演示",
    )
    window.shells[live.id] = live
    window.shells[standby.id] = standby
    window._rebuild_tree()

    window.connect_shell(live)
    session = window.sessions[live.id]
    pump(app, lambda: session.connected and bool(session.info))
    pump(app, lambda: session.info.get("cwd") != "")

    workspace = window.workspaces[live.id]
    app.processEvents()
    time.sleep(0.2)
    window.grab().save(str(OUT / "01-terminal.png"))

    workspace.tabs.setCurrentWidget(workspace.files)
    workspace.files.ensure_loaded()
    pump(app, lambda: bool(workspace.files.entries), 10)
    app.processEvents()
    window.grab().save(str(OUT / "02-files.png"))

    workspace.tabs.setCurrentWidget(workspace.info)
    pump(app, lambda: workspace.info.tree.topLevelItemCount() > 0, 10)
    app.processEvents()
    window.grab().save(str(OUT / "03-info.png"))

    workspace.terminal.input.setText("printf '\\033[32mANSI OK\\033[0m '; uname -a; php -v | head -1; whoami")
    workspace.terminal.submit()
    pump(app, lambda: "PHP" in workspace.terminal.output.toPlainText(), 15)
    workspace.tabs.setCurrentWidget(workspace.terminal)
    app.processEvents()
    window.grab().save(str(OUT / "04-terminal-output.png"))

    workspace.tabs.setCurrentWidget(workspace.traffic)
    app.processEvents()
    window.grab().save(str(OUT / "05-traffic.png"))

    from wshell.gui.dialogs.generate_dialog import GenerateDialog

    dialog = GenerateDialog(window)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(OUT / "06-generate.png"))
    dialog.close()

    from wshell.gui.dialogs.shell_dialog import ShellDialog

    shell_dialog = ShellDialog(live, window)
    shell_dialog.show()
    app.processEvents()
    shell_dialog.grab().save(str(OUT / "07-shell-dialog.png"))
    shell_dialog.close()

    window.close()
    php.terminate()
    print("screenshots ->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
