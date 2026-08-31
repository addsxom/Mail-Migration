import time
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar
from app.ui.accounts import AccountsPage

_original_accounts_init = AccountsPage.__init__
_original_start_scan = AccountsPage.start_scan

CARD_STYLE = """
QFrame#scanLiveCard {
    background: #171C24;
    border: 1px solid #252D39;
    border-radius: 28px;
}
QLabel#scanLiveTitle { color: #F4F7FB; font-size: 20px; font-weight: 700; }
QLabel#scanLiveSubtitle { color: #8993A3; font-size: 12px; }
QLabel#scanLiveBadge {
    color: #A8F5C0;
    background: #182820;
    border: 1px solid #31543F;
    border-radius: 16px;
    padding: 8px 13px;
    font-size: 10px;
    font-weight: 800;
}
QLabel#scanStat {
    color: #EEF2F7;
    background: #121720;
    border: 1px solid #222A35;
    border-radius: 18px;
    padding: 10px 12px;
    font-size: 12px;
    font-weight: 700;
}
QLabel#scanStatIcon { color: #69D8FF; font-size: 20px; font-weight: 700; }
QLabel#scanStatValue { color: #EEF2F7; font-size: 15px; font-weight: 800; }
QLabel#scanStatLabel { color: #8E98A8; font-size: 9px; font-weight: 700; letter-spacing: 1px; }
QLabel#scanLiveDetail { color: #8E98A8; font-size: 11px; }
QProgressBar#scanLiveProgress {
    background: #0E131A;
    border: 1px solid #202833;
    border-radius: 4px;
}
QProgressBar#scanLiveProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2388FF, stop:1 #35D6D1);
    border-radius: 4px;
}
"""


def _make_stat_card(icon, value, label):
    card = QFrame()
    card.setObjectName("scanStat")
    layout = QHBoxLayout(card)
    layout.setContentsMargins(13, 10, 13, 10)
    layout.setSpacing(10)
    icon_label = QLabel(icon)
    icon_label.setObjectName("scanStatIcon")
    icon_label.setFixedWidth(27)
    icon_label.setAlignment(Qt.AlignCenter)
    text = QVBoxLayout()
    text.setSpacing(2)
    value_label = QLabel(value)
    value_label.setObjectName("scanStatValue")
    label_label = QLabel(label)
    label_label.setObjectName("scanStatLabel")
    text.addWidget(value_label)
    text.addWidget(label_label)
    layout.addWidget(icon_label)
    layout.addLayout(text, 1)
    card._icon_label = icon_label
    card._value_label = value_label
    card._label_label = label_label
    return card


def _build_scan_interface(self):
    self.progress.hide()
    self.status.hide()
    panel = QFrame(self)
    panel.setObjectName("scanLiveCard")
    panel.setStyleSheet(CARD_STYLE)
    root = QVBoxLayout(panel)
    root.setContentsMargins(24, 21, 24, 21)
    root.setSpacing(15)

    top = QHBoxLayout()
    top.setSpacing(16)
    title_box = QVBoxLayout()
    title_box.setSpacing(3)
    self.scan_live_title = QLabel("Analyse du compte 0 / 0")
    self.scan_live_title.setObjectName("scanLiveTitle")
    self.scan_live_subtitle = QLabel("Prêt à analyser")
    self.scan_live_subtitle.setObjectName("scanLiveSubtitle")
    title_box.addWidget(self.scan_live_title)
    title_box.addWidget(self.scan_live_subtitle)
    top.addLayout(title_box, 1)
    self.scan_live_badge = QLabel("● EN ATTENTE")
    self.scan_live_badge.setObjectName("scanLiveBadge")
    top.addWidget(self.scan_live_badge, 0)
    root.addLayout(top)

    stats = QHBoxLayout()
    stats.setSpacing(12)
    self.scan_account_card = _make_stat_card("👤", "—", "COMPTE ACTUEL")
    self.scan_mail_card = _make_stat_card("✉", "0", "MAILS TRAITÉS")
    self.scan_service_card = _make_stat_card("▦", "0", "SERVICES DÉTECTÉS")
    self.scan_eta_card = _make_stat_card("⏱", "Calcul…", "TEMPS RESTANT")
    for card in (self.scan_account_card, self.scan_mail_card, self.scan_service_card, self.scan_eta_card):
        card.setMinimumHeight(66)
        stats.addWidget(card)
    root.addLayout(stats)

    self.scan_live_progress = QProgressBar()
    self.scan_live_progress.setRange(0, 100)
    self.scan_live_progress.setValue(0)
    self.scan_live_progress.setTextVisible(False)
    self.scan_live_progress.setFixedHeight(7)
    self.scan_live_progress.setObjectName("scanLiveProgress")
    root.addWidget(self.scan_live_progress)

    self.scan_live_detail = QLabel("Progression du compte : 0 %")
    self.scan_live_detail.setObjectName("scanLiveDetail")
    root.addWidget(self.scan_live_detail)
    parent_layout = self.list.parentWidget().layout()
    list_index = parent_layout.indexOf(self.list)
    parent_layout.insertWidget(list_index, panel)
    self.scan_live_card = panel
    panel.hide()


