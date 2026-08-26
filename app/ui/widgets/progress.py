from PySide6.QtWidgets import QProgressBar

class ScanProgress(QProgressBar):
    def __init__(self):
        super().__init__()
        self.setRange(0, 0)
