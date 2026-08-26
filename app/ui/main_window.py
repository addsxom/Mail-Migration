import sys
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QMessageBox
)
from app.core.logger import setup_logging
from app.database.database import init_db
from .dashboard import DashboardPage
from .accounts import AccountsPage
from .services import ServicesPage

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
QLabel#title {
    font-size: 22px;
    font-weight: 700;
}
QLabel#muted {
    color: #9AA2AF;
}
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mail Migration")
        self.resize(1180, 760)
        self.setStyleSheet(STYLE)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)

        sidebar = QVBoxLayout()
        title = QLabel("Mail Migration")
        title.setObjectName("title")
        sidebar.addWidget(title)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.accounts = AccountsPage(self.refresh_all)
        self.services = ServicesPage()

        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.accounts)
        self.stack.addWidget(self.services)

        for text, index in [
            ("Dashboard", 0),
            ("Comptes Google", 1),
            ("Services", 2),
        ]:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, i=index: self.stack.setCurrentIndex(i))
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

    def refresh_all(self):
        self.dashboard.refresh()
        self.accounts.refresh()
        self.services.refresh()

def run():
    setup_logging()
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
