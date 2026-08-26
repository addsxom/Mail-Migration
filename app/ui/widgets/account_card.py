from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel

class AccountCard(QFrame):
    def __init__(self, email):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(email))
