from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog
)
from app.database.database import get_session
from app.database.models import GoogleAccount
from app.database.repositories import get_accounts, delete_account
from app.google.oauth import authorize, revoke_token, token_path_for_email
from app.scanner.scanner import scan_account, ScanCancelled

class ScanWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(int, int)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, account_id):
        super().__init__()
        self.account_id = account_id
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        session = get_session()
        try:
            result = scan_account(
                session,
                self.account_id,
                progress=lambda messages, services: self.progress.emit(messages, services),
                cancel_check=lambda: self._cancel,
            )
            self.finished.emit(*result)
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            session.close()

class AccountsPage(QWidget):
    def __init__(self, on_change):
        super().__init__()
        self.on_change = on_change
        self.thread = None
        self.worker = None

        layout = QVBoxLayout(self)
        title = QLabel("Comptes Google")
        title.setObjectName("title")
        layout.addWidget(title)

        actions = QHBoxLayout()
        add = QPushButton("+ Ajouter un compte")
        add.clicked.connect(self.add_account)
        self.scan = QPushButton("Analyser le compte sélectionné")
        self.scan.clicked.connect(self.start_scan)
        self.cancel = QPushButton("Annuler")
        self.cancel.clicked.connect(self.cancel_scan)
        self.cancel.setEnabled(False)
        actions.addWidget(add)
        actions.addWidget(self.scan)
        actions.addWidget(self.cancel)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QLabel("Aucun scan en cours.")
        layout.addWidget(self.status)

        self.list = QListWidget()
        layout.addWidget(self.list)

    def refresh(self):
        self.list.clear()
        session = get_session()
        try:
            for account in get_accounts(session):
                text = f"{account.email}  —  {'Actif' if account.active else 'Inactif'}"
                if account.last_scan_at:
                    text += f"  —  Dernier scan : {account.last_scan_at:%d.%m.%Y %H:%M}"
                item = QListWidgetItem(text)
                item.setData(256, account.id)
                self.list.addItem(item)
        finally:
            session.close()

    def add_account(self):
        try:
            email, token_name = authorize()
            session = get_session()
            existing = session.query(GoogleAccount).filter_by(email=email).first()
            if not existing:
                session.add(GoogleAccount(
                    email=email,
                    display_name=email,
                    token_reference=token_name,
                ))
            else:
                existing.active = True
                existing.token_reference = token_name
            session.commit()
            session.close()
            self.refresh()
            self.on_change()
        except Exception as exc:
            QMessageBox.critical(self, "OAuth", str(exc))

    def selected_id(self):
        item = self.list.currentItem()
        return item.data(256) if item else None

    def start_scan(self):
        account_id = self.selected_id()
        if not account_id:
            QMessageBox.information(self, "Scan", "Sélectionne d'abord un compte.")
            return

        self.scan.setEnabled(False)
        self.cancel.setEnabled(True)
        self.status.setText("Scan en cours...")

        self.thread = QThread()
        self.worker = ScanWorker(account_id)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(
            lambda messages, services: self.status.setText(
                f"Scan en cours... {messages} messages analysés — {services} services détectés"
            )
        )
        self.worker.finished.connect(self.scan_finished)
        self.worker.cancelled.connect(self.scan_cancelled)
        self.worker.error.connect(self.scan_error)
        self.thread.start()

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.status.setText("Annulation demandée...")

    def cleanup_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
        self.scan.setEnabled(True)
        self.cancel.setEnabled(False)
        self.on_change()

    def scan_finished(self, messages, services):
        self.status.setText(f"Terminé : {messages} messages — {services} services détectés.")
        self.cleanup_thread()

    def scan_cancelled(self):
        self.status.setText("Scan annulé.")
        self.cleanup_thread()

    def scan_error(self, message):
        self.status.setText("Erreur pendant le scan.")
        self.cleanup_thread()
        QMessageBox.critical(self, "Erreur de scan", message)
