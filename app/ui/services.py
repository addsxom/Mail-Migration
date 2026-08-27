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
    QWidget, QLineEdit, QStyledItemDelegate, QMenu, QTextEdit, QInputDialog,
)
from sqlalchemy import delete, select

from app.database.database import get_session
from app.database.models import GoogleAccount, AccountService, ScanTrace, Service
from app.database.repositories import get_accounts, get_account_services

MIGRATION_STATUSES = ["À vérifier", "À migrer", "Migré", "Abandonné"]

_ICON_CACHE = {}
SERVICE_DOMAINS = {"amazon":"amazon.com","apple":"apple.com","discord":"discord.com","dropbox":"dropbox.com","epic-games":"epicgames.com","epicgames":"epicgames.com","facebook":"facebook.com","google":"google.com","google-drive":"drive.google.com","instagram":"instagram.com","linkedin":"linkedin.com","microsoft":"microsoft.com","microsoft-365":"microsoft.com","netflix":"netflix.com","nintendo":"nintendo.com","nintendo-switch":"nintendo.com","paypal":"paypal.com","playstation":"playstation.com","reddit":"reddit.com","roblox":"roblox.com","samsung":"samsung.com","spotify":"spotify.com","steam":"steampowered.com","tiktok":"tiktok.com","twitch":"twitch.tv","twitter":"x.com","x":"x.com","ubisoft":"ubisoft.com","xbox":"xbox.com","youtube":"youtube.com","yahoo":"yahoo.com","airbnb":"airbnb.com","adobe":"adobe.com","canva":"canva.com","github":"github.com","gitlab":"gitlab.com","nvidia":"nvidia.com","ea":"ea.com","ea-games":"ea.com","battle-net":"battle.net","blizzard":"blizzard.com","riot-games":"riotgames.com","valorant":"playvalorant.com","2k":"2k.com","nba-2k":"nba.2k.com","take-two":"taketwointeractivesoftware.com","snapchat":"snapchat.com","telegram":"telegram.org","whatsapp":"whatsapp.com","xhamster":"xhamster.com","aliexpress":"aliexpress.com","zalando":"zalando.ch","digitec":"digitec.ch","galaxus":"galaxus.ch","ricardo":"ricardo.ch","swisscom":"swisscom.ch","sunrise":"sunrise.ch","salt":"salt.ch"}

def _service_icon_key(name): return re.sub(r"[^a-z0-9]+","-",str(name or "service").strip().lower()).strip("-") or "service"
def _service_initials(name):
    words=[w for w in re.split(r"\s+",str(name or "Service").strip()) if w]
    if not words:return "?"
    if len(words)==1:
        letters=re.sub(r"[^A-Za-z0-9]","",words[0]); return (letters[:2] or "?").upper()
    return (words[0][0]+words[1][0]).upper()
def _service_domain(name):
    key=_service_icon_key(name)
    if key in SERVICE_DOMAINS:return SERVICE_DOMAINS[key]
    compact=key.replace("-","")
    for known_key,domain in SERVICE_DOMAINS.items():
        if known_key.replace("-","")==compact:return domain
    return None
def _fallback_service_icon(name):
    size=32; pixmap=QPixmap(size,size); pixmap.fill(Qt.transparent); painter=QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing,True); painter.setBrush(QColor(48,56,70)); painter.setPen(Qt.NoPen); painter.drawEllipse(1,1,size-2,size-2); painter.setPen(QColor(231,234,240)); font=QFont(); font.setBold(True); font.setPointSize(9); painter.setFont(font); painter.drawText(pixmap.rect(),Qt.AlignCenter,_service_initials(name)); painter.end(); return QIcon(pixmap)
def _service_icon(name,category=""):
    key=(_service_icon_key(name),str(category or ""))
    if key in _ICON_CACHE:return _ICON_CACHE[key]
    assets_dir=Path(__file__).resolve().parents[2]/"assets"/"service_logos"; local_key=key[0]
    for suffix in (".png",".jpg",".jpeg",".svg"):
        candidate=assets_dir/f"{local_key}{suffix}"
        if candidate.exists():
            icon=QIcon(str(candidate)); _ICON_CACHE[key]=icon; return icon
    domain=_service_domain(name)
    if domain:
        try:
            url=f"https://www.google.com/s2/favicons?sz=64&domain={quote(domain)}"; request=Request(url,headers={"User-Agent":"Mail-Migration/1.0"})
            with urlopen(request,timeout=2.5) as response:data=response.read()
            pixmap=QPixmap()
            if pixmap.loadFromData(data):
                icon=QIcon(pixmap); _ICON_CACHE[key]=icon; return icon
        except Exception:pass
    icon=_fallback_service_icon(name); _ICON_CACHE[key]=icon; return icon

