from datetime import datetime

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
    QWidget, QLineEdit, QStyledItemDelegate, QStyleOptionViewItem, QStyle,
)
from sqlalchemy import delete, select

from app.database.database import get_session
from app.database.models import GoogleAccount, AccountService, ScanTrace
from app.database.repositories import get_accounts, get_account_services


class ServiceDetailsDialog(QDialog):
    def __init__(self, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Détails — {details.get('name', 'Service')}")
        self.setModal(True)
        self.setMinimumWidth(540)
        self.setMaximumWidth(700)

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
            QLabel.signalValue { color: #E7EAF0; }
            QLabel.scoreValue { font-size: 18px; font-weight: 700; }
            QPushButton { padding: 8px 16px; border-radius: 8px; }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        title = QLabel(details.get("name", "Service"))
        title.setObjectName("serviceDetailsTitle")
        card_layout.addWidget(title)

        subtitle = QLabel(details.get("category", "Autre"))
        subtitle.setObjectName("serviceDetailsSubtitle")
        card_layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

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
            label = QLabel(label_text)
            label.setProperty("class", "detailLabel")
            value = QLabel(str(value_text or "—"))
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if label_text == "Confiance":
                value.setObjectName("scoreValue")
            grid.addWidget(label, row, 0, Qt.AlignTop)
            grid.addWidget(value, row, 1)

        row = len(fields)
        signal_label = QLabel("Signaux de détection")
        signal_label.setProperty("class", "detailLabel")
        signal_value = QLabel(self._format_signals(details.get("signals") or []))
        signal_value.setObjectName("signalValue")
        signal_value.setWordWrap(True)
        signal_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(signal_label, row, 0, Qt.AlignTop)
        grid.addWidget(signal_value, row, 1)

        row += 1
        score_label = QLabel("Détail du score")
        score_label.setProperty("class", "detailLabel")
        score_value = QLabel(self._format_score_breakdown(details.get("signals") or []))
        score_value.setObjectName("signalValue")
        score_value.setWordWrap(True)
        score_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(score_label, row, 0, Qt.AlignTop)
        grid.addWidget(score_value, row, 1)

        row += 1
        reliability_label = QLabel("Fiabilité de la source")
        reliability_label.setProperty("class", "detailLabel")
        reliability_value = QLabel(self._format_reliability(details.get("reliability") or {}))
        reliability_value.setObjectName("signalValue")
        reliability_value.setWordWrap(True)
        reliability_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(reliability_label, row, 0, Qt.AlignTop)
        grid.addWidget(reliability_value, row, 1)

        card_layout.addLayout(grid)
        root.addWidget(card)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button, 0, Qt.AlignRight)

    @staticmethod
    def _format_score(value):
        return "—" if value is None else f"{float(value):.0f} %"

    @staticmethod
    def _format_date(value):
        if not value:
            return "—"
        if isinstance(value, datetime):
            return value.astimezone().strftime("%d/%m/%Y %H:%M")
        return str(value)

    @staticmethod
    def _format_signals(signals):
        labels = {
            "domain": "✓ Domaine correspondant",
            "sender": "✓ Expéditeur correspondant",
            "subject": "✓ Sujet correspondant",
            "keyword": "✓ Mot-clé correspondant",
        }
        if not signals:
            return "Aucun signal détaillé disponible"
        return "\n".join(labels.get(signal, f"✓ {signal}") for signal in signals)

    @staticmethod
    def _format_score_breakdown(signals):
        weights = {"domain": 50, "sender": 25, "subject": 15, "keyword": 10}
        labels = {
            "domain": "Domaine exact",
            "sender": "Expéditeur connu",
            "subject": "Sujet correspondant",
            "keyword": "Mot-clé correspondant",
        }
        unique = set(signals)
        lines = [
            f"{'✓' if key in unique else '✗'} {labels[key]}    +{weights[key] if key in unique else 0}"
            for key in ("domain", "sender", "subject", "keyword")
        ]
        total = min(100, sum(weights[key] for key in unique if key in weights))
        return "\n".join(lines) + f"\n────────────────────────\nTotal                    {total} %"

    @staticmethod
    def _format_reliability(reliability):
        if not reliability:
            return "Aucune information de fiabilité disponible"

        lines = []
        lines.append("✓ Domaine officiel" if reliability.get("official_domain") else "✗ Domaine officiel non confirmé")
        lines.append("✓ Expéditeur connu" if reliability.get("known_sender") else "✗ Expéditeur non reconnu")
        lines.append("")
        lines.append("Authentification")

        if not reliability.get("authentication_available"):
            lines.extend(["○ SPF — non disponible", "○ DKIM — non disponible", "○ DMARC — non disponible"])
        else:
            for key, label in (("spf", "SPF"), ("dkim", "DKIM"), ("dmarc", "DMARC")):
                value = reliability.get(key)
                lines.append(f"{'✓' if value else '✗'} {label} — {'pass' if value else 'échec'}")

        return "\n".join(lines)


class ServiceTableDelegate(QStyledItemDelegate):
    """Draws one continuous rounded background for the complete service row."""

    def paint(self, painter, option, index):
        table = self.parent()
        hovered_row = getattr(table, "hovered_row", -1)
        row = index.row()
        column = index.column()

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        if column == 0:
            row_rect = QRectF(
                3,
                option.rect.top() + 4,
                max(0, table.viewport().width() - 6),
                max(0, option.rect.height() - 8),
            )
            bg = QColor(48, 58, 72) if row == hovered_row else QColor(29, 34, 43)
            path = QPainterPath()
            path.addRoundedRect(row_rect, 9, 9)
            painter.fillPath(path, bg)

        text_option = QStyleOptionViewItem(option)
        text_option.state &= ~QStyle.State_MouseOver
        text_option.state &= ~QStyle.State_Selected
        text_option.rect = option.rect.adjusted(8, 0, -8, 0)
        text_option.backgroundBrush = Qt.NoBrush
        super().paint(painter, text_option, index)
        painter.restore()


class ServicesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None
        self.live_scan = False
        self.live_account_ids = set()
        self.live_rows = {}
        self.row_details = []
        self.live_account_emails = {}
        self.hovered_row = -1
        self._all_rows = []
        self._all_details = []

        layout = QVBoxLayout(self)
        title = QLabel("Inventaire des services")
        title.setObjectName("title")
        layout.addWidget(title)

        self.account_label = QLabel("Tous les comptes")
        self.account_label.setObjectName("muted")
        layout.addWidget(self.account_label)

        self.scan_label = QLabel("")
        self.scan_label.setObjectName("muted")
        layout.addWidget(self.scan_label)

        search_container = QFrame()
        search_container.setObjectName("serviceSearchContainer")
        search_container.setStyleSheet("""
            QFrame#serviceSearchContainer {
                border: 1px solid #303846;
                border-radius: 10px;
                background: #171b22;
            }
            QFrame#serviceSearchContainer:focus-within {
                border: 1px solid #58677d;
            }
            QLabel#serviceSearchIcon {
                border: none;
                background: transparent;
                padding-left: 12px;
                padding-right: 4px;
                font-size: 17px;
            }
            QLineEdit#serviceSearchInput {
                border: none;
                background: transparent;
                padding: 0 10px 0 4px;
            }
        """)
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)

        search_icon = QLabel("🔎")
        search_icon.setObjectName("serviceSearchIcon")
        search_icon.setAlignment(Qt.AlignCenter)
        search_layout.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("serviceSearchInput")
        self.search_input.setPlaceholderText("Rechercher un service, compte ou catégorie...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(38)
        self.search_input.textChanged.connect(self._filter_services)
        search_layout.addWidget(self.search_input, 1)
        layout.addWidget(search_container)

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
        self.table.setShowGrid(False)
        self.table.setMouseTracking(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                gridline-color: transparent;
            }
            QTableWidget::item {
                background: transparent;
                border: none;
                outline: none;
            }
            QTableWidget::item:selected {
                background: transparent;
                color: inherit;
            }
            QTableWidget::item:focus {
                outline: none;
            }
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setItemDelegate(ServiceTableDelegate(self.table))
        self.table.cellClicked.connect(self._clear_table_click_state)
        self.table.cellDoubleClicked.connect(self._open_details_for_row)
        self.table.viewport().installEventFilter(self)
        layout.addWidget(self.table)

    def _clear_table_click_state(self, _row, _column):
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.table.viewport().update()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport():
            if event.type() == event.Type.MouseMove:
                index = self.table.indexAt(event.position().toPoint())
                new_row = index.row() if index.isValid() else -1
                if new_row != self.hovered_row:
                    self.hovered_row = new_row
                    self.table.viewport().update()
            elif event.type() == event.Type.Leave:
                if self.hovered_row != -1:
                    self.hovered_row = -1
                    self.table.viewport().update()
        return super().eventFilter(watched, event)

    def set_active_account(self, account_id):
        if self.live_scan:
            return
        self.active_account_id = account_id
        self.live_rows.clear()
        self.live_account_ids.clear()
        self.live_account_emails.clear()
        self.scan_label.setText("")
        self.refresh()

    @staticmethod
    def _get_account_email(account_id):
        session = get_session()
        try:
            account = session.get(GoogleAccount, account_id)
            return account.email if account else ""
        finally:
            session.close()

    def _open_details_for_row(self, row, _column):
        if not (0 <= row < len(self.row_details)):
            return
        details = dict(self.row_details[row])
        session = get_session()
        try:
            account_service_id = details.get("account_service_id")
            if account_service_id:
                traces = session.scalars(select(ScanTrace).where(ScanTrace.account_service_id == account_service_id)).all()
                signals = set(details.get("signals") or [])
                reliability = dict(details.get("reliability") or {})
                for trace in traces:
                    if trace.signal_type:
                        signals.add(trace.signal_type)
                    if trace.signal_value:
                        signals.update(part.strip() for part in str(trace.signal_value).split(",") if part.strip())
                details["signals"] = sorted(signals)
                if not reliability:
                    reliability = {
                        "official_domain": "domain" in signals,
                        "known_sender": "sender" in signals,
                        "authentication_available": False,
                        "spf": None,
                        "dkim": None,
                        "dmarc": None,
                    }
                    details["reliability"] = reliability
        finally:
            session.close()
        ServiceDetailsDialog(details, self).exec()

    def start_live_scan(self, account_id):
        if not self.live_scan:
            self.live_scan = True
            self.live_rows.clear()
            self.live_account_ids.clear()
            self.live_account_emails.clear()
        self.live_account_ids.add(account_id)
        email = self._get_account_email(account_id)
        if email:
            self.live_account_emails[account_id] = email
        self.scan_label.setText(f"● Scan en cours — {len(self.live_account_ids)} compte(s) — résultats en temps réel")
        self._render_live_rows()

    def update_live_detection(self, account_id, data):
        if not self.live_scan or account_id not in self.live_account_ids:
            return
        key = (account_id, data.get("service_id") or data.get("name", "").strip().lower())
        email = data.get("account_email") or self.live_account_emails.get(account_id, "")
        self.live_rows[key] = {
            "account_id": account_id,
            "account_email": email,
            "name": data.get("name", "Service inconnu"),
            "category": data.get("category", "Autre"),
            "score": float(data.get("score", 0)),
            "count": int(data.get("count", 0)),
            "status": data.get("status", "À vérifier"),
            "priority": data.get("priority", "Normale"),
            "destination": data.get("destination_email"),
            "notes": data.get("notes"),
            "first_detected_at": data.get("first_detected_at"),
            "last_detected_at": data.get("last_detected_at"),
            "signals": data.get("signals", []),
            "reliability": data.get("reliability", {}),
        }
        self._render_live_rows()

    def finish_live_scan(self, mode):
        if not self.live_scan:
            return
        if mode == -1:
            self.keep_live_results_after_cancel()
            return
        self.live_scan = False
        self.scan_label.setText("")
        self.refresh()
        self.live_rows.clear()
        self.live_account_ids.clear()
        self.live_account_emails.clear()

    def keep_live_results_after_cancel(self):
        self.live_scan = False
        self.scan_label.setText("Scan annulé — résultats déjà détectés conservés")
        self._render_live_rows()
        self.live_account_ids.clear()
        self.live_account_emails.clear()

    def _render_live_rows(self):
        rows, details = [], []
        for item in sorted(self.live_rows.values(), key=lambda x: (-x["score"], x["name"].lower(), x["account_email"].lower())):
            rows.append((item.get("account_email", ""), item["name"], item["category"], f'{item["score"]:.0f} %', str(item["count"]), item["status"]))
            details.append(item)
        self._set_rows(rows, details)

    def _set_rows(self, rows, details=None):
        self._all_rows = list(rows)
        self._all_details = list(details or [])
        self._filter_services(self.search_input.text())

    def _filter_services(self, text):
        query = (text or "").strip().casefold()
        if not query:
            rows = self._all_rows
            details = self._all_details
        else:
            rows, details = [], []
            for row, detail in zip(self._all_rows, self._all_details):
                haystack = " ".join(str(value) for value in row).casefold()
                if query in haystack:
                    rows.append(row)
                    details.append(detail)

        self.row_details = details
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
                self.table.setItem(r, c, item)
        self.hovered_row = -1
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.table.viewport().update()

    def refresh(self):
        session = get_session()
        rows, details, selected_account = [], [], None
        try:
            for account in get_accounts(session):
                if self.active_account_id is not None and account.id != self.active_account_id:
                    continue
                if account.id == self.active_account_id:
                    selected_account = account
                for link in get_account_services(session, account.id):
                    service = link.service
                    details.append({
                        "account_id": account.id,
                        "account_service_id": link.id,
                        "account_email": account.email,
                        "name": service.name,
                        "category": service.category,
                        "subcategory": service.subcategory,
                        "score": link.confidence_score,
                        "count": link.trace_count,
                        "status": link.status,
                        "priority": link.priority,
                        "destination": link.destination_email,
                        "notes": link.notes,
                        "first_detected_at": link.first_detected_at,
                        "last_detected_at": link.last_detected_at,
                        "signals": [],
                        "reliability": {},
                    })
                    rows.append((account.email, service.name, service.category, f"{link.confidence_score:.0f} %", str(link.trace_count), link.status))
        finally:
            session.close()

        self.account_label.setText("Tous les comptes" if self.active_account_id is None else (f"Compte sélectionné : {selected_account.email}" if selected_account else "Compte sélectionné introuvable"))
        if not self.live_scan:
            self._set_rows(rows, details)

    def cleanup_scanned_services(self):
        answer = QMessageBox.question(self, "Nettoyage des services", "Supprimer tous les services détectés par les scans ?\n\nLes comptes Google et leurs autorisations ne seront pas supprimés.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        session = get_session()
        try:
            session.execute(delete(ScanTrace))
            session.execute(delete(AccountService))
            session.commit()
        except Exception as exc:
            session.rollback()
            QMessageBox.critical(self, "Nettoyage", f"Impossible de nettoyer les résultats : {exc}")
            return
        finally:
            session.close()
        self.live_rows.clear()
        self.live_account_ids.clear()
        self.live_account_emails.clear()
        self.live_scan = False
        self.scan_label.setText("")
        self.refresh()
