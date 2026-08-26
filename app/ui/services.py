from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from app.database.database import get_session
from app.database.repositories import get_accounts, get_account_services

class ServicesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Inventaire des services")
        title.setObjectName("title")
        layout.addWidget(title)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Compte", "Service", "Catégorie", "Confiance", "Traces", "Statut"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def refresh(self):
        session = get_session()
        try:
            rows = []
            for account in get_accounts(session):
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

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(value))
