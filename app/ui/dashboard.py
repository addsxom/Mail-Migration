from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame
from app.database.database import get_session
from app.database.repositories import dashboard_counts

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Dashboard")
        title.setObjectName("title")
        layout.addWidget(title)

        self.grid = QGridLayout()
        layout.addLayout(self.grid)
        layout.addStretch()

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        session = get_session()
        try:
            accounts, services, migrated, abandoned, to_check = dashboard_counts(session)
        finally:
            session.close()

        values = [
            ("Comptes Google", accounts),
            ("Services détectés", services),
            ("Migrés", migrated),
            ("Abandonnés", abandoned),
            ("À vérifier", to_check),
        ]
        for i, (label, value) in enumerate(values):
            card = QFrame()
            card.setStyleSheet("QFrame { background:#1A1E26; border:1px solid #2A303B; border-radius:12px; }")
            box = QVBoxLayout(card)
            v = QLabel(str(value))
            v.setStyleSheet("font-size:28px;font-weight:700;")
            l = QLabel(label)
            l.setStyleSheet("color:#9AA2AF;")
            box.addWidget(v)
            box.addWidget(l)
            self.grid.addWidget(card, 0, i)
