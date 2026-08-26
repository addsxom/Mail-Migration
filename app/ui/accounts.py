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
    progress = Signal(int, int, int, int, int)
    detection = Signal(int, object)
    account_finished = Signal(int, int, int)
    finished = Signal()
    error = Signal(int, str)
    cancelled = Signal(int)

    def __init__(self, account_ids):
        super().__init__()
        self.account_ids = list(account_ids)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        completed = 0
        try:
            for account_id in self.account_ids:
                if self._cancel:
                    self.cancelled.emit(account_id)
                    break

                session = get_session()
                try:
                    result = scan_account(
                        session,
                        account_id,
                        progress=lambda messages, total, services, aid=account_id: self.progress.emit(
                            aid, messages, total, services, completed
                        ),
                        cancel_check=lambda: self._cancel,
                        detection_callback=lambda data, aid=account_id: self.detection.emit(aid, data),
                    )
                except ScanCancelled:
                    self.cancelled.emit(account_id)
                    break
                except Exception as exc:
                    self.error.emit(account_id, str(exc))
                    continue
                finally:
                    session.close()

                messages, services = result
                completed += 1
                self.account_finished.emit(account_id, messages, services)
                self.progress.emit(account_id, messages, messages, services, completed)

            self.finished.emit()
        except Exception as exc:
            self.error.emit(0, str(exc))
            self.finished.emit()


class AccountsPage(QWidget):
    scan_started = Signal(int)
    scan_detection = Signal(int, object)
    scan_finished_live = Signal(int)

    def __init__(self, on_change=None):
        super().__init__()
        self.on_change = on_change or (lambda *_: None)
        self.thread = None
        self.worker = None
        self.scan_account_ids = []
        self.scan_completed = 0
        self.scan_total_accounts = 0
        self.scan_messages = {}
        self.scan_services = {}

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
        self.scan = QPushButton("Analyser les comptes sélectionnés")
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
                    f"Compte : {account.email}\nNom : {label}\nÉtat OAuth : {state}"
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
        self.rename.setEnabled(has_one and self.worker is None)
        self.reauthorize.setEnabled(has_one and self.worker is None)
        self.delete.setEnabled(has_one and self.worker is None)
        self.scan.setEnabled(bool(ids) and self.worker is None)
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
                    account = GoogleAccount(email=email, display_name=email, token_reference=token_name, active=True)
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
        name, ok = QInputDialog.getText(self, "Nom du compte", "Nom personnalisé :", text=current)
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
                    new_account = GoogleAccount(email=email, display_name=email, token_reference=token_name, active=True)
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
            self, "Supprimer le compte",
            f"Supprimer « {label} » ({email}) ?\n\nCela supprimera aussi ses services détectés, traces et historique local.\nL'autorisation Google locale sera également révoquée.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
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
        account_ids = self.selected_ids()
        if not account_ids:
            QMessageBox.information(self, "Scan", "Sélectionne au moins un compte.")
            return

        self.scan_account_ids = account_ids
        self.scan_completed = 0
        self.scan_total_accounts = len(account_ids)
        self.scan_messages.clear()
        self.scan_services.clear()
        self.scan.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setFormat("Préparation...")
        self.status.setText(f"Préparation du scan de {len(account_ids)} compte(s)...")

        for account_id in account_ids:
            self.scan_started.emit(account_id)

        self.thread = QThread()
        self.worker = ScanWorker(account_ids)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.scan_progress)
        self.worker.detection.connect(self.scan_detection.emit)
        self.worker.finished.connect(self.scan_all_finished)
        self.worker.cancelled.connect(self.scan_cancelled)
        self.worker.error.connect(self.scan_error)
        self.thread.start()

    def scan_progress(self, account_id, messages, total, services, completed_accounts):
        self.scan_messages[account_id] = messages
        self.scan_services[account_id] = services
        account_progress = (messages / total * 100) if total > 0 else 0
        overall = ((completed_accounts + account_progress / 100) / max(1, self.scan_total_accounts)) * 100
        self.progress.setValue(min(100, int(overall)))
        self.progress.setFormat(f"{int(overall)}%")
        total_messages = sum(self.scan_messages.values())
        total_services = max(self.scan_services.values(), default=0)
        self.status.setText(
            f"Scan {completed_accounts + 1}/{self.scan_total_accounts} — "
            f"{messages:,} / ~{total:,} messages — "
            f"{total_messages:,} message(s) traités — {total_services} service(s) détecté(s)"
        )

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.cancel.setEnabled(False)
            self.status.setText("Annulation demandée — arrêt des scans en cours...")

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

    def scan_all_finished(self):
        self.progress.setValue(100 if self.scan_completed >= self.scan_total_accounts else self.progress.value())
        if self.scan_completed >= self.scan_total_accounts:
            self.progress.setFormat("Terminé")
            self.status.setText(
                f"Scan terminé — {sum(self.scan_messages.values()):,} messages — "
                f"{max(self.scan_services.values(), default=0)} service(s) détecté(s)."
            )
        self.cleanup_thread()

    def scan_finished(self, messages, services):
        self.scan_completed += 1
        self.scan_messages[self.selected_id() or 0] = messages
        self.scan_services[self.selected_id() or 0] = services
        self.refresh(self.selected_id())

    def scan_cancelled(self, account_id):
        self.progress.setFormat("Annulé")
        self.status.setText("Scan annulé.")
        self.scan_finished_live.emit(account_id)
        self.cleanup_thread()

    def scan_error(self, account_id, message):
        if account_id:
            self.scan_finished_live.emit(account_id)
        if self.worker:
            self.status.setText(f"Erreur sur le compte #{account_id} — poursuite des autres comptes...")
        else:
            self.status.setText("Erreur pendant le scan.")
        if account_id == 0:
            self.cleanup_thread()
            QMessageBox.critical(self, "Erreur de scan", message)
        else:
            QMessageBox.warning(self, "Erreur de scan", f"Compte #{account_id} : {message}")

    def scan_account_finished(self, account_id, messages, services):
        self.scan_completed += 1
        self.scan_messages[account_id] = messages
        self.scan_services[account_id] = services
        self.scan_finished_live.emit(account_id)
