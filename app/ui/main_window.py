import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QMenu, QMessageBox
)

from app.core.account_state import AccountState
from app.core.logger import setup_logging
from app.database.database import init_db
from .dashboard import DashboardPage
from .accounts import AccountsPage
from . import services as services_module
from .services import ServicesPage, MIGRATION_STATUSES


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


# ---------------------------------------------------------------------------
# Runtime safeguards for the Services page.
# These keep live-scan rendering from fighting with the context menu and any
# migration dialog that is currently open.
# ---------------------------------------------------------------------------
_original_schedule_live_render = services_module.ServicesPage._schedule_live_render
_original_render_live_rows_deferred = services_module.ServicesPage._render_live_rows_deferred
_original_cleanup_scanned_services = services_module.ServicesPage.cleanup_scanned_services
_original_open_details_for_row = services_module.ServicesPage._open_details_for_row
_original_set_destination_for_row = services_module.ServicesPage._set_destination_for_row
_original_set_status_for_row = services_module.ServicesPage._set_status_for_row


def _interaction_open(self):
    return (
        getattr(self, "_context_menu_open", False)
        or getattr(self, "_interaction_dialog_open", False)
    )


def _render_after_interaction(self):
    self._live_render_pending = False
    if self.live_scan and not _interaction_open(self):
        self._render_live_rows()


def _safe_schedule_live_render(self):
    if _interaction_open(self):
        self._live_render_pending = False
        return
    return _original_schedule_live_render(self)


def _safe_render_live_rows_deferred(self):
    self._live_render_pending = False
    if _interaction_open(self):
        return
    if self.live_scan:
        self._render_live_rows()


def _safe_show_service_context_menu(self, position):
    index = self.table.indexAt(position)
    if not index.isValid() or not (0 <= index.row() < len(self.row_details)):
        return

    row = index.row()
    self._context_menu_open = True

    try:
        menu = QMenu(self.table)
        menu.setStyleSheet("""
            QMenu {
                background: #171b22;
                border: 1px solid #303846;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                color: #E7EAF0;
                background: transparent;
                padding: 8px 18px;
                margin: 0;
                border-radius: 5px;
            }
            QMenu::item:selected {
                color: #E7EAF0;
                background: #303846;
            }
        """)

        details_action = menu.addAction("Plus de détails")
        status_menu = menu.addMenu("Statut de migration")
        status_actions = {}
        for status in MIGRATION_STATUSES:
            action = status_menu.addAction(status)
            status_actions[action] = status
        destination_action = menu.addAction("Définir l'adresse de destination…")

        chosen = menu.exec(self.table.viewport().mapToGlobal(position))

    finally:
        self._context_menu_open = False
        self._live_render_pending = False

    if chosen == details_action:
        QTimer.singleShot(0, lambda: self._open_details_for_row(row, index.column()))
    elif chosen == destination_action:
        QTimer.singleShot(0, lambda: self._set_destination_for_row(row))
    elif chosen in status_actions:
        status = status_actions[chosen]
        QTimer.singleShot(0, lambda: self._set_status_for_row(row, status))
    elif self.live_scan:
        self._render_live_rows()


def _safe_open_details_for_row(self, row, column):
    self._interaction_dialog_open = True
    try:
        return _original_open_details_for_row(self, row, column)
    finally:
        self._interaction_dialog_open = False
        _render_after_interaction(self)


def _safe_set_destination_for_row(self, row):
    self._interaction_dialog_open = True
    try:
        return _original_set_destination_for_row(self, row)
    finally:
        self._interaction_dialog_open = False
        _render_after_interaction(self)


def _safe_set_status_for_row(self, row, status):
    self._interaction_dialog_open = True
    try:
        return _original_set_status_for_row(self, row, status)
    finally:
        self._interaction_dialog_open = False
        _render_after_interaction(self)


def _confirmed_cleanup_scanned_services(self):
    answer = QMessageBox.question(
        self,
        "Nettoyage des services",
        "Voulez-vous vraiment supprimer tous les services détectés par les scans ?\n\n"
        "Les comptes Google et leurs autorisations ne seront pas supprimés.",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )

    if answer != QMessageBox.Yes:
        return

    return _original_cleanup_scanned_services(self)


services_module.ServicesPage._schedule_live_render = _safe_schedule_live_render
services_module.ServicesPage._render_live_rows_deferred = _safe_render_live_rows_deferred
services_module.ServicesPage._show_service_context_menu = _safe_show_service_context_menu
services_module.ServicesPage._open_details_for_row = _safe_open_details_for_row
services_module.ServicesPage._set_destination_for_row = _safe_set_destination_for_row
services_module.ServicesPage._set_status_for_row = _safe_set_status_for_row
services_module.ServicesPage.cleanup_scanned_services = _confirmed_cleanup_scanned_services


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
