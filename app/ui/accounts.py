from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog, QProgressBar,
)

from app.database.database import get_session
from app.database.models import GoogleAccount
from app.database.repositories import get_accounts, delete_account, update_account
from app.google.oauth import authorize, credential_state, revoke_token
from app.scanner.scanner import scan_account, ScanCancelled


class ScanWorker(QObject):
    progress = Signal(int, int, int)
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
                progress=lambda messages, total, services: self.progress.emit(
                    messages, total, services
                ),
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
    def __init__(self, on_change=None):
        super().__init__()
        self.on_change = on_change or (lambda *_: None)
        self.thread = None
        self.worker = None

        layout = QVBoxLayout(self)
        title = QLabel("Comptes Google")
        title.setObjectName("title")
        layout.addWidget(title)

        self.selected_label = QLabel("Aucun compte sélectionné")
        self.selected_label.setObjectName("muted")
        layout.addWidget(self.selected_label)

        actions = QHBoxLayout()
        add = QPushButton("+ Ajouter un compte")
        add.clicked.connect(self.add_account)
        self.rename = QPushButton("Renommer")
        self.rename.clicked.connect(self.rename_account)
        self.reauthorize = QPushButton("Réautoriser")
        self.reauthorize.clicked.connect(self.reauthorize_account)
        self.delete = QPushButton("Supprimer")
        self.delete.clicked.connect(self.remove_account)
        self.scan = QPushButton("Analyser le compte sélectionné")
        self.scan.clicked.connect(self.start_scan)
        self.cancel = QPushButton("Annuler")
        self.cancel.clicked.connect(self.cancel_scan)
        self.cancel.setEnabled(False)

        for widget in (add, self.rename, self.reauthorize, self.delete, self.scan, self.cancel):
            actions.addWidget(widget)
        actions.addStretch()
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("En attente")
        layout.addWidget(self.progress)

        self.status = QLabel("Aucun scan en cours.")
        layout.addWidget(self.status)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.list)

    def refresh(self, selected_id=None):
        current_id = selected_id if selected_id is not None else self.selected_id()
        self.list.blockSignals(True)
        self.list.clear()

        session = get_session()
        try:
            accounts = get_accounts(session)
            for account in accounts:
                state = credential_state(account.email) if account.active else "Désactivé"
                label = account.display_name or account.email
                text = f"{label}  —  {account.email}  —  {state}"
                if account.last_scan_at:
                    text += f"  —  Dernier scan : {account.last_scan_at:%d.%m.%Y %H:%M}"

                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, account.id)
                item.setToolTip(
                    f"Compte : {account.email}\n"
                    f"Nom : {label}\n"
                    f"État OAuth : {state}"
                )
                self.list.addItem(item)
                if account.id == current_id:
                    item.setSelected(True)
                    self.list.setCurrentItem(item)
        finally:
            session.close()

        self.list.blockSignals(False)
        self.selection_changed()

    def selection_changed(self):
        ids = self.selected_ids()
        current = self.selected_id()
        self.selected_label.setText(
            f"{len(ids)} compte(s) sélectionné(s)"
            + (f" — compte actif : #{current}" if current else "")
        )
        has_one = current is not None
        self.rename.setEnabled(has_one)
        self.reauthorize.setEnabled(has_one)
        self.delete.setEnabled(has_one)
        self.scan.setEnabled(has_one and self.worker is None)
        self.on_change(current)

    def selected_ids(self):
        return [item.data(Qt.UserRole) for item in self.list.selectedItems()]

    def selected_id(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def add_account(self):
        try:
            email, token_name = authorize()
            session = get_session()
            try:
                existing = session.query(GoogleAccount).filter_by(email=email).first()
                if not existing:
                    account = GoogleAccount(
                        email=email,
                        display_name=email,
                        token_reference=token_name,
                        active=True,
                    )
                    session.add(account)
                    session.flush()
                    account_id = account.id
                else:
                    existing.active = True
                    existing.token_reference = token_name
                    account_id = existing.id
                session.commit()
            finally:
                session.close()

            self.refresh(account_id)
            self.on_change(account_id)
        except Exception as exc:
            QMessageBox.critical(self, "OAuth", str(exc))

    def rename_account(self):
        account_id = self.selected_id()
        if not account_id:
            return

        session = get_session()
        try:
            account = session.get(GoogleAccount, account_id)
            if not account:
                return
            current = account.display_name or account.email
        finally:
            session.close()

        name, ok = QInputDialog.getText(
            self, "Nom du compte", "Nom personnalisé :", text=current
        )
        if not ok:
            return

        name = name.strip()
        if not name:
            QMessageBox.information(self, "Nom du compte", "Le nom ne peut pas être vide.")
            return

        session = get_session()
        try:
            update_account(session, account_id, display_name=name)
        finally:
            session.close()
        self.refresh(account_id)
        self.on_change(account_id)

    def reauthorize_account(self):
        account_id = self.selected_id()
        if not account_id:
            return

        try:
            email, token_name = authorize()
            session = get_session()
            try:
                account = session.get(GoogleAccount, account_id)
                existing = session.query(GoogleAccount).filter_by(email=email).first()

                if account and account.email.lower() == email.lower():
                    account.token_reference = token_name
                    account.active = True
                    target_id = account.id
                elif existing:
                    existing.token_reference = token_name
                    existing.active = True
                    target_id = existing.id
                else:
                    new_account = GoogleAccount(
                        email=email,
                        display_name=email,
                        token_reference=token_name,
                        active=True,
                    )
                    session.add(new_account)
                    session.flush()
                    target_id = new_account.id
                session.commit()
            finally:
                session.close()

            self.refresh(target_id)
            self.on_change(target_id)
        except Exception as exc:
            QMessageBox.critical(self, "Réautorisation", str(exc))

    def remove_account(self):
        account_id = self.selected_id()
        if not account_id:
            return

        session = get_session()
        try:
            account = session.get(GoogleAccount, account_id)
            if not account:
                return
            email = account.email
            label = account.display_name or email
        finally:
            session.close()

        answer = QMessageBox.question(
            self,
            "Supprimer le compte",
            f"Supprimer « {label} » ({email}) ?\n\n"
            "Cela supprimera aussi ses services détectés, traces et historique local.\n"
            "L'autorisation Google locale sera également révoquée.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            revoke_token(email)
            session = get_session()
            try:
                delete_account(session, account_id)
            finally:
                session.close()
            self.refresh()
            self.on_change(None)
        except Exception as exc:
            QMessageBox.critical(self, "Suppression", str(exc))

    def start_scan(self):
        account_id = self.selected_id()
        if not account_id:
            QMessageBox.information(self, "Scan", "Sélectionne d'abord un compte.")
            return

        self.scan.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setFormat("Préparation du scan...")
        self.status.setText("Préparation du scan Gmail...")

        self.thread = QThread()
        self.worker = ScanWorker(account_id)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.scan_progress)
        self.worker.finished.connect(self.scan_finished)
        self.worker.cancelled.connect(self.scan_cancelled)
        self.worker.error.connect(self.scan_error)
        self.thread.start()

    def scan_progress(self, messages, total, services):
        if total > 0:
            percent = min(100, int(messages * 100 / total))
            self.progress.setValue(percent)
            self.progress.setFormat(f"{percent}%")
            total_text = f"{messages:,} / ~{total:,} messages"
        else:
            self.progress.setValue(0)
            self.progress.setFormat("En cours")
            total_text = f"{messages:,} messages"

        self.status.setText(
            f"Scan en cours — {total_text} — {services} service(s) détecté(s)"
        )

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.cancel.setEnabled(False)
            self.status.setText("Annulation demandée — fin de la requête Gmail en cours...")

    def cleanup_thread(self):
        thread = self.thread
        self.thread = None
        self.worker = None
        self.scan.setEnabled(True)
        self.cancel.setEnabled(False)
        self.selection_changed()
        self.on_change(self.selected_id())
        if thread:
            thread.quit()
            thread.wait()

    def scan_finished(self, messages, services):
        self.progress.setValue(100)
        self.progress.setFormat("Terminé")
        self.status.setText(
            f"Scan terminé — {messages:,} messages — {services} service(s) détecté(s)."
        )
        self.refresh(self.selected_id())
        self.cleanup_thread()

    def scan_cancelled(self):
        self.progress.setFormat("Annulé")
        self.status.setText("Scan annulé.")
        self.cleanup_thread()

    def scan_error(self, message):
        self.progress.setFormat("Erreur")
        self.status.setText("Erreur pendant le scan.")
        self.cleanup_thread()
        QMessageBox.critical(self, "Erreur de scan", message)