class ServiceDetailsDialog(QDialog):
    def __init__(self,details,parent=None):
        super().__init__(parent); self.details=details; self.account_service_id=details.get("account_service_id"); self.setWindowTitle(f"Détails — {details.get('name','Service')}"); self.setModal(True); self.setMinimumWidth(600); self.setMaximumWidth(760)
        root=QVBoxLayout(self); root.setContentsMargins(18,18,18,18); root.setSpacing(12); card=QFrame(); card.setObjectName("serviceDetailsCard"); card.setStyleSheet("QFrame#serviceDetailsCard{border:1px solid #303846;border-radius:14px;background:#171b22;} QLabel#serviceDetailsTitle{font-size:22px;font-weight:700;} QLabel#serviceDetailsSubtitle{color:#9AA2AF;} QLabel.detailLabel{color:#9AA2AF;font-size:12px;} QLabel.signalValue{color:#E7EAF0;} QLabel.scoreValue{font-size:18px;font-weight:700;} QLineEdit,QComboBox,QTextEdit{border:1px solid #303846;border-radius:8px;background:#11151b;color:#E7EAF0;padding:7px 9px;} QPushButton{padding:8px 16px;border-radius:8px;}"); cl=QVBoxLayout(card); cl.setContentsMargins(18,18,18,18); cl.setSpacing(14); title=QLabel(details.get("name","Service")); title.setObjectName("serviceDetailsTitle"); cl.addWidget(title); subtitle=QLabel(details.get("category","Autre")); subtitle.setObjectName("serviceDetailsSubtitle"); cl.addWidget(subtitle)
        grid=QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(10); fields=[("Compte Gmail",details.get("account_email","—")),("Confiance",self._format_score(details.get("score"))), ("Traces",str(details.get("count",0))), ("Priorité",details.get("priority","Normale")), ("Première détection",self._format_date(details.get("first_detected_at"))), ("Dernière détection",self._format_date(details.get("last_detected_at"))), ("Sous-catégorie",details.get("subcategory","—"))]
        for row,(label_text,value_text) in enumerate(fields):
            label=QLabel(label_text); label.setProperty("class","detailLabel"); value=QLabel(str(value_text or "—")); value.setWordWrap(True); value.setTextInteractionFlags(Qt.TextSelectableByMouse); grid.addWidget(label,row,0,Qt.AlignTop); grid.addWidget(value,row,1)
        row=len(fields); status_label=QLabel("Statut de migration"); status_label.setProperty("class","detailLabel"); self.status_combo=QComboBox(); self.status_combo.addItems(MIGRATION_STATUSES); current_status=details.get("status") or "À vérifier"; self.status_combo.setCurrentText(current_status); grid.addWidget(status_label,row,0); grid.addWidget(self.status_combo,row,1); row+=1; destination_label=QLabel("Nouvelle adresse"); destination_label.setProperty("class","detailLabel"); self.destination_input=QLineEdit(details.get("destination") or ""); grid.addWidget(destination_label,row,0); grid.addWidget(self.destination_input,row,1); row+=1; notes_label=QLabel("Notes"); notes_label.setProperty("class","detailLabel"); self.notes_input=QTextEdit(details.get("notes") or ""); self.notes_input.setFixedHeight(75); grid.addWidget(notes_label,row,0); grid.addWidget(self.notes_input,row,1); cl.addLayout(grid); root.addWidget(card); buttons=QHBoxLayout(); buttons.addStretch(); cancel=QPushButton("Annuler"); cancel.clicked.connect(self.reject); buttons.addWidget(cancel); save=QPushButton("Enregistrer"); save.clicked.connect(self._save); buttons.addWidget(save); root.addLayout(buttons)
    def _save(self):
        if not self.account_service_id:return
        session=get_session()
        try:
            link=session.get(AccountService,self.account_service_id)
            if link: link.status=self.status_combo.currentText(); link.destination_email=self.destination_input.text().strip() or None; link.notes=self.notes_input.toPlainText().strip() or None; link.migrated_at=datetime.now(timezone.utc) if link.status=="Migré" else None; session.commit()
        finally:session.close()
        self.accept()
    @staticmethod
    def _format_score(value):return "—" if value is None else f"{float(value):.0f} %"
    @staticmethod
    def _format_date(value):return "—" if not value else (value.astimezone().strftime("%d/%m/%Y %H:%M") if isinstance(value,datetime) else str(value))
    @staticmethod
    def _format_signals(signals):return "Aucun signal détaillé disponible" if not signals else "\n".join(f"✓ {s}" for s in signals)
    @staticmethod
    def _format_score_breakdown(signals):return ""
    @staticmethod
    def _format_reliability(reliability):return ""

