from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from app.database.database import get_session
from app.database.repositories import get_accounts, get_account_services


class ServicesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None
        layout = QVBoxLayout(self)
        title = QLabel("Inventaire des services")
        title.setObjectName("title")
        layout.addWidget(title)

        self.account_label = QLabel("Tous les comptes")
        self.account_label.setObjectName("muted")
        layout.addWidget(self.account_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Compte", "Service", "Catégorie", "Confiance", "Traces", "Statut"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def set_active_account(self, account_id):
        self.active_account_id = account_id
        self.refresh()

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
            self.account_label.setText(
                f"Compte sélectionné : {selected_account.email}"
            )
        else:
            self.account_label.setText("Compte sélectionné introuvable")

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(value))
