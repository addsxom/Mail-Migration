import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QStackedWidget, QLabel, QMenu, QMessageBox, QFrame
from app.core.account_state import AccountState
from app.core.logger import setup_logging
from app.database.database import init_db
from .dashboard import DashboardPage
from .accounts import AccountsPage
from . import services as services_module
from .services import ServicesPage, MIGRATION_STATUSES, ServiceDetailsDialog
from .export import ExportPage
from .settings import SettingsPage

STYLE = """
QMainWindow, QWidget { background:#111318; color:#ECEEF2; font-family:Segoe UI; font-size:14px; }
QPushButton { background:#1C2028; border:1px solid #2B313C; border-radius:8px; padding:10px 14px; }
QPushButton:hover { background:#272D38; }
QPushButton:pressed { background:#303744; }
QPushButton:checked { background:#303846; border:1px solid #71819A; color:#FFFFFF; }
QPushButton:checked:hover { background:#363D49; border:1px solid #7B8AA2; }
QLabel#title { font-size:22px; font-weight:700; }
QLabel#muted { color:#9AA2AF; }
QDialog { background:#111318; }
QFrame#serviceDetailsCard { border:1px solid #303846; border-radius:16px; background:#171B22; }
QFrame#serviceDetailsCard QLabel#serviceDetailsTitle { font-size:24px; font-weight:700; color:#F2F4F7; padding-top:2px; }
QFrame#serviceDetailsCard QLabel#serviceDetailsSubtitle { color:#8F98A8; font-size:13px; padding-bottom:4px; }
QFrame#serviceDetailsCard QLabel[class="detailLabel"] { color:#8F98A8; font-size:12px; font-weight:600; padding-top:2px; }
QFrame#serviceDetailsCard QLabel#signalValue { color:#D9DEE7; line-height:1.35; }
QFrame#serviceDetailsCard QLabel#scoreValue { color:#FFFFFF; font-size:22px; font-weight:700; }
QFrame#serviceDetailsCard QLineEdit, QFrame#serviceDetailsCard QComboBox, QFrame#serviceDetailsCard QTextEdit { border:1px solid #303846; border-radius:9px; background:#10141A; color:#E7EAF0; padding:8px 10px; }
QFrame#serviceDetailsCard QLineEdit:focus, QFrame#serviceDetailsCard QComboBox:focus, QFrame#serviceDetailsCard QTextEdit:focus { border:1px solid #65748C; background:#12171E; }
QDialog QPushButton { min-width:90px; padding:9px 16px; border-radius:9px; }
QDialog QPushButton:hover { background:#272D38; }
QDialog QPushButton:default { background:#303846; border:1px solid #65748C; color:#FFFFFF; }
"""

_CIRCULAR_ICON_CACHE = {}
_original_service_icon = services_module._service_icon

