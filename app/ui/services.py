from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen
from PySide6.QtCore import Qt, QRectF, QSize, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFontMetrics, QIcon, QPixmap, QFont
from PySide6.QtWidgets import QComboBox, QDialog, QFrame, QGridLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit, QStyledItemDelegate, QMenu, QTextEdit, QInputDialog
from sqlalchemy import delete, select
from app.database.database import get_session
from app.database.models import GoogleAccount, AccountService, ScanTrace, Service
from app.database.repositories import get_accounts, get_account_services

MIGRATION_STATUSES=["À vérifier","À migrer","Migré","Abandonné"]
_ICON_CACHE={}
SERVICE_DOMAINS={"amazon":"amazon.com","apple":"apple.com","discord":"discord.com","dropbox":"dropbox.com","epic-games":"epicgames.com","epicgames":"epicgames.com","facebook":"facebook.com","google":"google.com","google-drive":"drive.google.com","instagram":"instagram.com","linkedin":"linkedin.com","microsoft":"microsoft.com","microsoft-365":"microsoft.com","netflix":"netflix.com","nintendo":"nintendo.com","nintendo-switch":"nintendo.com","paypal":"paypal.com","playstation":"playstation.com","reddit":"reddit.com","roblox":"roblox.com","samsung":"samsung.com","spotify":"spotify.com","steam":"steampowered.com","tiktok":"tiktok.com","twitch":"twitch.tv","twitter":"x.com","x":"x.com","ubisoft":"ubisoft.com","xbox":"xbox.com","youtube":"youtube.com","yahoo":"yahoo.com","airbnb":"airbnb.com","adobe":"adobe.com","canva":"canva.com","github":"github.com","gitlab":"gitlab.com","nvidia":"nvidia.com","ea":"ea.com","ea-games":"ea.com","battle-net":"battle.net","blizzard":"blizzard.com","riot-games":"riotgames.com","valorant":"playvalorant.com","2k":"2k.com","nba-2k":"nba.2k.com","take-two":"taketwointeractivesoftware.com","snapchat":"snapchat.com","telegram":"telegram.org","whatsapp":"whatsapp.com","aliexpress":"aliexpress.com","zalando":"zalando.ch","digitec":"digitec.ch","galaxus":"galaxus.ch","ricardo":"ricardo.ch","swisscom":"swisscom.ch","sunrise":"sunrise.ch","salt":"salt.ch"}

def _service_icon_key(name): return re.sub(r"[^a-z0-9]+","-",str(name or "service").strip().lower()).strip("-") or "service"
def _service_initials(name):
    words=[w for w in re.split(r"\s+",str(name or "Service").strip()) if w]
    if not words:return "?"
    if len(words)==1:return (re.sub(r"[^A-Za-z0-9]","",words[0])[:2] or "?").upper()
    return (words[0][0]+words[1][0]).upper()
def _catalog_domains(name):
    try:
        from app.services.builtin_catalog import CATALOG
        wanted=_service_icon_key(name); result=[]
        for item in CATALOG:
            if _service_icon_key(item.get("name"))==wanted: result.extend(str(d).strip().lower() for d in item.get("domains",[]) if d)
        return list(dict.fromkeys(result))
    except Exception:return []
def _service_domain(name):
    domains=_catalog_domains(name)
    if domains:return domains[0]
    key=_service_icon_key(name)
    if key in SERVICE_DOMAINS:return SERVICE_DOMAINS[key]
    compact=key.replace("-","")
    for known,domain in SERVICE_DOMAINS.items():
        if known.replace("-","")==compact:return domain
    return None
def _fallback_service_icon(name):
    pix=QPixmap(32,32); pix.fill(Qt.transparent); p=QPainter(pix); p.setRenderHint(QPainter.Antialiasing,True); p.setBrush(QColor(48,56,70)); p.setPen(Qt.NoPen); p.drawEllipse(1,1,30,30); p.setPen(QColor(231,234,240)); f=QFont(); f.setBold(True); f.setPointSize(9); p.setFont(f); p.drawText(pix.rect(),Qt.AlignCenter,_service_initials(name)); p.end(); return QIcon(pix)
