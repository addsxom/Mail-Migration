from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFontMetrics, QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
    QWidget, QLineEdit, QStyledItemDelegate, QMenu, QTextEdit,
)
from sqlalchemy import delete, select

from app.database.database import get_session
from app.database.models import GoogleAccount, AccountService, ScanTrace, Service
from app.database.repositories import get_accounts, get_account_services
from app.services.builtin_catalog import CATALOG


MIGRATION_STATUSES = ["À vérifier", "À migrer", "Migré", "Abandonné"]

_ICON_CACHE = {}

# Kept only as a compatibility/fallback map for service names that may exist
# outside the built-in catalog. Catalog domains are now the primary source.
SERVICE_DOMAINS = {
    "amazon": "amazon.com", "apple": "apple.com", "discord": "discord.com",
    "dropbox": "dropbox.com", "epic-games": "epicgames.com", "epicgames": "epicgames.com",
    "facebook": "facebook.com", "google": "google.com", "google-drive": "drive.google.com",
    "instagram": "instagram.com", "linkedin": "linkedin.com", "microsoft": "microsoft.com",
    "microsoft-365": "microsoft.com", "netflix": "netflix.com", "nintendo": "nintendo.com",
    "nintendo-switch": "nintendo.com", "paypal": "paypal.com", "playstation": "playstation.com",
    "reddit": "reddit.com", "roblox": "roblox.com", "samsung": "samsung.com",
    "spotify": "spotify.com", "steam": "steampowered.com", "tiktok": "tiktok.com",
    "twitch": "twitch.tv", "twitter": "x.com", "x": "x.com", "ubisoft": "ubisoft.com",
    "xbox": "xbox.com", "youtube": "youtube.com", "yahoo": "yahoo.com",
    "airbnb": "airbnb.com", "adobe": "adobe.com", "canva": "canva.com",
    "github": "github.com", "gitlab": "gitlab.com", "nvidia": "nvidia.com",
    "ea": "ea.com", "ea-games": "ea.com", "battle-net": "battle.net",
    "blizzard": "blizzard.com", "riot-games": "riotgames.com", "valorant": "playvalorant.com",
    "2k": "2k.com", "nba-2k": "nba.2k.com", "take-two": "taketwointeractivesoftware.com",
    "snapchat": "snapchat.com", "telegram": "telegram.org", "whatsapp": "whatsapp.com",
    "xhamster": "xhamster.com", "aliexpress": "aliexpress.com", "zalando": "zalando.ch",
    "digitec": "digitec.ch", "galaxus": "galaxus.ch", "ricardo": "ricardo.ch",
    "swisscom": "swisscom.ch", "sunrise": "sunrise.ch", "salt": "salt.ch",
}


def _service_icon_key(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name or "service").strip().lower()).strip("-") or "service"


def _service_initials(name):
    words = [word for word in re.split(r"\s+", str(name or "Service").strip()) if word]
    if not words:
        return "?"
    if len(words) == 1:
        letters = re.sub(r"[^A-Za-z0-9]", "", words[0])
        return (letters[:2] or "?").upper()
    return (words[0][0] + words[1][0]).upper()


def _catalog_domains(name, category=""):
    """Return domains declared by the built-in catalog for this service name."""
    wanted = _service_icon_key(name)
    matches = []
    for definition in CATALOG:
        definition_name = definition.get("name", "")
        if _service_icon_key(definition_name) == wanted:
            matches.extend(str(domain).strip().lower() for domain in definition.get("domains", []) if domain)
    return list(dict.fromkeys(matches))


def _service_domain(name, category=""):
    # 1. The catalog is the source of truth for recognized services.
    catalog_domains = _catalog_domains(name, category)
    if catalog_domains:
        return catalog_domains[0]

    # 2. Compatibility fallback for names not represented in the catalog.
    key = _service_icon_key(name)
    if key in SERVICE_DOMAINS:
        return SERVICE_DOMAINS[key]
    compact = key.replace("-", "")
    for known_key, domain in SERVICE_DOMAINS.items():
        if known_key.replace("-", "") == compact:
            return domain
    return None


