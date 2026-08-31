import time
from PySide6.QtCore import QTimer, QPropertyAnimation
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar
from app.ui.accounts import AccountsPage

_original_accounts_init = AccountsPage.__init__
_original_start_scan = AccountsPage.start_scan


def _build_scan_interface(self):
    """Clean scan dashboard. It only changes presentation; the scanner stays untouched."""
    self.progress.hide()
    self.status.hide()

    panel = QFrame(self)
    panel.setObjectName("scanLiveCard")
    root = QVBoxLayout(panel)
    root.setContentsMargins(20, 18, 20, 18)
    root.setSpacing(12)

    top = QHBoxLayout()
    top.setSpacing(10)
    title_box = QVBoxLayout()
    title_box.setSpacing(2)

    self.scan_live_title = QLabel("Prêt à analyser")
    self.scan_live_title.setObjectName("scanLiveTitle")
    self.scan_live_subtitle = QLabel("Sélectionnez un ou plusieurs comptes pour commencer")
    self.scan_live_subtitle.setObjectName("scanLiveSubtitle")
    title_box.addWidget(self.scan_live_title)
    title_box.addWidget(self.scan_live_subtitle)
    top.addLayout(title_box, 1)

    self.scan_live_badge = QLabel("● EN ATTENTE")
    self.scan_live_badge.setObjectName("scanLiveBadge")
    top.addWidget(self.scan_live_badge, 0)
    root.addLayout(top)

    stats = QHBoxLayout()
    stats.setSpacing(10)
    self.scan_account_stat = QLabel("—\nCOMPTES")
    self.scan_mail_stat = QLabel("—\nMAILS TRAITÉS")
    self.scan_service_stat = QLabel("—\nSERVICES")
    self.scan_eta_stat = QLabel("—\nTEMPS RESTANT")
    for widget in (self.scan_account_stat, self.scan_mail_stat, self.scan_service_stat, self.scan_eta_stat):
        widget.setObjectName("scanStat")
        widget.setMinimumHeight(54)
        stats.addWidget(widget)
    root.addLayout(stats)

    self.scan_live_progress = QProgressBar()
    self.scan_live_progress.setRange(0, 100)
    self.scan_live_progress.setValue(0)
    self.scan_live_progress.setTextVisible(False)
    self.scan_live_progress.setFixedHeight(8)
    self.scan_live_progress.setObjectName("scanLiveProgress")
    root.addWidget(self.scan_live_progress)

    self.scan_live_detail = QLabel("Aucun scan en cours.")
    self.scan_live_detail.setObjectName("scanLiveDetail")
    root.addWidget(self.scan_live_detail)

    # Insert the card immediately before the account list.
    parent_layout = self.list.parentWidget().layout()
    list_index = parent_layout.indexOf(self.list)
    parent_layout.insertWidget(list_index, panel)
    self.scan_live_card = panel
    panel.hide()


def _accounts_init(self, on_change=None):
    _original_accounts_init(self, on_change)
    self._smooth_target = 0
    self._smooth_timer = QTimer(self)
    self._smooth_timer.setInterval(25)
    self._smooth_timer.timeout.connect(lambda: _smooth_progress_step(self))
    self._smooth_timer.start()
    self._scan_email_cache = {}
    self._scan_position_cache = {}
    self._scan_last_status = 0.0
    self._scan_last_mail_display = {}
    _build_scan_interface(self)


def _smooth_progress_step(self):
    if not hasattr(self, "scan_live_progress"):
        return
    current = self.scan_live_progress.value()
    target = getattr(self, "_smooth_target", current)
    if current < target:
        distance = target - current
        step = max(1, min(2, int(distance * 0.16) + 1))
        self.scan_live_progress.setValue(min(target, current + step))
    elif current > target:
        self.scan_live_progress.setValue(target)


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
    self.scan_live_card.show()
    return _original_start_scan(self)