class ServiceTableDelegate(QStyledItemDelegate):
    ICON_SIZE=28; ICON_LEFT_PADDING=12; ICON_TEXT_GAP=8; TEXT_RIGHT_PADDING=12
    def paint(self,painter,option,index):
        painter.save(); painter.setRenderHint(QPainter.Antialiasing,True); text=index.data(Qt.DisplayRole)
        if text is not None:
            painter.setPen(QColor(231,234,240)); painter.setFont(option.font); metrics=QFontMetrics(option.font)
            if index.column()==1:
                icon=index.data(Qt.DecorationRole); icon_size=self.ICON_SIZE; icon_x=option.rect.left()+self.ICON_LEFT_PADDING; icon_y=option.rect.center().y()-icon_size/2
                if isinstance(icon,QIcon) and not icon.isNull():icon.paint(painter,int(icon_x),int(icon_y),icon_size,icon_size,Qt.AlignCenter,QIcon.Normal,QIcon.Off)
                text_rect=option.rect.adjusted(self.ICON_LEFT_PADDING+icon_size+self.ICON_TEXT_GAP,0,-self.TEXT_RIGHT_PADDING,0); painter.drawText(text_rect,Qt.AlignVCenter|Qt.AlignHCenter,metrics.elidedText(str(text),Qt.ElideRight,max(20,text_rect.width())))
            else:
                text_rect=option.rect.adjusted(self.ICON_LEFT_PADDING,0,-self.TEXT_RIGHT_PADDING,0); painter.drawText(text_rect,Qt.AlignVCenter|Qt.AlignHCenter,metrics.elidedText(str(text),Qt.ElideRight,max(0,text_rect.width())))
        painter.restore()

class ServiceTable(QTableWidget):
    def paintEvent(self,event):
        super().paintEvent(event)

