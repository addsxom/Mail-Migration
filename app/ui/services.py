from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from app.database.database import get_session
from app.database.repositories import get_accounts, get_account_services


class ServicesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None
        self.live_scan = False
        self.live_rows = {}

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

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Compte", "Service", "Catégorie", "Confiance", "Traces", "Statut"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def set_active_account(self, account_id):
        self.active_account_id = account_id
        self.live_rows.clear()
        self.live_scan = False
        self.scan_label.setText("")
        self.refresh()

    def start_live_scan(self, account_id):
        self.active_account_id = account_id
        self.live_scan = True
        self.live_rows.clear()
        self.scan_label.setText("● Scan en cours — les services apparaissent en temps réel")
        self.refresh()

    def update_live_detection(self, account_id, data):
        if not self.live_scan or account_id != self.active_account_id:
            return
        self.live_rows[data["name"]] = {
            "account_id": account_id,
            "name": data["name"],
            "category": data.get("category", "Autre"),
            "score": float(data.get("score", 0)),
            "count": int(data.get("count", 0)),
            "status": "À vérifier",
        }
        self._render_live_rows()

    def finish_live_scan(self, account_id):
        if account_id != self.active_account_id:
            return
        self.live_scan = False
        self.scan_label.setText("")
        self.refresh()

    def _render_live_rows(self):
        session = get_session()
        try:
            account = session.get(__import__("app.database.models", fromlist=["GoogleAccount"]).GoogleAccount, self.active_account_id)
            email = account.email if account else ""
        finally:
            session.close()

        rows = [
            (email, item["name"], item["category"], f'{item["score"]:.0f} %', str(item["count"]), item["status"])
            for item in sorted(self.live_rows.values(), key=lambda x: (-x["score"], x["name"].lower()))
        ]
        self._set_rows(rows)

    def _set_rows(self, rows):
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def refresh(self):
        session = get_session()
        try:
            accounts = get_accounts(session)
            rows = []
            selected_account = None
            for account in accounts:
                if self.active_account_id is not None and account.id != self.active_account_id:
                    continue
                if account.id == self.active_account_id:
                    selected_account = account
                for link in get_account_services(session, account.id):
                    rows.append((
                        account.email,
                        link.service.name,
                        link.service.category,
                        f"{link.confidence_score:.0f} %",
                        str(link.trace_count),
                        link.status,
                    ))
        finally:
            session.close()

        if self.active_account_id is None:
            self.account_label.setText("Tous les comptes")
        elif selected_account:
            self.account_label.setText(f"Compte sélectionné : {selected_account.email}")
        else:
            self.account_label.setText("Compte sélectionné introuvable")

        if not self.live_scan:
            self._set_rows(rows)
