from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame, QProgressBar
from app.database.database import get_session
from app.database.repositories import dashboard_counts, get_account


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("title")
        layout.addWidget(title)

        self.account_label = QLabel("Tous les comptes")
        self.account_label.setObjectName("muted")
        layout.addWidget(self.account_label)

        self.summary_card = QFrame()
        self.summary_card.setStyleSheet(
            "QFrame { background:#171B22; border:1px solid #303846; border-radius:14px; }"
        )
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(20, 18, 20, 18)
        summary_layout.setSpacing(12)

        header = QHBoxLayout()
        summary_title = QLabel("Progression de la migration")
        summary_title.setStyleSheet("font-size:16px;font-weight:700;")
        header.addWidget(summary_title)
        header.addStretch()
        self.progress_label = QLabel("0 / 0 migré · 0 %")
        self.progress_label.setObjectName("muted")
        header.addWidget(self.progress_label)
        summary_layout.addLayout(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(9)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background:#252B35; border:none; border-radius:4px; }"
            "QProgressBar::chunk { background:#66758C; border-radius:4px; }"
        )
        summary_layout.addWidget(self.progress_bar)
        layout.addWidget(self.summary_card)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        layout.addLayout(self.grid)
        layout.addStretch()

    def set_active_account(self, account_id):
        self.active_account_id = account_id
        self.refresh()

    def _make_card(self, value, label):
        card = QFrame()
        card.setMinimumHeight(92)
        card.setStyleSheet(
            "QFrame { background:#1A1E26; border:1px solid #2A303B; border-radius:12px; }"
        )
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(4)
        value_label = QLabel(str(value))
        value_label.setStyleSheet("font-size:26px;font-weight:700;")
        text_label = QLabel(label)
        text_label.setStyleSheet("color:#9AA2AF;")
        box.addWidget(value_label)
        box.addWidget(text_label)
        return card

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        session = get_session()
        try:
            accounts, services, migrated, abandoned, to_check, to_migrate = dashboard_counts(session)
            account = get_account(session, self.active_account_id) if self.active_account_id else None
        finally:
            session.close()

        if account:
            self.account_label.setText(
                f"Compte actif : {account.display_name or account.email} — {account.email}"
            )
        else:
            self.account_label.setText("Tous les comptes")

        total = int(services or 0)
        migrated = int(migrated or 0)
        abandoned = int(abandoned or 0)
        to_check = int(to_check or 0)
        to_migrate = int(to_migrate or 0)

        percentage = round((migrated / total) * 100) if total else 0
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(f"{migrated} / {total} migré{'s' if migrated != 1 else ''} · {percentage} %")

        cards = [
            (total, "Services détectés"),
            (to_check, "À vérifier"),
            (to_migrate, "À migrer"),
            (migrated, "Migrés"),
            (abandoned, "Abandonnés"),
        ]
        for column, (value, label) in enumerate(cards):
            self.grid.addWidget(self._make_card(value, label), 0, column)