def _fallback_service_icon(name):
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(48, 56, 70))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.setPen(QColor(231, 234, 240))
    font = QFont()
    font.setBold(True)
    font.setPointSize(9)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, _service_initials(name))
    painter.end()
    return QIcon(pixmap)


def _service_icon(name, category=""):
    key = (_service_icon_key(name), str(category or ""))
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    assets_dir = Path(__file__).resolve().parents[2] / "assets" / "service_logos"
    local_key = key[0]
    for suffix in (".png", ".jpg", ".jpeg", ".svg"):
        candidate = assets_dir / f"{local_key}{suffix}"
        if candidate.exists():
            icon = QIcon(str(candidate))
            _ICON_CACHE[key] = icon
            return icon

    domain = _service_domain(name, category)
    if domain:
        try:
            url = f"https://www.google.com/s2/favicons?sz=64&domain={quote(domain)}"
            request = Request(url, headers={"User-Agent": "Mail-Migration/1.0"})
            with urlopen(request, timeout=2.5) as response:
                data = response.read()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                icon = QIcon(pixmap)
                _ICON_CACHE[key] = icon
                return icon
        except Exception:
            pass

    icon = _fallback_service_icon(name)
    _ICON_CACHE[key] = icon
    return icon


class ServiceDetailsDialog(QDialog):
    def __init__(self, details, parent=None):
        super().__init__(parent)
        self.details = details
        self.account_service_id = details.get("account_service_id")
        self.setWindowTitle(f"Détails — {details.get('name', 'Service')}")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMaximumWidth(760)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        card = QFrame()
        card.setObjectName("serviceDetailsCard")
        card.setStyleSheet("""
            QFrame#serviceDetailsCard { border: 1px solid #303846; border-radius: 14px; background: #171b22; }
            QLabel#serviceDetailsTitle { font-size: 22px; font-weight: 700; }
            QLabel#serviceDetailsSubtitle { color: #9AA2AF; }
            QLabel.detailLabel { color: #9AA2AF; font-size: 12px; }
            QLabel.signalValue { color: #E7EAF0; }
            QLabel.scoreValue { font-size: 18px; font-weight: 700; }
            QLineEdit, QComboBox, QTextEdit { border: 1px solid #303846; border-radius: 8px; background: #11151b; color: #E7EAF0; padding: 7px 9px; }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 1px solid #58677d; }
            QPushButton { padding: 8px 16px; border-radius: 8px; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)

        title = QLabel(details.get("name", "Service"))
        title.setObjectName("serviceDetailsTitle")
        card_layout.addWidget(title)
        subtitle = QLabel(details.get("category", "Autre"))
        subtitle.setObjectName("serviceDetailsSubtitle")
        card_layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        fields = [
            ("Compte Gmail", details.get("account_email", "—")),
            ("Confiance", self._format_score(details.get("score"))),
            ("Traces", str(details.get("count", 0))),
            ("Priorité", details.get("priority", "Normale")),
            ("Première détection", self._format_date(details.get("first_detected_at"))),
            ("Dernière détection", self._format_date(details.get("last_detected_at"))),
            ("Sous-catégorie", details.get("subcategory", "—")),
        ]
        for row, (label_text, value_text) in enumerate(fields):
            label = QLabel(label_text)
            label.setProperty("class", "detailLabel")
            value = QLabel(str(value_text or "—"))
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if label_text == "Confiance":
                value.setObjectName("scoreValue")
            grid.addWidget(label, row, 0, Qt.AlignTop)
            grid.addWidget(value, row, 1)

        row = len(fields)
        status_label = QLabel("Statut de migration")
        status_label.setProperty("class", "detailLabel")
        self.status_combo = QComboBox()
        self.status_combo.addItems(MIGRATION_STATUSES)
        current_status = details.get("status") or "À vérifier"
        if current_status not in MIGRATION_STATUSES:
            self.status_combo.addItem(current_status)
        self.status_combo.setCurrentText(current_status)
        grid.addWidget(status_label, row, 0, Qt.AlignTop)
        grid.addWidget(self.status_combo, row, 1)

        row += 1
        destination_label = QLabel("Nouvelle adresse")
        destination_label.setProperty("class", "detailLabel")
        self.destination_input = QLineEdit(details.get("destination") or "")
        self.destination_input.setPlaceholderText("nouvelle.adresse@gmail.com")
        self.destination_input.setClearButtonEnabled(True)
        grid.addWidget(destination_label, row, 0, Qt.AlignTop)
        grid.addWidget(self.destination_input, row, 1)

        row += 1
        notes_label = QLabel("Notes")
        notes_label.setProperty("class", "detailLabel")
        self.notes_input = QTextEdit(details.get("notes") or "")
        self.notes_input.setPlaceholderText("Ajouter une note sur la migration...")
        self.notes_input.setFixedHeight(75)
        grid.addWidget(notes_label, row, 0, Qt.AlignTop)
        grid.addWidget(self.notes_input, row, 1)

        row += 1
        signal_label = QLabel("Signaux de détection")
        signal_label.setProperty("class", "detailLabel")
        signal_value = QLabel(self._format_signals(details.get("signals") or []))
        signal_value.setObjectName("signalValue")
        signal_value.setWordWrap(True)
        grid.addWidget(signal_label, row, 0, Qt.AlignTop)
        grid.addWidget(signal_value, row, 1)

        row += 1
        score_label = QLabel("Détail du score")
        score_label.setProperty("class", "detailLabel")
        score_value = QLabel(self._format_score_breakdown(details.get("signals") or []))
        score_value.setObjectName("signalValue")
        score_value.setWordWrap(True)
        grid.addWidget(score_label, row, 0, Qt.AlignTop)
        grid.addWidget(score_value, row, 1)

        row += 1
        reliability_label = QLabel("Fiabilité de la source")
        reliability_label.setProperty("class", "detailLabel")
        reliability_value = QLabel(self._format_reliability(details.get("reliability") or {}))
        reliability_value.setObjectName("signalValue")
        reliability_value.setWordWrap(True)
        grid.addWidget(reliability_label, row, 0, Qt.AlignTop)
        grid.addWidget(reliability_value, row, 1)

        card_layout.addLayout(grid)
        root.addWidget(card)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Enregistrer")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _save(self):
        if not self.account_service_id:
            QMessageBox.warning(self, "Migration", "Impossible de retrouver ce service.")
            return
        session = get_session()
        try:
            link = session.get(AccountService, self.account_service_id)
            if not link:
                QMessageBox.warning(self, "Migration", "Impossible de retrouver ce service.")
                return
            status = self.status_combo.currentText().strip() or "À vérifier"
            link.status = status
            link.destination_email = self.destination_input.text().strip() or None
            link.notes = self.notes_input.toPlainText().strip() or None
            link.migrated_at = datetime.now(timezone.utc) if status == "Migré" else None
            session.commit()
        except Exception as exc:
            session.rollback()
            QMessageBox.critical(self, "Migration", f"Impossible d'enregistrer les modifications : {exc}")
            return
        finally:
            session.close()
        self.accept()

    @staticmethod
    def _format_score(value):
        return "—" if value is None else f"{float(value):.0f} %"

    @staticmethod
    def _format_date(value):
        if not value:
            return "—"
        if isinstance(value, datetime):
            return value.astimezone().strftime("%d/%m/%Y %H:%M")
        return str(value)

    @staticmethod
    def _format_signals(signals):
        labels = {
            "domain": "✓ Domaine correspondant",
            "sender": "✓ Expéditeur correspondant",
            "subject": "✓ Sujet correspondant",
            "keyword": "✓ Mot-clé correspondant",
        }
        return "Aucun signal détaillé disponible" if not signals else "\n".join(labels.get(signal, f"✓ {signal}") for signal in signals)

    @staticmethod
    def _format_score_breakdown(signals):
        weights = {"domain": 50, "sender": 25, "subject": 15, "keyword": 10}
        labels = {"domain": "Domaine exact", "sender": "Expéditeur connu", "subject": "Sujet correspondant", "keyword": "Mot-clé correspondant"}
        unique = set(signals)
        lines = [f"{'✓' if key in unique else '✗'} {labels[key]}    +{weights[key] if key in unique else 0}" for key in ("domain", "sender", "subject", "keyword")]
        total = min(100, sum(weights[key] for key in unique if key in weights))
        return "\n".join(lines) + f"\n────────────────────────\nTotal                    {total} %"

    @staticmethod
    def _format_reliability(reliability):
        if not reliability:
            return "Aucune information de fiabilité disponible"
        lines = [
            "✓ Domaine officiel" if reliability.get("official_domain") else "✗ Domaine officiel non confirmé",
            "✓ Expéditeur connu" if reliability.get("known_sender") else "✗ Expéditeur non reconnu",
            "",
            "Authentification",
        ]
        if not reliability.get("authentication_available"):
            lines.extend(["○ SPF — non disponible", "○ DKIM — non disponible", "○ DMARC — non disponible"])
        else:
            for key, label in (("spf", "SPF"), ("dkim", "DKIM"), ("dmarc", "DMARC")):
                value = reliability.get(key)
                lines.append(f"{'✓' if value else '✗'} {label} — {'pass' if value else 'échec'}")
        return "\n".join(lines)


class ServiceTableDelegate(QStyledItemDelegate):
    ICON_SIZE = 28
    ICON_LEFT_PADDING = 12
    ICON_TEXT_GAP = 8
    TEXT_RIGHT_PADDING = 12

    def paint(self, painter, option, index):
        table = self.parent()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        if index.column() == 0:
            rect = QRectF(4, option.rect.top() + 5, max(0.0, table.viewport().width() - 8), max(0.0, option.rect.height() - 10))
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            painter.fillPath(path, QColor(29, 34, 43))

        text = index.data(Qt.DisplayRole)
        if text is not None:
            painter.setPen(QColor(231, 234, 240))
            painter.setFont(option.font)
            metrics = QFontMetrics(option.font)

            if index.column() == 1:
                icon = index.data(Qt.DecorationRole)
                icon_size = self.ICON_SIZE
                icon_x = option.rect.left() + self.ICON_LEFT_PADDING
                icon_y = option.rect.center().y() - icon_size / 2

                if isinstance(icon, QIcon) and not icon.isNull():
                    icon.paint(
                        painter,
                        int(icon_x),
                        int(icon_y),
                        icon_size,
                        icon_size,
                        Qt.AlignCenter,
                        QIcon.Normal,
                        QIcon.Off,
                    )

                text_left = option.rect.left() + self.ICON_LEFT_PADDING + icon_size + self.ICON_TEXT_GAP
                text_right = option.rect.right() - self.TEXT_RIGHT_PADDING
                text_rect = option.rect.adjusted(
                    int(text_left - option.rect.left()), 0,
                    int(text_right - option.rect.right()), 0,
                )
                display_text = metrics.elidedText(
                    str(text), Qt.ElideRight, max(20, int(text_rect.width()))
                )
                painter.drawText(
                    text_rect,
                    Qt.AlignVCenter | Qt.AlignHCenter,
                    display_text,
                )
            else:
                text_rect = option.rect.adjusted(
                    self.ICON_LEFT_PADDING, 0, -self.TEXT_RIGHT_PADDING, 0
                )
                display_text = metrics.elidedText(str(text), Qt.ElideRight, max(0, text_rect.width()))
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignHCenter, display_text)

        painter.restore()


class ServiceTable(QTableWidget):
    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        for row in range(self.rowCount()):
            y = self.rowViewportPosition(row)
            height = self.rowHeight(row)
            if y > self.viewport().height():
                break
            if y + height < 0:
                continue
            rect = QRectF(4, y + 5, max(0.0, self.viewport().width() - 8), max(0.0, height - 10))
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            painter.fillPath(path, QColor(29, 34, 43))
        painter.end()
        super().paintEvent(event)


class ServicesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.active_account_id = None
        self.live_scan = False
        self.live_account_ids = set()
        self.live_rows = {}
        self.live_account_emails = {}
        self._all_rows = []
        self._all_details = []
        self.row_details = []
        self._status_filters = set()
        self._category_filter = "Toutes les catégories"

        layout = QVBoxLayout(self)
        title = QLabel("Inventaire des services")
        title.setObjectName("title")
        layout.addWidget(title)

        search_container = QFrame()
        search_container.setObjectName("serviceSearchContainer")
        search_container.setStyleSheet("""
            QFrame#serviceSearchContainer { border: 1px solid #303846; border-radius: 10px; background: #171b22; }
            QFrame#serviceSearchContainer:focus-within { border: 1px solid #58677d; }
            QLabel#serviceSearchIcon { border: none; background: transparent; padding-left: 12px; padding-right: 4px; font-size: 17px; }
            QLineEdit#serviceSearchInput { border: none; background: transparent; padding: 0 10px 0 4px; color: #E7EAF0; }
            QLineEdit#serviceSearchInput:hover, QLineEdit#serviceSearchInput:focus { color: #E7EAF0; }
        """)
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)
        icon = QLabel("🔎")
        icon.setObjectName("serviceSearchIcon")
        icon.setAlignment(Qt.AlignCenter)
        search_layout.addWidget(icon)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("serviceSearchInput")
        self.search_input.setPlaceholderText("Rechercher un service, compte ou catégorie...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(38)
        self.search_input.textChanged.connect(self._filter_services)
        search_layout.addWidget(self.search_input, 1)
        layout.addWidget(search_container)

        actions = QHBoxLayout()
        self.status_buttons = {}
        for status in MIGRATION_STATUSES:
            button = QPushButton(status)
            button.setCheckable(True)
            button.setMinimumHeight(34)
            button.clicked.connect(lambda checked, value=status: self._toggle_status_filter(value, checked))
            self.status_buttons[status] = button
            actions.addWidget(button)
        actions.addStretch()

        self.category_combo = QComboBox()
        self.category_combo.setMinimumHeight(34)
        self.category_combo.setMinimumWidth(190)
        self.category_combo.addItem("Toutes les catégories")
        self.category_combo.currentTextChanged.connect(self._set_category_filter)
        actions.addWidget(self.category_combo)

        self.cleanup_button = QPushButton("🧹 Nettoyage")
        self.cleanup_button.setToolTip("Supprimer les résultats issus des scans")
        self.cleanup_button.setMinimumHeight(34)
        self.cleanup_button.clicked.connect(self.cleanup_scanned_services)
        actions.addWidget(self.cleanup_button)
        layout.addLayout(actions)

        self.table = ServiceTable(0, 6)
        self.table.setHorizontalHeaderLabels(["Compte", "Service", "Catégorie", "Confiance", "Traces", "Statut"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignCenter)
        for column in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(column)
            if item:
                item.setTextAlignment(Qt.AlignCenter)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.setMouseTracking(False)
        self.table.setAttribute(Qt.WA_Hover, False)
        self.table.viewport().setAttribute(Qt.WA_Hover, False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_service_context_menu)
        self.table.setStyleSheet("""
            QTableWidget { background: transparent; border: none; gridline-color: transparent; outline: none; color: #E7EAF0; }
            QTableWidget::item { background: transparent; border: none; outline: none; padding: 0; color: #E7EAF0; }
            QTableWidget::item:hover { background: transparent; color: #E7EAF0; }
            QTableWidget::item:selected, QTableWidget::item:focus { background: transparent; color: #E7EAF0; outline: none; border: none; }
            QTableCornerButton::section { background: transparent; border: none; }
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.setIconSize(QSize(28, 28))
        self.table.setItemDelegate(ServiceTableDelegate(self.table))
        layout.addWidget(self.table)

    def _toggle_status_filter(self, status, checked):
        if checked:
            self._status_filters.add(status)
        else:
            self._status_filters.discard(status)
        self._filter_services(self.search_input.text())

    def _set_category_filter(self, category):
        self._category_filter = category or "Toutes les catégories"
        self._filter_services(self.search_input.text())

    def _refresh_categories(self):
        current = self._category_filter
        categories = sorted({str(d.get("category") or "Autre") for d in self._all_details}, key=str.casefold)
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Toutes les catégories")
        self.category_combo.addItems(categories)
        self.category_combo.setCurrentText(current if current in categories or current == "Toutes les catégories" else "Toutes les catégories")
        self._category_filter = self.category_combo.currentText()
        self.category_combo.blockSignals(False)

    def _filter_services(self, text):
        query = (text or "").strip().casefold()
        rows, details = [], []
        for row, detail in zip(self._all_rows, self._all_details):
            status = detail.get("status") or "À vérifier"
            category = str(detail.get("category") or "Autre")
            haystack = " ".join(str(value) for value in row).casefold()
            if query and query not in haystack:
                continue
            if self._status_filters and status not in self._status_filters:
                continue
            if self._category_filter != "Toutes les catégories" and category != self._category_filter:
                continue
            rows.append(row)
            details.append(detail)

        self.row_details = details
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
                item.setForeground(QColor(231, 234, 240))
                item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                if c == 1:
                    detail = details[r]
                    item.setIcon(_service_icon(detail.get("name"), detail.get("category")))
                    item.setToolTip(str(detail.get("name") or "Service"))
                self.table.setItem(r, c, item)
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.table.viewport().update()

    def _resolve_account_service_id(self, details):
        if details.get("account_service_id"):
            return details["account_service_id"]
        account_id = details.get("account_id")
        service_name = details.get("name")
        if not account_id or not service_name:
            return None
        session = get_session()
        try:
            link = session.scalar(select(AccountService).join(AccountService.service).where(AccountService.account_id == account_id, Service.name == service_name))
            if link:
                details["account_service_id"] = link.id
                return link.id
        finally:
            session.close()
        return None

    def _show_service_context_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid() or not (0 <= index.row() < len(self.row_details)):
            return
        row = index.row()
        details = self.row_details[row]
        self._resolve_account_service_id(details)
        menu = QMenu(self.table)
        menu.setStyleSheet("""
            QMenu { background: #171b22; border: 1px solid #303846; border-radius: 8px; padding: 4px; }
            QMenu::item { color: #E7EAF0; background: transparent; padding: 8px 18px; border-radius: 5px; }
            QMenu::item:selected { color: #E7EAF0; background: #303846; }
        """)
        details_action = menu.addAction("Plus de détails")
        status_menu = menu.addMenu("Statut de migration")
        status_actions = {status_menu.addAction(status): status for status in MIGRATION_STATUSES}
        destination_action = menu.addAction("Définir l'adresse de destination…")
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen == details_action:
            self._open_details_for_row(row, index.column())
        elif chosen == destination_action:
            self._set_destination_for_row(row)
        elif chosen in status_actions:
            self._set_status_for_row(row, status_actions[chosen])

    def _set_status_for_row(self, row, status):
        if not (0 <= row < len(self.row_details)):
            return
        details = self.row_details[row]
        account_service_id = self._resolve_account_service_id(details)
        if not account_service_id:
            return
        session = get_session()
        try:
            link = session.get(AccountService, account_service_id)
            if not link:
                return
            link.status = status
            link.migrated_at = datetime.now(timezone.utc) if status == "Migré" else None
            session.commit()
        finally:
            session.close()
        self.load_services()

    def _set_destination_for_row(self, row):
        if not (0 <= row < len(self.row_details)):
            return
        details = self.row_details[row]
        account_service_id = self._resolve_account_service_id(details)
        if not account_service_id:
            return
        current = details.get("destination_email") or ""
        value, accepted = QInputDialog.getText(self, "Adresse de destination", "Nouvelle adresse :", text=current)
        if not accepted:
            return
        session = get_session()
        try:
            link = session.get(AccountService, account_service_id)
            if link:
                link.destination_email = value.strip() or None
                session.commit()
        finally:
            session.close()
        self.load_services()

    def _open_details_for_row(self, row, column=0):
        if not (0 <= row < len(self.row_details)):
            return
        dialog = ServiceDetailsDialog(self.row_details[row], self)
        if dialog.exec():
            self.load_services()

    def cleanup_scanned_services(self):
        session = get_session()
        try:
            account_services = session.scalars(select(AccountService)).all()
            ids = [link.id for link in account_services if link.service and link.service.name]
            if not ids:
                return
            session.execute(delete(ScanTrace).where(ScanTrace.account_service_id.in_(ids)))
            session.execute(delete(AccountService).where(AccountService.id.in_(ids)))
            session.commit()
        finally:
            session.close()
        self.load_services()
