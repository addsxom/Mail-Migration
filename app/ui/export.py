from datetime import datetime
from pathlib import Path
import html

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog, QMessageBox, QFrame
from sqlalchemy import select

from app.database.database import get_session
from app.database.models import GoogleAccount, ScanHistory, AccountService, Service


class ExportPage(QWidget):
    """Export a completed saved scan to TXT, SQL or PDF."""
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
        form.setContentsMargins(18, 18, 18, 18)
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
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(browse)
        form.addLayout(path_row)

        form.addWidget(QLabel("Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["TXT", "SQL", "PDF"])
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
            rows = session.execute(
                select(ScanHistory, GoogleAccount)
                .join(GoogleAccount, GoogleAccount.id == ScanHistory.account_id)
                .where(ScanHistory.status == "completed")
                .order_by(ScanHistory.finished_at.desc())
            ).all()
            self._histories = [history for history, _ in rows]
            for history, account in rows:
                date = history.finished_at.strftime("%d.%m.%Y %H:%M") if history.finished_at else "Date inconnue"
                self.scan_combo.addItem(f"{account.email}  —  {date}  —  {history.services_detected} service(s)", history.id)
        finally:
            session.close()
        if current is not None:
            index = self.scan_combo.findData(current)
            if index >= 0: self.scan_combo.setCurrentIndex(index)
        self._format_changed(self.format_combo.currentText())

    def _browse(self):
        suffix = self.format_combo.currentText().lower()
        filename, _ = QFileDialog.getSaveFileName(self, "Exporter l'analyse", f"mail-migration.{suffix}", f"{suffix.upper()} (*.{suffix})")
        if filename: self.path_input.setText(filename)

    def _format_changed(self, fmt):
        if not self.path_input.text().strip():
            self.path_input.setPlaceholderText(f"Choisissez un fichier .{str(fmt).lower()}…")

    def _load_data(self, history_id):
        session = get_session()
        try:
            history = session.get(ScanHistory, history_id)
            if not history or history.status != "completed": return None, []
            account = session.get(GoogleAccount, history.account_id)
            services = session.scalars(
                select(AccountService).where(AccountService.account_id == history.account_id).order_by(AccountService.confidence_score.desc())
            ).all()
            data = []
            for link in services:
                service = session.get(Service, link.service_id)
                data.append({"name": service.name if service else "Service inconnu", "category": service.category if service else "Autre", "score": link.confidence_score, "traces": link.trace_count, "status": link.status or "À vérifier", "priority": link.priority or "Normale", "destination": link.destination_email or "", "notes": link.notes or ""})
            return {"history": history, "account": account}, data
        finally:
            session.close()

    def export_selected(self):
        history_id = self.scan_combo.currentData()
        path = self.path_input.text().strip()
        if not history_id:
            QMessageBox.information(self, "Exportation", "Aucune analyse sauvegardée n'est disponible.")
            return
        if not path:
            self._browse(); path = self.path_input.text().strip()
        if not path: return
        info, services = self._load_data(history_id)
        if not info:
            QMessageBox.warning(self, "Exportation", "Cette analyse n'est plus disponible.")
            return
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            fmt = self.format_combo.currentText()
            if fmt == "TXT": self._write_txt(target, info, services)
            elif fmt == "SQL": self._write_sql(target, info, services)
            else: self._write_pdf(target, info, services)
            QMessageBox.information(self, "Exportation", f"Export terminé.\n\n{target}")
        except Exception as exc:
            QMessageBox.critical(self, "Exportation", f"Impossible d'exporter l'analyse.\n\n{exc}")

    @staticmethod
    def _write_txt(path, info, services):
        history, account = info["history"], info["account"]
        lines = ["MAIL MIGRATION", "=" * 60, f"Compte : {account.email}", f"Scan : {history.finished_at:%d.%m.%Y %H:%M}" if history.finished_at else "Scan : —", f"Messages analysés : {history.messages_scanned}", f"Services détectés : {history.services_detected}", "", "SERVICES", "-" * 60]
        for s in services: lines.append(f"{s['name']} | {s['category']} | {s['score']:.0f}% | {s['traces']} traces | {s['status']}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_sql(path, info, services):
        history, account = info["history"], info["account"]
        q = lambda value: "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"
        lines = ["-- Mail Migration export", "BEGIN TRANSACTION;", "CREATE TABLE IF NOT EXISTS scan_export (account_email TEXT, service_name TEXT, category TEXT, confidence REAL, traces INTEGER, status TEXT, priority TEXT, destination_email TEXT, notes TEXT);"]
        for s in services:
            lines.append("INSERT INTO scan_export VALUES (" + ", ".join([q(account.email), q(s["name"]), q(s["category"]), str(float(s["score"])), str(int(s["traces"])), q(s["status"]), q(s["priority"]), q(s["destination"]), q(s["notes"])]) + ");")
        lines.append("COMMIT;")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_pdf(path, info, services):
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        history, account = info["history"], info["account"]
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        story = [Paragraph("Mail Migration — Export", styles["Title"]), Spacer(1, 10), Paragraph(f"Compte : {html.escape(account.email)}", styles["Normal"]), Paragraph(f"Messages analysés : {history.messages_scanned}", styles["Normal"]), Paragraph(f"Services détectés : {history.services_detected}", styles["Normal"]), Spacer(1, 16)]
        data = [["Service", "Catégorie", "Confiance", "Traces", "Statut"]] + [[s["name"], s["category"], f"{s['score']:.0f}%", str(s["traces"]), s["status"]] for s in services]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#303846")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.25, colors.grey), ("FONTSIZE", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
        story.append(table)
        doc.build(story)