def _make_circular_icon(icon):
    if not isinstance(icon, QIcon) or icon.isNull(): return icon
    cache_key=id(icon)
    if cache_key in _CIRCULAR_ICON_CACHE: return _CIRCULAR_ICON_CACHE[cache_key]
    size=64; pixmap=QPixmap(size,size); pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing,True); painter.setRenderHint(QPainter.SmoothPixmapTransform,True)
    circle=QPainterPath(); circle.addEllipse(1,1,size-2,size-2); painter.setClipPath(circle); painter.fillPath(circle,QColor(29,34,43))
    source=icon.pixmap(size-12,size-12)
    if not source.isNull():
        target=source.scaled(size-12,size-12,Qt.KeepAspectRatio,Qt.SmoothTransformation); painter.drawPixmap((size-target.width())//2,(size-target.height())//2,target)
    painter.end(); circular=QIcon(pixmap); _CIRCULAR_ICON_CACHE[cache_key]=circular; return circular

def _circular_service_icon(name,category=""): return _make_circular_icon(_original_service_icon(name,category))
services_module._service_icon=_circular_service_icon

_original_accounts_refresh=AccountsPage.refresh
def _accounts_refresh_with_saved_label(self,selected_id=None):
    _original_accounts_refresh(self,selected_id)
    for i in range(self.list.count()):
        item=self.list.item(i)
        item.setText(item.text().replace("Dernier scan :", "✓ Scan sauvegardé :"))
AccountsPage.refresh=_accounts_refresh_with_saved_label

_original_schedule_live_render=services_module.ServicesPage._schedule_live_render
_original_render_live_rows_deferred=services_module.ServicesPage._render_live_rows_deferred
_original_cleanup_scanned_services=services_module.ServicesPage.cleanup_scanned_services
_original_open_details_for_row=services_module.ServicesPage._open_details_for_row
_original_set_destination_for_row=services_module.ServicesPage._set_destination_for_row
_original_set_status_for_row=services_module.ServicesPage._set_status_for_row

def _interaction_open(self): return getattr(self,"_context_menu_open",False) or getattr(self,"_interaction_dialog_open",False)
def _render_after_interaction(self):
    self._live_render_pending=False
    if self.live_scan and not _interaction_open(self): self._render_live_rows()
def _safe_schedule_live_render(self):
    if _interaction_open(self): self._live_render_pending=False; return
    return _original_schedule_live_render(self)
def _safe_render_live_rows_deferred(self):
    self._live_render_pending=False
    if _interaction_open(self): return
    if self.live_scan: self._render_live_rows()
def _safe_show_service_context_menu(self,position):
    index=self.table.indexAt(position)
    if not index.isValid() or not (0<=index.row()<len(self.row_details)): return
    row=index.row(); self._context_menu_open=True
    try:
        menu=QMenu(self.table); menu.setStyleSheet("QMenu{background:#171b22;border:1px solid #303846;border-radius:8px;padding:4px;} QMenu::item{color:#E7EAF0;background:transparent;padding:8px 18px;margin:0;border-radius:5px;} QMenu::item:selected{color:#E7EAF0;background:#303846;}")
        details_action=menu.addAction("Plus de détails"); status_menu=menu.addMenu("Statut de migration"); status_actions={}
        for status in MIGRATION_STATUSES: status_actions[status_menu.addAction(status)]=status
        destination_action=menu.addAction("Définir l'adresse de destination…"); chosen=menu.exec(self.table.viewport().mapToGlobal(position))
    finally:
        self._context_menu_open=False; self._live_render_pending=False
    if chosen==details_action: QTimer.singleShot(0,lambda:self._open_details_for_row(row,index.column()))
    elif chosen==destination_action: QTimer.singleShot(0,lambda:self._set_destination_for_row(row))
    elif chosen in status_actions: QTimer.singleShot(0,lambda:self._set_status_for_row(row,status_actions[chosen]))
    elif self.live_scan: self._render_live_rows()
def _safe_open_details_for_row(self,row,column):
    self._interaction_dialog_open=True
    try: return _original_open_details_for_row(self,row,column)
    finally: self._interaction_dialog_open=False; _render_after_interaction(self)
def _safe_set_destination_for_row(self,row):
    self._interaction_dialog_open=True
    try: return _original_set_destination_for_row(self,row)
    finally: self._interaction_dialog_open=False; _render_after_interaction(self)
def _safe_set_status_for_row(self,row,status):
    self._interaction_dialog_open=True
    try: return _original_set_status_for_row(self,row,status)
    finally: self._interaction_dialog_open=False; _render_after_interaction(self)
def _confirmed_cleanup_scanned_services(self):
    answer=QMessageBox.question(self,"Nettoyage des services","Voulez-vous vraiment supprimer tous les services détectés par les scans ?\n\nLes comptes Google et leurs autorisations ne seront pas supprimés.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
    return _original_cleanup_scanned_services(self) if answer==QMessageBox.Yes else None

def _polish_service_details_dialog(self):
    self.setMinimumWidth(700)
    self.setMaximumWidth(820)
    root=self.layout()
    if root:
        root.setContentsMargins(22,22,22,22)
        root.setSpacing(16)
    card=self.findChild(QFrame,"serviceDetailsCard")
    if not card:return
    card_layout=card.layout()
    if card_layout:
        card_layout.setContentsMargins(22,22,22,22)
        card_layout.setSpacing(16)
    for label in card.findChildren(QLabel):
        if label.property("class")=="detailLabel": label.setMinimumWidth(125)
    if hasattr(self,"status_combo"): self.status_combo.setMinimumHeight(38)
    if hasattr(self,"destination_input"): self.destination_input.setMinimumHeight(38)
    if hasattr(self,"notes_input"): self.notes_input.setMinimumHeight(82)
    if hasattr(self,"save_button"): self.save_button.setMinimumWidth(120)
    for button in self.findChildren(QPushButton): button.setMinimumHeight(38)

_original_details_init=ServiceDetailsDialog.__init__
def _styled_details_init(self,details,parent=None):
    _original_details_init(self,details,parent)
    _polish_service_details_dialog(self)
ServiceDetailsDialog.__init__=_styled_details_init

services_module.ServicesPage._schedule_live_render=_safe_schedule_live_render
services_module.ServicesPage._render_live_rows_deferred=_safe_render_live_rows_deferred
services_module.ServicesPage._show_service_context_menu=_safe_show_service_context_menu
services_module.ServicesPage._open_details_for_row=_safe_open_details_for_row
services_module.ServicesPage._set_destination_for_row=_safe_set_destination_for_row
services_module.ServicesPage._set_status_for_row=_safe_set_status_for_row
services_module.ServicesPage.cleanup_scanned_services=_confirmed_cleanup_scanned_services

_original_export_init=ExportPage.__init__
def _export_init_with_refresh(self):
    _original_export_init(self)
    refresh_button=QPushButton("↻")
    refresh_button.setToolTip("Actualiser les analyses sauvegardées")
    refresh_button.setFixedWidth(42)
    refresh_button.setMinimumHeight(38)
    refresh_button.clicked.connect(self.refresh)
    form=self.scan_combo.parentWidget().layout()
    index=form.indexOf(self.scan_combo)
    row=QHBoxLayout()
    row.addWidget(self.scan_combo,1)
    row.addWidget(refresh_button)
    form.removeWidget(self.scan_combo)
    form.insertLayout(index,row)
    self.scan_refresh_button=refresh_button
ExportPage.__init__=_export_init_with_refresh

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Mail Migration"); self.resize(1180,760); self.setStyleSheet(STYLE)
        self.account_state=AccountState(); self.account_state.changed.connect(self._account_changed)
        root=QWidget(); root_layout=QVBoxLayout(root); root_layout.setContentsMargins(12,12,12,12); root_layout.setSpacing(0)
        content=QHBoxLayout(); content.setSpacing(12)
        sidebar=QVBoxLayout(); sidebar.setSpacing(8); title=QLabel("Mail Migration"); title.setObjectName("title"); sidebar.addWidget(title)
        self.stack=QStackedWidget(); self.dashboard=DashboardPage(); self.accounts=AccountsPage(self.set_active_account); self.services=ServicesPage(); self.export_page=ExportPage(); self.settings_page=SettingsPage()
        self.accounts.scan_started.connect(self.services.start_live_scan); self.accounts.scan_detection.connect(self.services.update_live_detection); self.accounts.scan_finished_live.connect(self._scan_finished)
        self.stack.addWidget(self.dashboard); self.stack.addWidget(self.accounts); self.stack.addWidget(self.services); self.stack.addWidget(self.export_page); self.stack.addWidget(self.settings_page)
        for text,index in [("Dashboard",0),("Comptes Google",1),("Services",2),("Exportation",3)]:
            button=QPushButton(text); button.clicked.connect(lambda checked=False,i=index:self._navigate(i)); sidebar.addWidget(button)
        sidebar.addStretch()
        settings_button=QPushButton("⚙ Paramètres"); settings_button.clicked.connect(lambda:self._navigate(4)); sidebar.addWidget(settings_button)
        content.addLayout(sidebar,1); content.addWidget(self.stack,4); root_layout.addLayout(content,1)
        bottom=QFrame(); bottom.setFixedHeight(36); bottom_layout=QHBoxLayout(bottom); bottom_layout.setContentsMargins(0,0,0,0); bottom_label=QLabel("Lecture Gmail uniquement"); bottom_label.setObjectName("muted"); bottom_label.setAlignment(Qt.AlignCenter); bottom_layout.addStretch(); bottom_layout.addWidget(bottom_label); bottom_layout.addStretch(); root_layout.addWidget(bottom)
        self.setCentralWidget(root); self.refresh_all()
    def _navigate(self,index):
        self.stack.setCurrentIndex(index)
        if index==3: self.export_page.refresh()
    def _scan_finished(self,mode):
        self.accounts.refresh(self.active_account_id); self.services.finish_live_scan(mode); self.export_page.refresh()
    @property
    def active_account_id(self): return self.account_state.account_id
    def set_active_account(self,account_id): self.account_state.set_account(account_id)
    def _account_changed(self,account_id):
        self.dashboard.set_active_account(account_id); self.services.set_active_account(account_id); self.export_page.refresh()
    def refresh_all(self): self.accounts.refresh(self.active_account_id); self.dashboard.refresh(); self.services.refresh(); self.export_page.refresh()

def run():
    setup_logging(); init_db(); app=QApplication(sys.argv); window=MainWindow(); window.show(); sys.exit(app.exec())