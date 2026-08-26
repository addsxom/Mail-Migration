from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel

class ServiceCard(QFrame):
    def __init__(self, name, category, score):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(name)
        title.setStyleSheet("font-size:16px;font-weight:700;")
        info = QLabel(f"{category} • Confiance {score:.0f}%")
        info.setStyleSheet("color:#9AA2AF;")
        layout.addWidget(title)
        layout.addWidget(info)