def _scan_account_started(self, account_id, position, total_accounts):
    self.scan_current_account = account_id
    self.scan_account_started_at = time.monotonic()
    self.scan_current_total = 0
    self._smooth_target = 0
    self.scan_live_title.setText(f"Analyse du compte {position} / {total_accounts}")
    self.scan_live_subtitle.setText(self._scan_email_cache.get(account_id, "Compte Google"))
    self.scan_live_badge.setText("● ANALYSE EN COURS")
    self.scan_live_detail.setText("Connexion à Gmail et préparation des messages…")
    self.scan_account_stat.setText(f"{position} / {total_accounts}\nCOMPTE ACTUEL")
    self.scan_eta_stat.setText("Calcul…\nTEMPS RESTANT")


def _scan_progress(self, account_id, mails, total, services, completed_accounts):
    self.scan_messages[account_id] = mails
    self.scan_services[account_id] = services
    self.scan_current_total = total

    current_progress = (mails / total * 100) if total > 0 else 0
    completed_base = min(completed_accounts, self.scan_total_accounts)
    overall = ((completed_base + current_progress / 100) / max(1, self.scan_total_accounts)) * 100
    self._smooth_target = max(0, min(100, int(round(overall))))

    elapsed = 0.0
    if self.scan_account_started_at is not None:
        elapsed = max(0.0, time.monotonic() - self.scan_account_started_at)
    eta = None
    if mails > 0 and elapsed > 0 and total > mails:
        rate = mails / elapsed
        eta = (total - mails) / rate if rate > 0 else None

    email = self._scan_email_cache.get(account_id, "Compte Google")
    position = self._scan_position_cache.get(account_id, self.scan_completed + 1)
    eta_text = self._format_eta_short(eta)
    account_percent = int(round(current_progress)) if total else 0

    self.scan_live_title.setText(f"Analyse du compte {position} / {self.scan_total_accounts}")
    self.scan_live_subtitle.setText(email)
    self.scan_live_badge.setText("● ANALYSE EN COURS")
    self.scan_account_stat.setText(f"{position} / {self.scan_total_accounts}\nCOMPTE ACTUEL")
    self.scan_mail_stat.setText(f"{mails:,}\nMAILS TRAITÉS")
    self.scan_service_stat.setText(f"{services}\nSERVICES DÉTECTÉS")
    self.scan_eta_stat.setText(f"{eta_text}\nTEMPS RESTANT")
    self.scan_live_detail.setText(f"Progression du compte : {account_percent} %   •   {mails:,} / {total:,} mails")


def _format_eta_short(self, seconds):
    if seconds is None or seconds < 0:
        return "Calcul…"
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _start_status_blink(self, text, success):
    if getattr(self, "status_timer", None):
        self.status_timer.stop()
    self.scan_live_title.setText("✓ Scan terminé" if success else "✕ Scan annulé")
    self.scan_live_badge.setText("● TERMINÉ" if success else "● ANNULÉ")
    self.scan_live_subtitle.setText(text)
    self.scan_live_detail.setText("Les résultats sont disponibles dans les services détectés.")
    self.scan_live_progress.setValue(100 if success else self._smooth_target)

    self.status_timer = QTimer(self)
    visible = [True]

    def blink():
        visible[0] = not visible[0]
        self.scan_live_badge.setVisible(visible[0])

    self.status_timer.timeout.connect(blink)
    self.status_timer.start(420)
    QTimer.singleShot(2600, self._stop_status_blink)


def _stop_status_blink(self):
    if getattr(self, "status_timer", None):
        self.status_timer.stop()
        self.status_timer = None
    self.scan_live_badge.setVisible(True)


AccountsPage.__init__ = _accounts_init
AccountsPage.start_scan = _start_scan
AccountsPage.scan_account_started = _scan_account_started
AccountsPage.scan_progress = _scan_progress
AccountsPage._start_status_blink = _start_status_blink
AccountsPage._stop_status_blink = _stop_status_blink
AccountsPage._format_eta_short = _format_eta_short
