"""Dark console styling for the application."""

from __future__ import annotations

APP_QSS = """
* {
    font-family: "PingFang SC", "Helvetica Neue", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}
QWidget {
    background: #16181d;
    color: #d7dae1;
}
QMainWindow, QDialog {
    background: #121418;
}
QMenuBar {
    background: #121418;
    border-bottom: 1px solid #24272f;
}
QMenuBar::item { padding: 6px 12px; background: transparent; }
QMenuBar::item:selected { background: #23262f; border-radius: 4px; }
QMenu {
    background: #1b1e25;
    border: 1px solid #2b2f39;
    padding: 4px;
}
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 4px; }
QMenu::item:selected { background: #2b6cb0; color: #ffffff; }
QMenu::separator { height: 1px; background: #2b2f39; margin: 4px 8px; }

QToolBar {
    background: #14161b;
    border-bottom: 1px solid #24272f;
    spacing: 4px;
    padding: 4px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 10px;
    color: #cfd3db;
}
QToolButton:hover { background: #23262f; border-color: #2e3340; }
QToolButton:pressed { background: #2b6cb0; color: #fff; }
QToolButton:disabled { color: #5b606b; }

QSplitter::handle { background: #1d2027; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }

QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget {
    background: #16181d;
    alternate-background-color: #191c22;
    border: 1px solid #24272f;
    border-radius: 6px;
    gridline-color: #23262d;
    selection-background-color: #2b6cb0;
    selection-color: #ffffff;
    outline: none;
}
QTreeWidget::item, QTableWidget::item { padding: 4px 6px; }
QHeaderView::section {
    background: #1b1e25;
    color: #9aa1ad;
    border: none;
    border-right: 1px solid #24272f;
    border-bottom: 1px solid #24272f;
    padding: 6px;
    font-weight: 600;
}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #1a1d23;
    border: 1px solid #2b2f39;
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: #2b6cb0;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #1b1e25;
    border: 1px solid #2b2f39;
    selection-background-color: #2b6cb0;
}

QPushButton {
    background: #23262f;
    border: 1px solid #2f3440;
    border-radius: 5px;
    padding: 5px 14px;
    color: #dfe3ea;
}
QPushButton:hover { background: #2b3040; border-color: #3a4152; }
QPushButton:pressed { background: #2b6cb0; border-color: #2b6cb0; color: #fff; }
QPushButton:disabled { color: #5b606b; background: #1b1e25; }
QPushButton#primary {
    background: #2b6cb0;
    border-color: #2b6cb0;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primary:hover { background: #3182ce; }
QPushButton#danger { background: #7f1d1d; border-color: #7f1d1d; }
QPushButton#danger:hover { background: #991b1b; }

QTabWidget::pane {
    border: 1px solid #24272f;
    border-radius: 6px;
    top: -1px;
    background: #16181d;
}
QTabBar::tab {
    background: #1a1d23;
    color: #98a0ad;
    padding: 7px 14px;
    border: 1px solid #24272f;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #23262f; color: #f0f2f6; }
QTabBar::tab:hover { color: #dbe0e8; }

QStatusBar {
    background: #121418;
    border-top: 1px solid #24272f;
    color: #8f96a3;
}
QStatusBar::item { border: none; }

QProgressBar {
    background: #1a1d23;
    border: 1px solid #2b2f39;
    border-radius: 4px;
    text-align: center;
    color: #cfd3db;
}
QProgressBar::chunk { background: #2b6cb0; border-radius: 3px; }

QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #333845; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #414857; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent; height: 10px; margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #333845; border-radius: 5px; min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QToolTip {
    background: #23262f;
    color: #e6e9ef;
    border: 1px solid #3a4152;
    padding: 4px 6px;
}
QLabel#sectionTitle {
    color: #8f96a3;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#hint { color: #7b8290; }
QLabel#badge {
    border-radius: 4px;
    padding: 1px 6px;
    background: #1f3a5f;
    color: #9ec5ff;
    font-size: 11px;
}
QCheckBox, QRadioButton { spacing: 6px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid #3a4152; background: #1a1d23;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: #2b6cb0; border-color: #2b6cb0;
}
QGroupBox {
    border: 1px solid #24272f;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #8f96a3;
}
QTableCornerButton::section { background: #1b1e25; border: none; }
"""