class ServicesPage(QWidget):
    def __init__(self):
        super().__init__(); self.active_account_id=None; self.live_scan=False; self.live_account_ids=set(); self.live_rows={}; self.live_account_emails={}; self._all_rows=[]; self._all_details=[]; self.row_details=[]; self._status_filters=set(); self._category_filter="Toutes les catégories"
        layout=QVBoxLayout(self); title=QLabel("Inventaire des services"); title.setObjectName("title"); layout.addWidget(title)
        search=QLineEdit(); search.setPlaceholderText("Rechercher un service, compte ou catégorie..."); search.textChanged.connect(self._filter_services); self.search_input=search; layout.addWidget(search)
        actions=QHBoxLayout(); self.status_buttons={}
        for status in MIGRATION_STATUSES:
            button=QPushButton(status); button.setCheckable(True); button.clicked.connect(lambda checked,value=status:self._toggle_status_filter(value,checked)); self.status_buttons[status]=button; actions.addWidget(button)
        actions.addStretch(); self.category_combo=QComboBox(); self.category_combo.addItem("Toutes les catégories"); self.category_combo.currentTextChanged.connect(self._set_category_filter); actions.addWidget(self.category_combo); self.cleanup_button=QPushButton("🧹 Nettoyage"); self.cleanup_button.clicked.connect(self.cleanup_scanned_services); actions.addWidget(self.cleanup_button); layout.addLayout(actions)
        self.table=ServiceTable(0,6); self.table.setHorizontalHeaderLabels(["Compte","Service","Catégorie","Confiance","Traces","Statut"]); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.verticalHeader().setVisible(False); self.table.verticalHeader().setDefaultSectionSize(54); self.table.setIconSize(QSize(28,28)); self.table.setSelectionMode(QTableWidget.NoSelection); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setContextMenuPolicy(Qt.CustomContextMenu); self.table.customContextMenuRequested.connect(self._show_service_context_menu); self.table.setItemDelegate(ServiceTableDelegate(self.table)); layout.addWidget(self.table)
    def _toggle_status_filter(self,status,checked):
        if checked:self._status_filters.add(status)
        else:self._status_filters.discard(status)
        self._filter_services(self.search_input.text())
    def _set_category_filter(self,category):self._category_filter=category or "Toutes les catégories"; self._filter_services(self.search_input.text())
    def _refresh_categories(self):
        current=self._category_filter; categories=sorted({str(d.get("category") or "Autre") for d in self._all_details},key=str.casefold); self.category_combo.blockSignals(True); self.category_combo.clear(); self.category_combo.addItem("Toutes les catégories"); self.category_combo.addItems(categories); self.category_combo.setCurrentText(current if current in categories or current=="Toutes les catégories" else "Toutes les catégories"); self._category_filter=self.category_combo.currentText(); self.category_combo.blockSignals(False)
    def _filter_services(self,text):
        query=(text or "").strip().casefold(); rows=[]; details=[]
        for row,detail in zip(self._all_rows,self._all_details):
            if query and query not in " ".join(str(v) for v in row).casefold():continue
            if self._status_filters and (detail.get("status") or "À vérifier") not in self._status_filters:continue
            if self._category_filter!="Toutes les catégories" and str(detail.get("category") or "Autre")!=self._category_filter:continue
            rows.append(row); details.append(detail)
        self.row_details=details; self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,value in enumerate(row):
                item=QTableWidgetItem(str(value)); item.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
                if c==1:item.setIcon(_service_icon(details[r].get("name"),details[r].get("category")))
                self.table.setItem(r,c,item)
    def _resolve_account_service_id(self,details):
        if details.get("account_service_id"):return details["account_service_id"]
        return None
    def _show_service_context_menu(self,position):pass
    def _set_status_for_row(self,row,status):pass
    def _set_destination_for_row(self,row):pass
    def _open_details_for_row(self,row,column=0):
        if 0<=row<len(self.row_details):
            if ServiceDetailsDialog(self.row_details[row],self).exec():self.load_services()
    def cleanup_scanned_services(self):
        session=get_session()
        try:session.execute(delete(ScanTrace)); session.execute(delete(AccountService)); session.commit()
        finally:session.close()
        self.load_services()
    def set_active_account(self,account_id):
        if self.live_scan:return
        self.active_account_id=account_id; self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear(); self.refresh()
    @staticmethod
    def _get_account_email(account_id):
        session=get_session()
        try:
            account=session.get(GoogleAccount,account_id); return account.email if account else ""
        finally:session.close()
    def start_live_scan(self,account_id):
        if not self.live_scan:self.live_scan=True; self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear()
        self.live_account_ids.add(account_id); email=self._get_account_email(account_id)
        if email:self.live_account_emails[account_id]=email
        self._render_live_rows()
    def update_live_detection(self,account_id,data):
        if not self.live_scan or account_id not in self.live_account_ids:return
        key=(account_id,data.get("service_id") or data.get("name","").strip().lower()); email=data.get("account_email") or self.live_account_emails.get(account_id,"")
        self.live_rows[key]={"account_id":account_id,"account_service_id":data.get("account_service_id"),"account_email":email,"name":data.get("name","Service inconnu"),"category":data.get("category","Autre"),"score":float(data.get("score",0)),"count":int(data.get("count",0)),"status":data.get("status","À vérifier"),"priority":data.get("priority","Normale"),"destination":data.get("destination_email"),"notes":data.get("notes"),"first_detected_at":data.get("first_detected_at"),"last_detected_at":data.get("last_detected_at"),"signals":data.get("signals",[]),"reliability":data.get("reliability",{})}; self._render_live_rows()
    def finish_live_scan(self,mode):
        if not self.live_scan:return
        if mode==-1:return self.keep_live_results_after_cancel()
        self.live_scan=False; self.refresh(); self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear()
    def keep_live_results_after_cancel(self):
        self.live_scan=False; self._render_live_rows(); self.live_account_ids.clear(); self.live_account_emails.clear()
    def _render_live_rows(self):
        items=sorted(self.live_rows.values(),key=lambda x:(-x["score"],x["name"].lower(),x["account_email"].lower())); self._set_rows([(i.get("account_email",""),i["name"],i["category"],f'{i["score"]:.0f} %',str(i["count"]),i["status"]) for i in items],items)
    def _set_rows(self,rows,details=None):self._all_rows=list(rows); self._all_details=list(details or []); self._refresh_categories(); self._filter_services(self.search_input.text())
    def refresh(self):
        session=get_session(); rows=[]; details=[]
        try:
            for account in get_accounts(session):
                if self.active_account_id is not None and account.id!=self.active_account_id:continue
                for link in get_account_services(session,account.id):
                    service=link.service; status=link.status or "À vérifier"; details.append({"account_id":account.id,"account_service_id":link.id,"account_email":account.email,"name":service.name,"category":service.category,"subcategory":service.subcategory,"score":link.confidence_score,"count":link.trace_count,"status":status,"priority":link.priority,"destination":link.destination_email,"notes":link.notes,"first_detected_at":link.first_detected_at,"last_detected_at":link.last_detected_at,"migrated_at":link.migrated_at,"signals":[],"reliability":{}}); rows.append((account.email,service.name,service.category,f"{link.confidence_score:.0f} %",str(link.trace_count),status))
        finally:session.close()
        if not self.live_scan:self._set_rows(rows,details)
    load_services=refresh
