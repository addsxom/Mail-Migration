from datetime import datetime
from pathlib import Path
import html

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog, QMessageBox, QFrame
from sqlalchemy import select

from app.database.database import get_session
from app.database.models import GoogleAccount, ScanHistory, AccountService, Service


class ExportPage(QWidget):
    def __init__(self):
        super().__init__()
        self._histories = []
        layout = QVBoxLayout(self)
        title = QLabel("Exportation")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Choisissez une analyse sauvegardée et le format à exporter.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        card = QFrame()
        card.setStyleSheet("QFrame{background:#171b22;border:1px solid #303846;border-radius:14px;} QLabel{background:transparent;border:none;} QLineEdit,QComboBox{border:1px solid #303846;border-radius:8px;background:#11151b;color:#E7EAF0;padding:9px 10px;} QPushButton{padding:9px 14px;border-radius:8px;}")
        form = QVBoxLayout(card)
        form.setContentsMargins(18,18,18,18)
        form.setSpacing(10)
        form.addWidget(QLabel("Analyse à exporter"))
        self.scan_combo = QComboBox()
        form.addWidget(self.scan_combo)
        form.addWidget(QLabel("Chemin d'exportation"))
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Choisissez un dossier ou un fichier…")
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_input,1)
        path_row.addWidget(browse)
        form.addLayout(path_row)
        form.addWidget(QLabel("Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["TXT","SQL","PDF"])
        self.format_combo.currentTextChanged.connect(self._format_changed)
        form.addWidget(self.format_combo)
        self.export_button = QPushButton("Exporter")
        self.export_button.clicked.connect(self.export_selected)
        self.export_button.setMinimumHeight(42)
        form.addWidget(self.export_button)
        layout.addWidget(card)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        current = self.scan_combo.currentData()
        self.scan_combo.clear()
        session = get_session()
        try:
            rows = session.execute(select(ScanHistory,GoogleAccount).join(GoogleAccount,GoogleAccount.id == ScanHistory.account_id).where(ScanHistory.status == "completed").order_by(ScanHistory.finished_at.desc())).all()
            self._histories = [history for history,_ in rows]
            for history,account in rows:
                date = history.finished_at.strftime("%d.%m.%Y %H:%M") if history.finished_at else "Date inconnue"
                self.scan_combo.addItem(f"{account.email}  —  {date}  —  {history.services_detected} service(s)",history.id)
        finally:
            session.close()
        if current is not None:
            index = self.scan_combo.findData(current)
            if index >= 0:
                self.scan_combo.setCurrentIndex(index)
        self._format_changed(self.format_combo.currentText())

    def _browse(self):
        suffix = self.format_combo.currentText().lower()
        filename,_ = QFileDialog.getSaveFileName(self,"Exporter l'analyse",f"mail-migration.{suffix}",f"{suffix.upper()} (*.{suffix})")
        if filename:
            self.path_input.setText(filename)

    def _format_changed(self,fmt):
        if not self.path_input.text().strip():
            self.path_input.setPlaceholderText(f"Choisissez un fichier .{str(fmt).lower()}…")

    def _load_data(self,history_id):
        session = get_session()
        try:
            history = session.get(ScanHistory,history_id)
            if not history or history.status != "completed":
                return None,[]
            account = session.get(GoogleAccount,history.account_id)
            services = session.scalars(select(AccountService).where(AccountService.account_id == history.account_id).order_by(AccountService.confidence_score.desc())).all()
            data = []
            for link in services:
                service = session.get(Service,link.service_id)
                data.append({"name":service.name if service else "Service inconnu","category":service.category if service else "Autre","score":link.confidence_score or 0,"traces":link.trace_count or 0,"status":link.status or "À vérifier","priority":link.priority or "Normale","destination":link.destination_email or "","notes":link.notes or ""})
            return {"history":history,"account":account},data
        finally:
            session.close()

    def export_selected(self):
        history_id = self.scan_combo.currentData()
        path = self.path_input.text().strip()
        if not history_id:
            QMessageBox.information(self,"Exportation","Aucune analyse sauvegardée n'est disponible.")
            return
        if not path:
            self._browse()
            path = self.path_input.text().strip()
        if not path:
            return
        info,services = self._load_data(history_id)
        if not info:
            QMessageBox.warning(self,"Exportation","Cette analyse n'est plus disponible.")
            return
        try:
            target = Path(path)
            fmt = self.format_combo.currentText().upper()
            expected_suffix = f".{fmt.lower()}"
            if target.suffix.lower() != expected_suffix:
                target = target.with_suffix(expected_suffix)
                self.path_input.setText(str(target))
            target.parent.mkdir(parents=True,exist_ok=True)
            if fmt == "TXT":
                self._write_txt(target,info,services)
            elif fmt == "SQL":
                self._write_sql(target,info,services)
            elif fmt == "PDF":
                self._write_pdf(target,info,services)
            else:
                raise ValueError(f"Format d'exportation non pris en charge : {fmt}")
            QMessageBox.information(self,"Exportation",f"Export {fmt} terminé.\n\n{target}")
        except Exception as exc:
            QMessageBox.critical(self,"Exportation",f"Impossible d'exporter l'analyse.\n\n{exc}")

    @staticmethod
    def _write_txt(path,info,services):
        history,account = info["history"],info["account"]
        lines=["MAIL MIGRATION — RAPPORT D'ANALYSE","="*72,f"Compte              : {account.email}",f"Date du scan        : {history.finished_at:%d.%m.%Y %H:%M}" if history.finished_at else "Date du scan        : —",f"Messages analysés   : {history.messages_scanned}",f"Services détectés   : {history.services_detected}","","SERVICES DÉTECTÉS","-"*72]
        if not services:
            lines.append("Aucun service détecté.")
        else:
            for number,service in enumerate(services,1):
                lines.extend([f"{number}. {service['name']}",f"   Catégorie       : {service['category']}",f"   Confiance       : {service['score']:.0f} %",f"   Traces          : {service['traces']}",f"   Statut          : {service['status']}",f"   Priorité        : {service['priority']}",f"   Adresse cible   : {service['destination'] or 'Non définie'}",f"   Notes           : {service['notes'] or 'Aucune'}",""])
        lines.extend(["="*72,"Fin du rapport."])
        path.write_text("\n".join(lines)+"\n",encoding="utf-8-sig")

    @staticmethod
    def _write_sql(path,info,services):
        history,account = info["history"],info["account"]
        def sql(value):
            if value is None:
                return "NULL"
            return "'"+str(value).replace("'","''")+"'"
        lines=["-- ============================================================","-- MAIL MIGRATION — RAPPORT SQL","-- Format : SQLite","-- ============================================================",f"-- Compte : {account.email}",f"-- Date du scan : {history.finished_at:%d.%m.%Y %H:%M}" if history.finished_at else "-- Date du scan : —",f"-- Messages analysés : {history.messages_scanned}",f"-- Services détectés : {history.services_detected}","-- Le fichier contient une copie autonome et lisible du rapport.","","PRAGMA foreign_keys = OFF;","BEGIN TRANSACTION;","","DROP TABLE IF EXISTS services;","DROP TABLE IF EXISTS scan_info;","","CREATE TABLE scan_info (","    id INTEGER PRIMARY KEY,","    account_email TEXT NOT NULL,","    scanned_at TEXT,","    messages_scanned INTEGER NOT NULL,","    services_detected INTEGER NOT NULL"," );".replace(" ",""),"","CREATE TABLE services (","    id INTEGER PRIMARY KEY AUTOINCREMENT,","    scan_id INTEGER NOT NULL,","    service_name TEXT NOT NULL,","    category TEXT,","    confidence REAL,","    traces INTEGER,","    migration_status TEXT,","    priority TEXT,","    destination_email TEXT,","    notes TEXT,","    FOREIGN KEY (scan_id) REFERENCES scan_info(id)",");","","INSERT INTO scan_info (id, account_email, scanned_at, messages_scanned, services_detected)","VALUES (","    1,",f"    {sql(account.email)},",f"    {sql(history.finished_at.isoformat() if history.finished_at else None)},",f"    {int(history.messages_scanned or 0)},",f"    {int(history.services_detected or 0)}"," );".replace(" ",""),""]
        for service in services:
            lines.extend(["INSERT INTO services (","    scan_id,","    service_name,","    category,","    confidence,","    traces,","    migration_status,","    priority,","    destination_email,","    notes"," ) VALUES (".replace(" ",""),"    1,",f"    {sql(service['name'])},",f"    {sql(service['category'])},",f"    {float(service['score'])},",f"    {int(service['traces'])},",f"    {sql(service['status'])},",f"    {sql(service['priority'])},",f"    {sql(service['destination'])},",f"    {sql(service['notes'])}",");",""])
        lines.extend(["CREATE INDEX idx_services_scan_id ON services(scan_id);","CREATE INDEX idx_services_name ON services(service_name);","CREATE INDEX idx_services_status ON services(migration_status);","","COMMIT;","PRAGMA foreign_keys = ON;","","-- Exemples de lecture :","-- SELECT * FROM services ORDER BY confidence DESC;","-- SELECT * FROM services WHERE migration_status = 'À migrer';","-- SELECT category, COUNT(*) FROM services GROUP BY category;"])
        path.write_text("\n".join(lines)+"\n",encoding="utf-8")

    @staticmethod
    def _write_pdf(path,info,services):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        history,account = info["history"],info["account"]
        styles=getSampleStyleSheet()
        body=ParagraphStyle("ExportBody",parent=styles["Normal"],fontSize=9,leading=12,spaceAfter=2)
        small=ParagraphStyle("ExportSmall",parent=body,fontSize=8,leading=10)
        title=ParagraphStyle("ExportTitle",parent=styles["Title"],fontSize=22,leading=26,spaceAfter=4,alignment=TA_LEFT)
        subtitle=ParagraphStyle("ExportSubtitle",parent=body,fontSize=10,leading=13,textColor=colors.HexColor("#667085"),spaceAfter=12)
        heading=ParagraphStyle("ExportHeading",parent=styles["Heading2"],fontSize=13,leading=16,spaceBefore=12,spaceAfter=8)
        service_title=ParagraphStyle("ExportServiceTitle",parent=body,fontSize=10,leading=13)
        meta=ParagraphStyle("ExportMeta",parent=small,textColor=colors.HexColor("#667085"))
        doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=58,bottomMargin=48,title="Mail Migration — Rapport d'analyse",author="Mail Migration")
        def p(value,style=small):
            return Paragraph(html.escape(str(value if value not in (None,"") else "—")).replace("\n","<br/>"),style)
        def draw_header_footer(canvas,document):
            canvas.saveState()
            width,height=A4
            canvas.setStrokeColor(colors.HexColor("#D9DEE7")); canvas.setLineWidth(0.6)
            canvas.line(document.leftMargin,height-34,width-document.rightMargin,height-34)
            canvas.setFont("Helvetica-Bold",8); canvas.setFillColor(colors.HexColor("#344054")); canvas.drawString(document.leftMargin,height-25,"MAIL MIGRATION")
            canvas.setFont("Helvetica",8); canvas.setFillColor(colors.HexColor("#667085")); canvas.drawRightString(width-document.rightMargin,height-25,"Rapport d'analyse")
            canvas.line(document.leftMargin,30,width-document.rightMargin,30)
            canvas.drawString(document.leftMargin,19,str(account.email)); canvas.drawRightString(width-document.rightMargin,19,f"Page {document.page}")
            canvas.restoreState()
        summary_data=[[p("Compte",meta),p("Date du scan",meta),p("Messages analysés",meta),p("Services détectés",meta)],[p(account.email,body),p(history.finished_at.strftime("%d.%m.%Y %H:%M") if history.finished_at else "—",body),p(history.messages_scanned or 0,body),p(history.services_detected or 0,body)]]
        summary=Table(summary_data,colWidths=[125,105,105,105],hAlign="LEFT")
        summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F7F8FA")),("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#D9DEE7")),("INNERGRID",(0,0),(-1,-1),0.35,colors.HexColor("#E4E7EC")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        story=[Paragraph("Mail Migration",title),Paragraph("Rapport d'analyse sauvegardée",subtitle),summary,Spacer(1,10),Paragraph("Services détectés",heading)]
        if not services:
            story.append(p("Aucun service détecté.",body))
        else:
            service_rows=[[p("Service",meta),p("Catégorie",meta),p("Confiance",meta),p("Traces",meta),p("Statut",meta)]]
            for service in services:
                service_rows.append([Paragraph(html.escape(str(service["name"])),service_title),p(service["category"]),p(f"{service['score']:.0f} %"),p(service["traces"]),p(service["status"])])
            service_table=Table(service_rows,colWidths=[128,92,58,45,117],repeatRows=1,hAlign="LEFT")
            service_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EEF1F5")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#344054")),("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#D9DEE7")),("INNERGRID",(0,0),(-1,-1),0.35,colors.HexColor("#E4E7EC")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#FAFBFC")]),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
            story.append(service_table)
            story.extend([Spacer(1,14),Paragraph("Informations de migration",heading)])
            migration_rows=[[p("Service",meta),p("Statut",meta),p("Priorité",meta),p("Adresse de destination",meta),p("Notes",meta)]]
            for service in services:
                migration_rows.append([Paragraph(html.escape(str(service["name"])),service_title),p(service["status"]),p(service["priority"]),p(service["destination"] or "Non définie"),p(service["notes"] or "Aucune")])
            migration_table=Table(migration_rows,colWidths=[105,70,58,125,82],repeatRows=1,hAlign="LEFT")
            migration_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EEF1F5")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#344054")),("BOX",(0,0),(-1,-1),0.7,colors.HexColor("#D9DEE7")),("INNERGRID",(0,0),(-1,-1),0.35,colors.HexColor("#E4E7EC")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#FAFBFC")]),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
            story.append(migration_table)
        doc.build(story,onFirstPage=draw_header_footer,onLaterPages=draw_header_footer)
