from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame
from app.database.database import get_session
from app.database.repositories import dashboard_counts, get_account


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None
        layout = QVBoxLayout(self)
        title = QLabel("Dashboard")
        title.setObjectName("title")
        layout.addWidget(title)

        self.account_label = QLabel("Compte actif : aucun")
        self.account_label.setObjectName("muted")
        layout.addWidget(self.account_label)

        self.grid = QGridLayout()
        layout.addLayout(self.grid)
        layout.addStretch()

    def set_active_account(self, account_id):
        self.active_account_id = account_id
        self.refresh()

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        session = get_session()
        try:
            accounts, services, migrated, abandoned, to_check = dashboard_counts(session)
            account = get_account(session, self.active_account_id) if self.active_account_id else None
        finally:
            session.close()

        if account:
            self.account_label.setText(
                f"Compte actif : {account.display_name or account.email} — {account.email}"
            )
        else:
            self.account_label.setText("Compte actif : aucun")

        values = [
            ("Comptes Google", accounts),
            ("Services détectés", services),
            ("Migrés", migrated),
            ("Abandonnés", abandoned),
            ("À vérifier", to_check),
        ]
        for i, (label, value) in enumerate(values):
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background:#1A1E26; border:1px solid #2A303B; border-radius:12px; }"
            )
            box = QVBoxLayout(card)
            v = QLabel(str(value))
            v.setStyleSheet("font-size:28px;font-weight:700;")
            l = QLabel(label)
            l.setStyleSheet("color:#9AA2AF;")
            box.addWidget(v)
            box.addWidget(l)
            self.grid.addWidget(card, 0, i)