def _set_stat(card, value):
    card._value_label.setText(str(value))


def _accounts_init(self, on_change=None):
    _original_accounts_init(self, on_change)
    self._smooth_target = 0
    self._smooth_timer = QTimer(self)
    self._smooth_timer.setInterval(25)
    self._smooth_timer.timeout.connect(lambda: _smooth_progress_step(self))
    self._smooth_timer.start()
    self._scan_email_cache = {}
    self._scan_position_cache = {}
    self._scan_selected_total = 0
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
        self._scan_selected_total = len(ids)
        for position, account_id in enumerate(ids, 1):
            self._scan_position_cache[account_id] = position
            for index in range(self.list.count()):
                item = self.list.item(index)
                if item.data(256) == account_id:
                    text = item.text()
                    if " - " in text:
                        email = text.split(" - ", 1)[1].split("  —  ", 1)[0].strip()
                        self._scan_email_cache[account_id] = email
                    break
    self.scan_live_card.show()
    return _original_start_scan(self)


def _scan_account_started(self, account_id, position, total_accounts):
    self.scan_current_account = account_id
    self.scan_account_started_at = time.monotonic()
    self.scan_current_total = 0
    self._smooth_target = max(0, int(round(((position - 1) / max(1, self._scan_selected_total)) * 100)))
    display_total = self._scan_selected_total or len(getattr(self, "scan_account_ids", [])) or total_accounts
    display_position = self._scan_position_cache.get(account_id, position)
    self.scan_live_title.setText(f"Analyse du compte {display_position} / {display_total}")
    self.scan_live_subtitle.setText(self._scan_email_cache.get(account_id, "Compte Google"))
    self.scan_live_badge.setText("ANALYSE EN COURS  ●")
    self.scan_live_detail.setText("Progression du compte : 0 %")
    _set_stat(self.scan_account_card, f"{display_position} / {display_total}")
    _set_stat(self.scan_mail_card, "0")
    _set_stat(self.scan_service_card, "0")
    _set_stat(self.scan_eta_card, "Calcul…")


def _scan_progress(self, account_id, mails, total, services, completed_accounts):
    self.scan_messages[account_id] = mails
    self.scan_services[account_id] = services
    self.scan_current_total = total
    current_progress = (mails / total * 100) if total > 0 else 0
    selected_total = self._scan_selected_total or self.scan_total_accounts or 1
    completed_base = min(completed_accounts, selected_total)
    overall = ((completed_base + current_progress / 100) / selected_total) * 100
    self._smooth_target = max(0, min(100, int(round(overall))))
    elapsed = 0.0
    if self.scan_account_started_at is not None:
        elapsed = max(0.0, time.monotonic() - self.scan_account_started_at)
    eta = None
    if mails > 0 and elapsed > 0 and total > mails:
        rate = mails / elapsed
        eta = (total - mails) / rate if rate > 0 else None
    email = self._scan_email_cache.get(account_id, "Compte Google")
    position = self._scan_position_cache.get(account_id, completed_accounts + 1)
    display_total = self._scan_selected_total or len(self.scan_account_ids) or self.scan_total_accounts
    account_percent = int(round(current_progress)) if total else 0
    self.scan_live_title.setText(f"Analyse du compte {position} / {display_total}")
    self.scan_live_subtitle.setText(email)
    self.scan_live_badge.setText("ANALYSE EN COURS  ●")
    _set_stat(self.scan_account_card, f"{position} / {display_total}")
    _set_stat(self.scan_mail_card, f"{mails:,}")
    _set_stat(self.scan_service_card, services)
    _set_stat(self.scan_eta_card, _format_eta_short(eta))
    self.scan_live_detail.setText(f"Progression du compte : {account_percent} %")


def _format_eta_short(seconds):
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
    self.scan_live_title.setText("Scan terminé" if success else "Scan annulé")
    self.scan_live_badge.setText("SCAN TERMINÉ  ✓" if success else "SCAN ANNULÉ  ✕")
    self.scan_live_subtitle.setText(text)
    self.scan_live_detail.setText("Progression du compte : 100 %" if success else "Scan interrompu")
    self._smooth_target = 100 if success else self._smooth_target
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
