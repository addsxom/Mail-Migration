from PySide6.QtWidgets import QLabel

class Toast(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet(
            "background:#252B35;color:#fff;border:1px solid #3A4350;"
            "border-radius:8px;padding:10px 14px;"
        )
