from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget,
)
from sqlalchemy import delete

from app.database.database import get_session
from app.database.models import GoogleAccount, AccountService, ScanTrace
from app.database.repositories import get_accounts, get_account_services


class ServiceDetailsDialog(QDialog):
    """Compact, read-only details card opened by double-click."""
    def __init__(self, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Détails — {details.get('name', 'Service')}")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(600)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        card = QFrame()
        card.setObjectName("serviceDetailsCard")
        card.setStyleSheet("""
            QFrame#serviceDetailsCard { border: 1px solid #303846; border-radius: 14px; background: #171b22; }
            QLabel#serviceDetailsTitle { font-size: 22px; font-weight: 700; }
            QLabel#serviceDetailsSubtitle { color: #9AA2AF; }
            QLabel.detailLabel { color: #9AA2AF; font-size: 12px; }
            QPushButton { padding: 8px 16px; border-radius: 8px; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)
        title = QLabel(details.get("name", "Service")); title.setObjectName("serviceDetailsTitle"); card_layout.addWidget(title)
        subtitle = QLabel(details.get("category", "Autre")); subtitle.setObjectName("serviceDetailsSubtitle"); card_layout.addWidget(subtitle)
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(10)
        fields = [
            ("Compte Gmail", details.get("account_email", "—")),
            ("Confiance", self._format_score(details.get("score"))),
            ("Traces", str(details.get("count", 0))),
            ("Statut", details.get("status", "À vérifier")),
            ("Priorité", details.get("priority", "Normale")),
            ("Destination", details.get("destination", "—")),
            ("Première détection", self._format_date(details.get("first_detected_at"))),
            ("Dernière détection", self._format_date(details.get("last_detected_at"))),
            ("Sous-catégorie", details.get("subcategory", "—")),
            ("Notes", details.get("notes", "—")),
        ]
        for row, (label_text, value_text) in enumerate(fields):
            label = QLabel(label_text); label.setProperty("class", "detailLabel")
            value = QLabel(str(value_text or "—")); value.setWordWrap(True); value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(label, row, 0, Qt.AlignTop); grid.addWidget(value, row, 1)
        card_layout.addLayout(grid); root.addWidget(card)
        close_button = QPushButton("Fermer"); close_button.clicked.connect(self.accept); root.addWidget(close_button, 0, Qt.AlignRight)

    @staticmethod
    def _format_score(value):
        return "—" if value is None else f"{float(value):.0f} %"

    @staticmethod
    def _format_date(value):
        if not value: return "—"
        if isinstance(value, datetime): return value.astimezone().strftime("%d/%m/%Y %H:%M")
        return str(value)


class ServicesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None
        self.live_scan = False
        self.live_account_ids = set()
        self.live_rows = {}
        self.row_details = []
        self.live_account_emails = {}

        layout = QVBoxLayout(self)
        title = QLabel("Inventaire des services"); title.setObjectName("title"); layout.addWidget(title)
        self.account_label = QLabel("Tous les comptes"); self.account_label.setObjectName("muted"); layout.addWidget(self.account_label)
        self.scan_label = QLabel(""); self.scan_label.setObjectName("muted"); layout.addWidget(self.scan_label)

        actions = QHBoxLayout()
        actions.addStretch()
        self.cleanup_button = QPushButton("🧹 Nettoyage")
        self.cleanup_button.setToolTip("Supprimer les résultats issus des scans")
        self.cleanup_button.clicked.connect(self.cleanup_scanned_services)
        actions.addWidget(self.cleanup_button)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Compte", "Service", "Catégorie", "Confiance", "Traces", "Statut"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.cellDoubleClicked.connect(self._open_details_for_row)
        layout.addWidget(self.table)

    def set_active_account(self, account_id):
        if self.live_scan:
            return
        self.active_account_id = account_id
        self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear()
        self.scan_label.setText("")
        self.refresh()

    def start_live_scan(self, account_id):
        if not self.live_scan:
            self.live_scan = True
            self.live_rows.clear()
            self.live_account_ids.clear()
            self.live_account_emails.clear()
        self.live_account_ids.add(account_id)
        email = self._get_account_email(account_id)
        if email: self.live_account_emails[account_id] = email
        self.scan_label.setText(f"● Scan en cours — {len(self.live_account_ids)} compte(s) — résultats en temps réel")
        self._render_live_rows()

    @staticmethod
    def _get_account_email(account_id):
        session = get_session()
        try:
            account = session.get(GoogleAccount, account_id)
            return account.email if account else ""
        finally:
            session.close()

    def update_live_detection(self, account_id, data):
        if not self.live_scan or account_id not in self.live_account_ids:
            return
        key = (account_id, data.get("service_id") or data.get("name", "").strip().lower())
        account_email = data.get("account_email") or self.live_account_emails.get(account_id, "")
        self.live_rows[key] = {
            "account_id": account_id, "account_email": account_email,
            "name": data.get("name", "Service inconnu"), "category": data.get("category", "Autre"),
            "subcategory": data.get("subcategory"), "score": float(data.get("score", 0)),
            "count": int(data.get("count", 0)), "status": data.get("status", "À vérifier"),
            "priority": data.get("priority", "Normale"), "destination": data.get("destination_email"),
            "notes": data.get("notes"), "first_detected_at": data.get("first_detected_at"),
            "last_detected_at": data.get("last_detected_at"),
        }
        self._render_live_rows()

    def finish_live_scan(self, account_id):
        # Called once after the whole multi-account job, or after cancellation.
        if not self.live_scan: return
        self.live_scan = False
        self.scan_label.setText("")
        # Keep live_rows visible on cancellation; refresh only after a completed scan.
        self.refresh()
        self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear()

    def keep_live_results_after_cancel(self):
        self.live_scan = False
        self.scan_label.setText("Scan annulé — résultats déjà détectés conservés")
        self._render_live_rows()
        self.live_account_ids.clear(); self.live_account_emails.clear()

    def _render_live_rows(self):
        rows, details = [], []
        for item in sorted(self.live_rows.values(), key=lambda x: (-x["score"], x["name"].lower(), x["account_email"].lower())):
            rows.append((item.get("account_email", ""), item["name"], item["category"], f'{item["score"]:.0f} %', str(item["count"]), item["status"]))
            details.append(item)
        self._set_rows(rows, details)

    def _set_rows(self, rows, details=None):
        self.row_details = details or []
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
                self.table.setItem(r, c, item)

    def _open_details_for_row(self, row, _column):
        if 0 <= row < len(self.row_details): ServiceDetailsDialog(self.row_details[row], self).exec()

    def refresh(self):
        session = get_session()
        rows, details, selected_account = [], [], None
        try:
            accounts = get_accounts(session)
            for account in accounts:
                if self.active_account_id is not None and account.id != self.active_account_id: continue
                if account.id == self.active_account_id: selected_account = account
                for link in get_account_services(session, account.id):
                    service = link.service
                    details.append({
                        "account_id": account.id, "account_email": account.email, "name": service.name,
                        "category": service.category, "subcategory": service.subcategory, "score": link.confidence_score,
                        "count": link.trace_count, "status": link.status, "priority": link.priority,
                        "destination": link.destination_email, "notes": link.notes,
                        "first_detected_at": link.first_detected_at, "last_detected_at": link.last_detected_at,
                    })
                    rows.append((account.email, service.name, service.category, f"{link.confidence_score:.0f} %", str(link.trace_count), link.status))
        finally:
            session.close()
        self.account_label.setText("Tous les comptes" if self.active_account_id is None else (f"Compte sélectionné : {selected_account.email}" if selected_account else "Compte sélectionné introuvable"))
        if not self.live_scan: self._set_rows(rows, details)

    def cleanup_scanned_services(self):
        answer = QMessageBox.question(
            self, "Nettoyage des services",
            "Supprimer tous les services détectés par les scans ?\n\nLes comptes Google et leurs autorisations ne seront pas supprimés.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes: return
        session = get_session()
        try:
            session.execute(delete(ScanTrace))
            session.execute(delete(AccountService))
            session.commit()
        except Exception as exc:
            session.rollback()
            QMessageBox.critical(self, "Nettoyage", f"Impossible de nettoyer les résultats : {exc}")
            return
        self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear(); self.live_scan = False
        self.scan_label.setText("")
        self.refresh()
