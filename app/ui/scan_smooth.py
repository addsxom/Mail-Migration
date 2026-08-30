import time
from PySide6.QtCore import QTimer
from app.database.database import get_session
from app.ui.accounts import AccountsPage, ScanWorker
from app.database.repositories import get_accounts
from app.scanner.scanner import scan_account, ScanCancelled

_original_start_scan = AccountsPage.start_scan
_original_accounts_init = AccountsPage.__init__


def _accounts_init(self, on_change=None):
    _original_accounts_init(self, on_change)
    self._smooth_target = 0
    self._smooth_timer = QTimer(self)
    self._smooth_timer.setInterval(25)
    self._smooth_timer.timeout.connect(self._smooth_progress_step)
    self._smooth_timer.start()
    self._scan_email_cache = {}
    self._scan_position_cache = {}
    self._scan_last_status = 0.0


def _smooth_progress_step(self):
    current = self.progress.value()
    target = getattr(self, "_smooth_target", current)
    if current < target:
        step = max(1, min(2, int((target - current) * 0.18) + 1))
        self.progress.setValue(min(target, current + step))
    elif current > target:
        self.progress.setValue(target)


def _start_scan(self):
    ids = self.selected_ids()
    if ids:
        self._scan_email_cache = {}
        self._scan_position_cache = {}
        for index in range(self.list.count()):
            item = self.list.item(index)
            account_id = item.data(256)
            if account_id is not None:
                text = item.text()
                if " - " in text:
                    email = text.split(" - ", 1)[1].split("  —  ", 1)[0].strip()
                    self._scan_email_cache[account_id] = email
                self._scan_position_cache[account_id] = index + 1
    return _original_start_scan(self)


def _scan_progress(self, account_id, mails, total, services, completed_accounts):
    self.scan_messages[account_id] = mails
    self.scan_services[account_id] = services
    self.scan_current_total = total
    current_progress = (mails / total * 100) if total > 0 else 0
    completed_base = min(completed_accounts, self.scan_total_accounts)
    overall = ((completed_base + current_progress / 100) / max(1, self.scan_total_accounts)) * 100
    self._smooth_target = max(0, min(100, int(round(overall))))

    now = time.monotonic()
    if now - getattr(self, "_scan_last_status", 0.0) < 0.08 and mails != total:
        return
    self._scan_last_status = now

    elapsed = 0.0
    if self.scan_account_started_at is not None:
        elapsed = max(0.0, now - self.scan_account_started_at)
    eta = None
    if mails > 0 and elapsed > 0 and total > mails:
        rate = mails / elapsed
        eta = (total - mails) / rate if rate > 0 else None

    email = self._scan_email_cache.get(account_id, "Compte inconnu")
    position = self._scan_position_cache.get(account_id, self.scan_completed + 1)
    self.status.setText(
        f"Compte {position} / {self.scan_total_accounts}   •   {email}   •   "
        f"{self._format_eta(eta)}   •   {mails:,} MAILS traités   •   {services} service(s) détecté(s)"
    )


def _scan_account_started(self, account_id, position, total_accounts):
    self.scan_current_account = account_id
    self.scan_account_started_at = time.monotonic()
    self.scan_current_total = 0
    self.status.setText(f"Compte {position} / {total_accounts}   •   Scan en préparation…")


def _worker_run(self):
    completed = 0
    total_accounts = len(self.account_ids)
    try:
        for account_id in self.account_ids:
            if self._cancel:
                self.cancelled.emit(account_id)
                break
            position = self.positions.get(account_id, completed + 1)
            total_positions = max(position, max(self.positions.values(), default=total_accounts))
            self.account_started.emit(account_id, position, total_positions)
            session = get_session()
            last_emit = 0.0
            last_values = None

            def emit_progress(m, t, s, aid=account_id):
                nonlocal last_emit, last_values
                now = time.monotonic()
                values = (m, t, s, completed)
                if m == t or now - last_emit >= 0.06 or values != last_values:
                    if m == t or now - last_emit >= 0.06:
                        self.progress.emit(aid, m, t, s, completed)
                        last_emit = now
                        last_values = values

            try:
                result = scan_account(
                    session,
                    account_id,
                    progress=emit_progress,
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


AccountsPage.__init__ = _accounts_init
AccountsPage.start_scan = _start_scan
AccountsPage.scan_progress = _scan_progress
AccountsPage.scan_account_started = _scan_account_started
ScanWorker.run = _worker_run