def _service_icon(name,category=""):
    key=(_service_icon_key(name),str(category or ""))
    if key in _ICON_CACHE:return _ICON_CACHE[key]
    assets=Path(__file__).resolve().parents[2]/"assets"/"service_logos"; local=key[0]
    for suffix in (".png",".jpg",".jpeg",".svg"):
        candidate=assets/f"{local}{suffix}"
        if candidate.exists():
            icon=QIcon(str(candidate)); _ICON_CACHE[key]=icon
            return icon
    domain=_service_domain(name)
    if domain:
        try:
            req=Request(f"https://www.google.com/s2/favicons?sz=64&domain={quote(domain)}",headers={"User-Agent":"Mail-Migration/1.0"})
            with urlopen(req,timeout=2.5) as response:data=response.read()
            pix=QPixmap()
            if pix.loadFromData(data):
                icon=QIcon(pix); _ICON_CACHE[key]=icon
                return icon
        except Exception:pass
    icon=_fallback_service_icon(name); _ICON_CACHE[key]=icon; return icon

class ServiceDetailsDialog(QDialog):
    def __init__(self,details,parent=None):
        super().__init__(parent)
        self.details=details
        self.account_service_id=details.get("account_service_id")
        self.setWindowTitle(f"Détails — {details.get('name','Service')}")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMaximumWidth(760)
        root=QVBoxLayout(self); root.setContentsMargins(18,18,18,18); root.setSpacing(12)
        card=QFrame(); card.setObjectName("serviceDetailsCard"); card.setStyleSheet("""
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
        cl=QVBoxLayout(card); cl.setContentsMargins(18,18,18,18); cl.setSpacing(14)
        title=QLabel(details.get("name","Service")); title.setObjectName("serviceDetailsTitle"); cl.addWidget(title)
        subtitle=QLabel(details.get("category","Autre")); subtitle.setObjectName("serviceDetailsSubtitle"); cl.addWidget(subtitle)
        grid=QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(10)
        fields=[("Compte Gmail",details.get("account_email","—")),("Confiance",self._format_score(details.get("score"))),("Traces",str(details.get("count",0))),("Priorité",details.get("priority","Normale")),("Première détection",self._format_date(details.get("first_detected_at"))),("Dernière détection",self._format_date(details.get("last_detected_at"))),("Sous-catégorie",details.get("subcategory","—"))]
        for row,(label_text,value_text) in enumerate(fields):
            label=QLabel(label_text); label.setProperty("class","detailLabel")
            value=QLabel(str(value_text or "—")); value.setWordWrap(True); value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if label_text=="Confiance":value.setObjectName("scoreValue")
            grid.addWidget(label,row,0,Qt.AlignTop); grid.addWidget(value,row,1)
        row=len(fields)
        status_label=QLabel("Statut de migration"); status_label.setProperty("class","detailLabel")
        self.status_combo=QComboBox(); self.status_combo.addItems(MIGRATION_STATUSES)
        current_status=details.get("status") or "À vérifier"
        if current_status not in MIGRATION_STATUSES:self.status_combo.addItem(current_status)
        self.status_combo.setCurrentText(current_status); grid.addWidget(status_label,row,0,Qt.AlignTop); grid.addWidget(self.status_combo,row,1); row+=1
        destination_label=QLabel("Nouvelle adresse"); destination_label.setProperty("class","detailLabel")
        self.destination_input=QLineEdit(details.get("destination") or ""); self.destination_input.setPlaceholderText("nouvelle.adresse@gmail.com"); self.destination_input.setClearButtonEnabled(True)
        grid.addWidget(destination_label,row,0,Qt.AlignTop); grid.addWidget(self.destination_input,row,1); row+=1
        notes_label=QLabel("Notes"); notes_label.setProperty("class","detailLabel")
        self.notes_input=QTextEdit(details.get("notes") or ""); self.notes_input.setPlaceholderText("Ajouter une note sur la migration..."); self.notes_input.setFixedHeight(75)
        grid.addWidget(notes_label,row,0,Qt.AlignTop); grid.addWidget(self.notes_input,row,1); row+=1
        signal_label=QLabel("Signaux de détection"); signal_label.setProperty("class","detailLabel")
        signal_value=QLabel(self._format_signals(details.get("signals") or [])); signal_value.setObjectName("signalValue"); signal_value.setWordWrap(True)
        grid.addWidget(signal_label,row,0,Qt.AlignTop); grid.addWidget(signal_value,row,1); row+=1
        score_label=QLabel("Détail du score"); score_label.setProperty("class","detailLabel")
        score_value=QLabel(self._format_score_breakdown(details.get("signals") or [])); score_value.setObjectName("signalValue"); score_value.setWordWrap(True)
        grid.addWidget(score_label,row,0,Qt.AlignTop); grid.addWidget(score_value,row,1); row+=1
        reliability_label=QLabel("Fiabilité de la source"); reliability_label.setProperty("class","detailLabel")
        reliability_value=QLabel(self._format_reliability(details.get("reliability") or {})); reliability_value.setObjectName("signalValue"); reliability_value.setWordWrap(True)
        grid.addWidget(reliability_label,row,0,Qt.AlignTop); grid.addWidget(reliability_value,row,1)
        cl.addLayout(grid); root.addWidget(card)
        buttons=QHBoxLayout(); buttons.addStretch(); cancel=QPushButton("Annuler"); cancel.clicked.connect(self.reject); buttons.addWidget(cancel)
        self.save_button=QPushButton("Enregistrer"); self.save_button.setDefault(True); self.save_button.clicked.connect(self._save); buttons.addWidget(self.save_button); root.addLayout(buttons)
        if not self.account_service_id:
            self.save_button.setEnabled(False); self.save_button.setToolTip("Disponible après l'enregistrement du service")
    def _save(self):
        if not self.account_service_id:
            QMessageBox.warning(self,"Migration","Impossible de retrouver ce service."); return
        session=get_session()
        try:
            link=session.get(AccountService,self.account_service_id)
            if not link:
                QMessageBox.warning(self,"Migration","Impossible de retrouver ce service."); return
            status=self.status_combo.currentText().strip(); destination=self.destination_input.text().strip() or None; notes=self.notes_input.toPlainText().strip() or None
            link.status=status; link.destination_email=destination; link.notes=notes; link.migrated_at=datetime.now(timezone.utc) if status=="Migré" else None; session.commit()
        except Exception as exc:
            session.rollback(); QMessageBox.critical(self,"Migration",f"Impossible d'enregistrer les modifications : {exc}"); return
        finally:session.close()
        self.accept()
    @staticmethod
    def _format_score(value): return "—" if value is None else f"{float(value):.0f} %"
    @staticmethod
    def _format_date(value): return "—" if not value else (value.astimezone().strftime("%d/%m/%Y %H:%M") if isinstance(value,datetime) else str(value))
    @staticmethod
    def _format_signals(signals):
        labels={"domain":"✓ Domaine correspondant","sender":"✓ Expéditeur correspondant","subject":"✓ Sujet correspondant","keyword":"✓ Mot-clé correspondant"}
        if not signals:return "Aucun signal détaillé disponible"
        return "\n".join(labels.get(signal,f"✓ {signal}") for signal in signals)
    @staticmethod
    def _format_score_breakdown(signals):
        weights={"domain":50,"sender":25,"subject":15,"keyword":10}; labels={"domain":"Domaine exact","sender":"Expéditeur connu","subject":"Sujet correspondant","keyword":"Mot-clé correspondant"}; unique=set(signals)
        lines=[f"{'✓' if key in unique else '✗'} {labels[key]}    +{weights[key] if key in unique else 0}" for key in ("domain","sender","subject","keyword")]
        total=min(100,sum(weights[key] for key in unique if key in weights))
        return "\n".join(lines)+"\n────────────────────────\nTotal                    "+f"{total} %"
    @staticmethod
    def _format_reliability(reliability):
        if not reliability:return "Aucune information de fiabilité disponible"
        lines=["✓ Domaine officiel" if reliability.get("official_domain") else "✗ Domaine officiel non confirmé","✓ Expéditeur connu" if reliability.get("known_sender") else "✗ Expéditeur non reconnu","","Authentification"]
        if not reliability.get("authentication_available"):
            lines.extend(["○ SPF — non disponible","○ DKIM — non disponible","○ DMARC — non disponible"])
        else:
            for key,label in (("spf","SPF"),("dkim","DKIM"),("dmarc","DMARC")):
                value=reliability.get(key); lines.append(f"{'✓' if value else '✗'} {label} — {'pass' if value else 'échec'}")
        return "\n".join(lines)

class ServiceTableDelegate(QStyledItemDelegate):
    ICON_SIZE=28; ICON_LEFT_PADDING=12; ICON_TEXT_GAP=8; TEXT_RIGHT_PADDING=12
    def paint(self,painter,option,index):
        painter.save(); painter.setRenderHint(QPainter.Antialiasing,True); text=index.data(Qt.DisplayRole)
        if text is not None:
            painter.setPen(QColor(231,234,240)); painter.setFont(option.font); metrics=QFontMetrics(option.font)
            if index.column()==1:
                icon=index.data(Qt.DecorationRole); x=option.rect.left()+self.ICON_LEFT_PADDING; y=option.rect.center().y()-self.ICON_SIZE/2
                if isinstance(icon,QIcon) and not icon.isNull():icon.paint(painter,int(x),int(y),self.ICON_SIZE,self.ICON_SIZE,Qt.AlignCenter,QIcon.Normal,QIcon.Off)
                rect=option.rect.adjusted(self.ICON_LEFT_PADDING+self.ICON_SIZE+self.ICON_TEXT_GAP,0,-self.TEXT_RIGHT_PADDING,0)
            else:rect=option.rect.adjusted(self.ICON_LEFT_PADDING,0,-self.TEXT_RIGHT_PADDING,0)
            painter.drawText(rect,Qt.AlignVCenter|Qt.AlignHCenter,metrics.elidedText(str(text),Qt.ElideRight,max(0,rect.width())))
        painter.restore()

class ServiceTable(QTableWidget):
    def paintEvent(self,event):
        painter=QPainter(self.viewport()); painter.setRenderHint(QPainter.Antialiasing,True)
        first=max(0,self.rowAt(0)); last=self.rowAt(self.viewport().height()-1)
        if last<0:last=self.rowCount()-1
        for row in range(first,last+1):
            y=self.rowViewportPosition(row); h=self.rowHeight(row); rect=QRectF(5,y+4,max(0.0,self.viewport().width()-10),max(0.0,h-8)); path=QPainterPath(); path.addRoundedRect(rect,11,11); painter.fillPath(path,QColor(29,34,43))
        painter.end(); super().paintEvent(event)

class ServicesPage(QWidget):
    def __init__(self):
        super().__init__(); self.active_account_id=None; self.live_scan=False; self.live_account_ids=set(); self.live_rows={}; self.live_account_emails={}; self._all_rows=[]; self._all_details=[]; self.row_details=[]; self._status_filters=set(); self._category_filter="Toutes les catégories"; self._live_render_pending=False; self._icon_loading=False
        layout=QVBoxLayout(self); title=QLabel("Inventaire des services"); title.setObjectName("title"); layout.addWidget(title)
        search_container=QFrame(); search_container.setObjectName("serviceSearchContainer"); search_container.setStyleSheet("QFrame#serviceSearchContainer{border:1px solid #303846;border-radius:10px;background:#171b22;} QFrame#serviceSearchContainer:focus-within{border:1px solid #58677d;} QLabel#serviceSearchIcon{border:none;background:transparent;padding-left:12px;padding-right:4px;font-size:17px;} QLineEdit#serviceSearchInput{border:none;background:transparent;padding:0 10px 0 4px;color:#E7EAF0;} QLineEdit#serviceSearchInput:focus{border:none;}")
        search_layout=QHBoxLayout(search_container); search_layout.setContentsMargins(0,0,0,0); search_layout.setSpacing(0); search_icon=QLabel("🔎"); search_icon.setObjectName("serviceSearchIcon"); search_icon.setAlignment(Qt.AlignCenter); search_layout.addWidget(search_icon)
        search=QLineEdit(); search.setObjectName("serviceSearchInput"); search.setPlaceholderText("Rechercher un service, compte ou catégorie..."); search.setClearButtonEnabled(True); search.setMinimumHeight(38); search.textChanged.connect(self._filter_services); self.search_input=search; search_layout.addWidget(search,1); layout.addWidget(search_container)
        actions=QHBoxLayout(); self.status_buttons={}
        for status in MIGRATION_STATUSES:
            b=QPushButton(status); b.setCheckable(True); b.clicked.connect(lambda checked,value=status:self._toggle_status_filter(value,checked)); self.status_buttons[status]=b; actions.addWidget(b)
        actions.addStretch(); self.category_combo=QComboBox(); self.category_combo.addItem("Toutes les catégories"); self.category_combo.currentTextChanged.connect(self._set_category_filter); actions.addWidget(self.category_combo); self.cleanup_button=QPushButton("🧹 Nettoyage"); self.cleanup_button.clicked.connect(self.cleanup_scanned_services); actions.addWidget(self.cleanup_button); layout.addLayout(actions)
        self.table=ServiceTable(0,6); self.table.setHorizontalHeaderLabels(["Compte","Service","Catégorie","Confiance","Traces","Statut"]); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.verticalHeader().setVisible(False); self.table.verticalHeader().setDefaultSectionSize(54); self.table.setIconSize(QSize(28,28)); self.table.setSelectionMode(QTableWidget.NoSelection); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setContextMenuPolicy(Qt.CustomContextMenu); self.table.customContextMenuRequested.connect(self._show_service_context_menu); self.table.setItemDelegate(ServiceTableDelegate(self.table)); self.table.setStyleSheet("QTableWidget{background:transparent;border:none;gridline-color:transparent;color:#E7EAF0;outline:none;} QTableWidget::item{background:transparent;border:none;color:#E7EAF0;padding:0;} QTableWidget::item:selected,QTableWidget::item:focus{background:transparent;border:none;outline:none;}"); layout.addWidget(self.table)
    def _toggle_status_filter(self,s,c):
        if c:self._status_filters.add(s)
        else:self._status_filters.discard(s)
        self._filter_services(self.search_input.text())
    def _set_category_filter(self,c):self._category_filter=c or "Toutes les catégories"; self._filter_services(self.search_input.text())
    def _filter_services(self,text):
        q=(text or "").strip().casefold(); rows=[]; details=[]
        for row,detail in zip(self._all_rows,self._all_details):
            if q and q not in " ".join(str(v) for v in row).casefold():continue
            if self._status_filters and (detail.get("status") or "À vérifier") not in self._status_filters:continue
            if self._category_filter!="Toutes les catégories" and str(detail.get("category") or "Autre")!=self._category_filter:continue
            rows.append(row);details.append(detail)
        self.row_details=details; self.table.setUpdatesEnabled(False); self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,value in enumerate(row):
                item=QTableWidgetItem(str(value)); item.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
                if c==1:item.setIcon(_service_icon(details[r].get("name"),details[r].get("category")))
                self.table.setItem(r,c,item)
        self.table.setUpdatesEnabled(True); self.table.viewport().update()
    def _refresh_categories(self):
        cats=sorted({str(d.get("category") or "Autre") for d in self._all_details},key=str.casefold); current=self._category_filter; self.category_combo.blockSignals(True); self.category_combo.clear(); self.category_combo.addItem("Toutes les catégories"); self.category_combo.addItems(cats); self.category_combo.setCurrentText(current if current in cats else "Toutes les catégories"); self._category_filter=self.category_combo.currentText(); self.category_combo.blockSignals(False)
    def _resolve_account_service_id(self,details):
        account_service_id=details.get("account_service_id")
        if account_service_id:return account_service_id
        account_id=details.get("account_id"); service_name=details.get("name")
        if not account_id or not service_name:return None
        session=get_session()
        try:
            link=session.scalar(select(AccountService).join(AccountService.service).where(AccountService.account_id==account_id,Service.name==service_name))
            if link:
                details["account_service_id"]=link.id
                return link.id
        finally:session.close()
        return None
    def _show_service_context_menu(self,position):
        index=self.table.indexAt(position)
        if not index.isValid() or not (0<=index.row()<len(self.row_details)):return
        row=index.row(); details=self.row_details[row]; self._resolve_account_service_id(details)
        menu=QMenu(self.table); menu.setStyleSheet("QMenu{background:#171b22;border:1px solid #303846;border-radius:8px;padding:4px;} QMenu::item{color:#E7EAF0;background:transparent;padding:8px 18px;margin:0;border-radius:5px;} QMenu::item:selected{color:#E7EAF0;background:#303846;}")
        details_action=menu.addAction("Plus de détails"); status_menu=menu.addMenu("Statut de migration"); actions={}
        for s in MIGRATION_STATUSES:actions[status_menu.addAction(s)]=s
        destination_action=menu.addAction("Définir l'adresse de destination…"); chosen=menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen==details_action:self._open_details_for_row(row,index.column())
        elif chosen==destination_action:self._set_destination_for_row(row)
        elif chosen in actions:self._set_status_for_row(row,actions[chosen])
    def _update_row_status(self,row,status):
        if not (0<=row<self.table.rowCount()):return
        item=self.table.item(row,5)
        if item:item.setText(status)
        if 0<=row<len(self.row_details):self.row_details[row]["status"]=status
        for detail in self._all_details:
            if 0<=row<len(self.row_details) and detail is self.row_details[row]:detail["status"]=status;break
        for i,r in enumerate(self._all_rows):
            if i<len(self._all_details) and 0<=row<len(self.row_details) and self._all_details[i] is self.row_details[row]:self._all_rows[i]=tuple(list(r[:5])+[status]);break
    def _set_status_for_row(self,row,status):
        if not (0<=row<len(self.row_details)):return
        aid=self._resolve_account_service_id(self.row_details[row])
        if not aid:
            QMessageBox.information(self,"Migration","Ce service n'est pas encore disponible en base de données."); return
        session=get_session()
        try:
            link=session.get(AccountService,aid)
            if not link:return
            link.status=status; link.migrated_at=datetime.now(timezone.utc) if status=="Migré" else None; session.commit()
        except Exception as e:
            session.rollback(); QMessageBox.critical(self,"Erreur","Impossible de modifier le statut.\n\n"+str(e)); return
        finally:session.close()
        self._update_row_status(row,status)
    def _set_destination_for_row(self,row):
        if not (0<=row<len(self.row_details)):return
        d=self.row_details[row]; aid=self._resolve_account_service_id(d)
        if not aid:return
        value,ok=QInputDialog.getText(self,"Adresse de destination","Nouvelle adresse :",text=d.get("destination") or "")
        if not ok:return
        session=get_session()
        try:
            link=session.get(AccountService,aid)
            if not link:return
            link.destination_email=value.strip() or None; session.commit()
        except Exception as e:
            session.rollback(); QMessageBox.critical(self,"Erreur","Impossible d'enregistrer l'adresse.\n\n"+str(e)); return
        finally:session.close()
        d["destination"]=value.strip() or None
    def _open_details_for_row(self,row,_column):
        if not (0<=row<len(self.row_details)):return
        details=dict(self.row_details[row]); self._resolve_account_service_id(details)
        session=get_session()
        try:
            account_service_id=details.get("account_service_id")
            if account_service_id:
                traces=session.scalars(select(ScanTrace).where(ScanTrace.account_service_id==account_service_id)).all()
                signals=set(details.get("signals") or []); reliability=dict(details.get("reliability") or {})
                for trace in traces:
                    if trace.signal_type:signals.add(trace.signal_type)
                    if trace.signal_value:signals.update(part.strip() for part in str(trace.signal_value).split(",") if part.strip())
                details["signals"]=sorted(signals)
                if not reliability:
                    details["reliability"]={"official_domain":"domain" in signals,"known_sender":"sender" in signals,"authentication_available":False,"spf":None,"dkim":None,"dmarc":None}
        finally:session.close()
        dialog=ServiceDetailsDialog(details,self)
        if dialog.exec()==QDialog.Accepted:self.refresh()
    def set_active_account(self,account_id):
        if self.live_scan:return
        self.active_account_id=account_id; self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear(); self.refresh()
    @staticmethod
    def _get_account_email(account_id):
        session=get_session()
        try:account=session.get(GoogleAccount,account_id); return account.email if account else ""
        finally:session.close()
    def start_live_scan(self,account_id):
        if not self.live_scan:self.live_scan=True; self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear()
        self.live_account_ids.add(account_id); email=self._get_account_email(account_id)
        if email:self.live_account_emails[account_id]=email
        self._schedule_live_render()
    def update_live_detection(self,account_id,data):
        if not self.live_scan or account_id not in self.live_account_ids:return
        key=(account_id,data.get("service_id") or data.get("name","").strip().lower()); email=data.get("account_email") or self.live_account_emails.get(account_id,"")
        self.live_rows[key]={"account_id":account_id,"account_service_id":data.get("account_service_id"),"account_email":email,"name":data.get("name","Service inconnu"),"category":data.get("category","Autre"),"score":float(data.get("score",0)),"count":int(data.get("count",0)),"status":data.get("status","À vérifier"),"priority":data.get("priority","Normale"),"destination":data.get("destination_email"),"notes":data.get("notes"),"first_detected_at":data.get("first_detected_at"),"last_detected_at":data.get("last_detected_at"),"signals":data.get("signals",[]),"reliability":data.get("reliability",{})}
        self._schedule_live_render()
    def _schedule_live_render(self):
        if self._live_render_pending:return
        self._live_render_pending=True; QTimer.singleShot(120,self._render_live_rows_deferred)
    def _render_live_rows_deferred(self):
        self._live_render_pending=False
        if self.live_scan:self._render_live_rows()
    def finish_live_scan(self,mode):
        if not self.live_scan:return
        if mode==-1:self.keep_live_results_after_cancel();return
        self.live_scan=False; self._render_live_rows(); self.refresh(); self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear()
    def keep_live_results_after_cancel(self):
        self.live_scan=False; self._render_live_rows(); self.live_account_ids.clear(); self.live_account_emails.clear()
    def _render_live_rows(self):
        rows=[]; details=[]
        for item in sorted(self.live_rows.values(),key=lambda x:(-x["score"],x["name"].lower(),x["account_email"].lower())):
            rows.append((item.get("account_email",""),item["name"],item["category"],f'{item["score"]:.0f} %',str(item["count"]),item["status"])); details.append(item)
        self._set_rows(rows,details)
    def _set_rows(self,rows,details=None):
        self._all_rows=list(rows); self._all_details=list(details or []); self._refresh_categories(); self._filter_services(self.search_input.text())
    def refresh(self):
        session=get_session(); rows=[]; details=[]
        try:
            for account in get_accounts(session):
                if self.active_account_id is not None and account.id!=self.active_account_id:continue
                for link in get_account_services(session,account.id):
                    service=link.service
                    details.append({"account_id":account.id,"account_service_id":link.id,"account_email":account.email,"name":service.name,"category":service.category,"subcategory":service.subcategory,"score":link.confidence_score,"count":link.trace_count,"status":link.status or "À vérifier","priority":link.priority,"destination":link.destination_email,"notes":link.notes,"first_detected_at":link.first_detected_at,"last_detected_at":link.last_detected_at,"migrated_at":link.migrated_at,"signals":[],"reliability":{}})
                    rows.append((account.email,service.name,service.category,f"{link.confidence_score:.0f} %",str(link.trace_count),link.status or "À vérifier"))
        finally:session.close()
        if not self.live_scan:self._set_rows(rows,details)
    def cleanup_scanned_services(self):
        session=get_session()
        try:session.execute(delete(ScanTrace)); session.execute(delete(AccountService)); session.commit()
        finally:session.close()
        self.live_rows.clear(); self.live_account_ids.clear(); self.live_account_emails.clear(); self.live_scan=False; self.refresh()
