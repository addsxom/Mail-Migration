import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel
)

from app.core.account_state import AccountState
from app.core.logger import setup_logging
from app.database.database import init_db
from .dashboard import DashboardPage
from .accounts import AccountsPage
from . import services as services_module
from .services import ServicesPage


STYLE = """
QMainWindow, QWidget {
    background: #111318;
    color: #ECEEF2;
    font-family: Segoe UI;
    font-size: 14px;
}
QPushButton {
    background: #1C2028;
    border: 1px solid #2B313C;
    border-radius: 8px;
    padding: 10px 14px;
}
QPushButton:hover {
    background: #272D38;
}
QPushButton:pressed {
    background: #303744;
}
QPushButton:checked {
    background: #303846;
    border: 1px solid #71819A;
    color: #FFFFFF;
}
QPushButton:checked:hover {
    background: #363D49;
    border: 1px solid #7B8AA2;
}
QLabel#title {
    font-size: 22px;
    font-weight: 700;
}
QLabel#muted {
    color: #9AA2AF;
}
"""


_CIRCULAR_ICON_CACHE = {}
_original_service_icon = services_module._service_icon


def _make_circular_icon(icon):
    """Place any service logo inside a consistent circular mask."""
    if not isinstance(icon, QIcon) or icon.isNull():
        return icon

    cache_key = id(icon)
    cached = _CIRCULAR_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    circle = QPainterPath()
    circle.addEllipse(1, 1, size - 2, size - 2)
    painter.setClipPath(circle)

    painter.fillPath(circle, QColor(29, 34, 43))

    source = icon.pixmap(size - 12, size - 12)
    if not source.isNull():
        target = source.scaled(
            size - 12,
            size - 12,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        x = (size - target.width()) // 2
        y = (size - target.height()) // 2
        painter.drawPixmap(x, y, target)

    painter.end()

    circular = QIcon(pixmap)
    _CIRCULAR_ICON_CACHE[cache_key] = circular
    return circular


def _circular_service_icon(name, category=""):
    return _make_circular_icon(_original_service_icon(name, category))


# Keep the existing service/icon system, but normalize every displayed logo to a circle.
services_module._service_icon = _circular_service_icon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mail Migration")
        self.resize(1180, 760)
        self.setStyleSheet(STYLE)

        self.account_state = AccountState()
        self.account_state.changed.connect(self._account_changed)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)

        sidebar = QVBoxLayout()
        title = QLabel("Mail Migration")
        title.setObjectName("title")
        sidebar.addWidget(title)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.accounts = AccountsPage(self.set_active_account)
        self.services = ServicesPage()

        self.accounts.scan_started.connect(self.services.start_live_scan)
        self.accounts.scan_detection.connect(self.services.update_live_detection)
        self.accounts.scan_finished_live.connect(self.services.finish_live_scan)

        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.accounts)
        self.stack.addWidget(self.services)

        for text, index in [
            ("Dashboard", 0),
            ("Comptes Google", 1),
            ("Services", 2),
        ]:
            button = QPushButton(text)
            button.clicked.connect(
                lambda checked=False, i=index: self.stack.setCurrentIndex(i)
            )
            sidebar.addWidget(button)

        sidebar.addStretch()
        info = QLabel("Lecture Gmail uniquement")
        info.setObjectName("muted")
        info.setAlignment(Qt.AlignCenter)
        sidebar.addWidget(info)

        layout.addLayout(sidebar, 1)
        layout.addWidget(self.stack, 4)
        self.setCentralWidget(root)
        self.refresh_all()

    @property
    def active_account_id(self):
        return self.account_state.account_id

    def set_active_account(self, account_id):
        self.account_state.set_account(account_id)

    def _account_changed(self, account_id):
        self.dashboard.set_active_account(account_id)
        self.services.set_active_account(account_id)

    def refresh_all(self):
        self.accounts.refresh(self.active_account_id)
        self.dashboard.refresh()
        self.services.refresh()


def run():
    setup_logging()
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
