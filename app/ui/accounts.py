import time
from datetime import timezone

from PySide6.QtCore import QObject, Signal, QThread, Qt, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QMessageBox, QInputDialog, QProgressBar

from app.database.database import get_session
from app.database.models import GoogleAccount
from app.database.repositories import get_accounts, delete_account, update_account
from app.google.oauth import authorize, credential_state, revoke_token
from app.scanner.scanner import scan_account, ScanCancelled


class ScanWorker(QObject):
    progress = Signal(int, int, int, int, int)
    detection = Signal(int, object)
    account_started = Signal(int, int, int)
    account_finished = Signal(int, int, int)
    finished = Signal()
    error = Signal(int, str)
    cancelled = Signal(int)

    def __init__(self, account_ids, positions):
        super().__init__()
        self.account_ids = list(account_ids)
        self.positions = dict(positions)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        completed = 0
        total_accounts = len(self.account_ids)
        try:
            for account_id in self.account_ids:
                if self._cancel:
                    self.cancelled.emit(account_id)
                    break
                position = self.positions.get(account_id, completed + 1)
                self.account_started.emit(account_id, position, max(position, max(self.positions.values(), default=total_accounts)))
                session = get_session()
                try:
                    result = scan_account(
                        session,
                        account_id,
                        progress=lambda m, t, s, aid=account_id: self.progress.emit(aid, m, t, s, completed),
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
        self.scan_started_at = None
        self.scan_account_started_at = None
        self.scan_current_total = 0
        self.scan_current_account = None
        self.status_effect = None
        self.status_timer = None
        self.progress_animation = None

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
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        layout.addWidget(self.progress)

        self.status = QLabel("Aucun scan en cours.")
        self.status.setObjectName("scanStatus")
        layout.addWidget(self.status)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.list)

    @staticmethod
    def _local_datetime(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone()

    def refresh(self, selected_id=None):
        current_id = selected_id if selected_id is not None else self.selected_id()
        self.list.blockSignals(True)
        self.list.clear()
        session = get_session()
        try:
            accounts = list(get_accounts(session))
            for number, account in enumerate(accounts, 1):
                state = credential_state(account.email) if account.active else "Désactivé"
                text = f"Numéro {number} - {account.email}  —  {state}"
                last_scan = self._local_datetime(account.last_scan_at)
                if last_scan:
                    text += f"  —  Dernier scan : {last_scan:%d.%m.%Y %H:%M}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, account.id)
                item.setToolTip(f"Compte n°{number} : {account.email}\nÉtat OAuth : {state}")
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
        self.selected_label.setText(f"{len(ids)} compte(s) sélectionné(s)" + (f" — compte actif : #{current}" if current else ""))
        one = current is not None
        enabled = self.worker is None
        self.rename.setEnabled(one and enabled)
        self.reauthorize.setEnabled(one and enabled)
        self.delete.setEnabled(one and enabled)
        self.scan.setEnabled(bool(ids) and enabled)
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
        if QMessageBox.question(
            self,
            "Supprimer le compte",
            f"Supprimer « {label} » ({email}) ?\n\nCela supprimera aussi ses services détectés, traces et historique local.\nL'autorisation Google locale sera également révoquée.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
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

        session = get_session()
        try:
            all_accounts = [account.id for account in get_accounts(session) if account.active]
        finally:
            session.close()
        positions = {account_id: index + 1 for index, account_id in enumerate(all_accounts)}

        self.scan_account_ids = account_ids
        self.scan_completed = 0
        self.scan_total_accounts = len(all_accounts) or len(account_ids)
        self.scan_messages.clear()
        self.scan_services.clear()
        self.scan_started_at = time.monotonic()
        self.scan_account_started_at = None
        self.scan_current_total = 0
        self.scan_current_account = None
        self.scan.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText(f"Compte 1 / {self.scan_total_accounts}   •   Préparation du scan…")

        for account_id in account_ids:
            self.scan_started.emit(account_id)

        self.thread = QThread()
        self.worker = ScanWorker(account_ids, positions)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.account_started.connect(self.scan_account_started)
        self.worker.progress.connect(self.scan_progress)
        self.worker.detection.connect(self.scan_detection.emit)
        self.worker.account_finished.connect(self.scan_account_finished)
        self.worker.finished.connect(self.scan_all_finished)
        self.worker.cancelled.connect(self.scan_cancelled)
        self.worker.error.connect(self.scan_error)
        self.thread.start()

    @staticmethod
    def _format_eta(seconds):
        if seconds is None or seconds < 0:
            return "Calcul du temps restant…"
        seconds = int(round(seconds))
        if seconds < 60:
            return f"{seconds} s restantes"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes} min {sec:02d} s restantes"
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min restantes"

    def _animate_progress(self, value):
        value = max(0, min(100, int(value)))
        if self.progress_animation:
            self.progress_animation.stop()
        self.progress_animation = QPropertyAnimation(self.progress, b"value", self)
        self.progress_animation.setDuration(220)
        self.progress_animation.setStartValue(self.progress.value())
        self.progress_animation.setEndValue(value)
        self.progress_animation.start()

    def scan_account_started(self, account_id, position, total_accounts):
        self.scan_current_account = account_id
        self.scan_account_started_at = time.monotonic()
        self.scan_current_total = 0
        self.status.setText(f"Compte {position} / {total_accounts}   •   Scan en préparation…")

    def scan_progress(self, account_id, mails, total, services, completed_accounts):
        self.scan_messages[account_id] = mails
        self.scan_services[account_id] = services
        self.scan_current_total = total
        current_progress = (mails / total * 100) if total > 0 else 0
        completed_base = min(completed_accounts, self.scan_total_accounts)
        overall = ((completed_base + current_progress / 100) / max(1, self.scan_total_accounts)) * 100
        self._animate_progress(overall)

        elapsed = 0
        if self.scan_account_started_at is not None:
            elapsed = max(0.0, time.monotonic() - self.scan_account_started_at)
        eta = None
        if mails > 0 and elapsed > 0 and total > mails:
            rate = mails / elapsed
            eta = (total - mails) / rate if rate > 0 else None

        session = get_session()
        try:
            account = session.get(GoogleAccount, account_id)
            email = account.email if account else "Compte inconnu"
        finally:
            session.close()

        position = self._account_position(account_id)
        total_accounts = self.scan_total_accounts
        self.status.setText(
            f"Compte {position} / {total_accounts}   •   {email}   •   "
            f"{self._format_eta(eta)}   •   {mails:,} MAILS traités   •   {services} service(s) détecté(s)"
        )

    def _account_position(self, account_id):
        session = get_session()
        try:
            accounts = [account.id for account in get_accounts(session) if account.active]
            try:
                return accounts.index(account_id) + 1
            except ValueError:
                return self.scan_completed + 1
        finally:
            session.close()

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel()
            self.cancel.setEnabled(False)
            self.status.setText("Annulation du scan…")

    def _start_status_blink(self, text, success):
        if self.status_timer:
            self.status_timer.stop()
        self.status.setText(text)
        self.status_timer = QTimer(self)
        visible = [True]

        def blink():
            visible[0] = not visible[0]
            self.status.setVisible(visible[0])

        self.status_timer.timeout.connect(blink)
        self.status_timer.start(420)
        QTimer.singleShot(2600, self._stop_status_blink)

    def _stop_status_blink(self):
        if self.status_timer:
            self.status_timer.stop()
            self.status_timer = None
        self.status.setVisible(True)

    def cleanup_thread(self):
        thread = self.thread
        self.thread = None
        self.worker = None
        self.scan.setEnabled(True)
        self.cancel.setEnabled(False)
        self.selection_changed()
        if thread:
            thread.quit()
            thread.wait()

    def scan_all_finished(self):
        if self.scan_completed >= len(self.scan_account_ids):
            self._animate_progress(100)
            total_mails = sum(self.scan_messages.values())
            total_services = sum(self.scan_services.values())
            self._start_status_blink(f"✓  Scan terminé   •   {total_mails:,} MAILS   •   {total_services} service(s) détecté(s)", True)
        self.scan_finished_live.emit(-2)
        self.cleanup_thread()
        self.refresh(self.selected_id())

    def scan_cancelled(self, _account_id):
        self._start_status_blink(
            f"✕  Scan annulé   •   {sum(self.scan_messages.values()):,} MAILS traités   •   résultats conservés",
            False,
        )
        self.scan_finished_live.emit(-1)
        self.cleanup_thread()

    def scan_error(self, account_id, message):
        if account_id == 0:
            self.cleanup_thread()
            QMessageBox.critical(self, "Erreur de scan", message)
        else:
            self.status.setText(f"⚠ Erreur sur le compte #{account_id}   •   poursuite des autres comptes…")
            QMessageBox.warning(self, "Erreur de scan", f"Compte #{account_id} : {message}")

    def scan_finished(self, messages, services):
        self.scan_completed += 1

    def scan_account_finished(self, account_id, messages, services):
        self.scan_completed += 1
        self.scan_messages[account_id] = messages
        self.scan_services[account_id] = services
