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
            if index >= 0:
                self.scan_combo.setCurrentIndex(index)
        self._format_changed(self.format_combo.currentText())

    def _browse(self):
        suffix = self.format_combo.currentText().lower()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter l'analyse",
            f"mail-migration.{suffix}",
            f"{suffix.upper()} (*.{suffix})"
        )
        if filename:
            self.path_input.setText(filename)

    def _format_changed(self, fmt):
        if not self.path_input.text().strip():
            self.path_input.setPlaceholderText(f"Choisissez un fichier .{str(fmt).lower()}…")

    def _load_data(self, history_id):
        session = get_session()
        try:
            history = session.get(ScanHistory, history_id)
            if not history or history.status != "completed":
                return None, []
            account = session.get(GoogleAccount, history.account_id)
            services = session.scalars(
                select(AccountService)
                .where(AccountService.account_id == history.account_id)
                .order_by(AccountService.confidence_score.desc())
            ).all()
            data = []
            for link in services:
                service = session.get(Service, link.service_id)
                data.append({
                    "name": service.name if service else "Service inconnu",
                    "category": service.category if service else "Autre",
                    "score": link.confidence_score or 0,
                    "traces": link.trace_count or 0,
                    "status": link.status or "À vérifier",
                    "priority": link.priority or "Normale",
                    "destination": link.destination_email or "",
                    "notes": link.notes or "",
                })
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
            self._browse()
            path = self.path_input.text().strip()
        if not path:
            return

        info, services = self._load_data(history_id)
        if not info:
            QMessageBox.warning(self, "Exportation", "Cette analyse n'est plus disponible.")
            return

        try:
            target = Path(path)
            fmt = self.format_combo.currentText().upper()
            expected_suffix = f".{fmt.lower()}"
            if target.suffix.lower() != expected_suffix:
                target = target.with_suffix(expected_suffix)
                self.path_input.setText(str(target))
            target.parent.mkdir(parents=True, exist_ok=True)

            if fmt == "TXT":
                self._write_txt(target, info, services)
            elif fmt == "SQL":
                self._write_sql(target, info, services)
            elif fmt == "PDF":
                self._write_pdf(target, info, services)
            else:
                raise ValueError(f"Format d'exportation non pris en charge : {fmt}")

            QMessageBox.information(self, "Exportation", f"Export {fmt} terminé.\n\n{target}")
        except Exception as exc:
            QMessageBox.critical(self, "Exportation", f"Impossible d'exporter l'analyse.\n\n{exc}")

    @staticmethod
    def _write_txt(path, info, services):
        history, account = info["history"], info["account"]
        lines = [
            "MAIL MIGRATION — RAPPORT D'ANALYSE",
            "=" * 72,
            f"Compte              : {account.email}",
            f"Date du scan        : {history.finished_at:%d.%m.%Y %H:%M}" if history.finished_at else "Date du scan        : —",
            f"Messages analysés   : {history.messages_scanned}",
            f"Services détectés   : {history.services_detected}",
            "",
            "SERVICES DÉTECTÉS",
            "-" * 72,
        ]
        if not services:
            lines.append("Aucun service détecté.")
        else:
            for number, service in enumerate(services, 1):
                lines.extend([
                    f"{number}. {service['name']}",
                    f"   Catégorie       : {service['category']}",
                    f"   Confiance       : {service['score']:.0f} %",
                    f"   Traces          : {service['traces']}",
                    f"   Statut          : {service['status']}",
                    f"   Priorité        : {service['priority']}",
                    f"   Adresse cible   : {service['destination'] or 'Non définie'}",
                    f"   Notes           : {service['notes'] or 'Aucune'}",
                    "",
                ])
        lines.extend(["=" * 72, "Fin du rapport."])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    @staticmethod
    def _write_sql(path, info, services):
        history, account = info["history"], info["account"]

        def sql(value):
            if value is None:
                return "NULL"
            return "'" + str(value).replace("'", "''") + "'"

        lines = [
            "-- ============================================================",
            "-- MAIL MIGRATION — EXPORT SQL",
            "-- ============================================================",
            f"-- Compte : {account.email}",
            f"-- Scan : {history.finished_at:%d.%m.%Y %H:%M}" if history.finished_at else "-- Scan : —",
            f"-- Messages analysés : {history.messages_scanned}",
            f"-- Services détectés : {history.services_detected}",
            "-- Ce fichier est autonome et peut être importé dans SQLite.",
            "",
            "PRAGMA foreign_keys = OFF;",
            "BEGIN TRANSACTION;",
            "",
            "DROP TABLE IF EXISTS scan_export;",
            "CREATE TABLE scan_export (",
            "    id INTEGER PRIMARY KEY AUTOINCREMENT,",
            "    account_email TEXT NOT NULL,",
            "    service_name TEXT NOT NULL,",
            "    category TEXT,",
            "    confidence REAL,",
            "    traces INTEGER,",
            "    status TEXT,",
            "    priority TEXT,",
            "    destination_email TEXT,",
            "    notes TEXT",
            ");",
            "",
        ]

        for service in services:
            values = [
                sql(account.email),
                sql(service["name"]),
                sql(service["category"]),
                str(float(service["score"])),
                str(int(service["traces"])),
                sql(service["status"]),
                sql(service["priority"]),
                sql(service["destination"]),
                sql(service["notes"]),
            ]
            lines.append("INSERT INTO scan_export (account_email, service_name, category, confidence, traces, status, priority, destination_email, notes) VALUES (" + ", ".join(values) + ");")

        lines.extend([
            "",
            "CREATE INDEX idx_scan_export_service ON scan_export(service_name);",
            "CREATE INDEX idx_scan_export_status ON scan_export(status);",
            "",
            "COMMIT;",
            "PRAGMA foreign_keys = ON;",
            "",
            "-- Exemple :",
            "-- SELECT * FROM scan_export ORDER BY confidence DESC;",
        ])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_pdf(path, info, services):
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT

        history, account = info["history"], info["account"]
        styles = getSampleStyleSheet()
        body = ParagraphStyle("ExportBody", parent=styles["Normal"], fontSize=9, leading=12)
        small = ParagraphStyle("ExportSmall", parent=body, fontSize=8, leading=10)
        title = ParagraphStyle("ExportTitle", parent=styles["Title"], fontSize=20, leading=24, spaceAfter=8)
        heading = ParagraphStyle("ExportHeading", parent=styles["Heading2"], fontSize=12, leading=15, spaceBefore=8, spaceAfter=8)

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
            title="Mail Migration — Rapport d'analyse",
            author="Mail Migration",
        )

        def p(value, style=small):
            return Paragraph(html.escape(str(value or "—")), style)

        story = [
            Paragraph("Mail Migration", title),
            Paragraph("Rapport d'analyse sauvegardée", heading),
            p(f"<b>Compte :</b> {account.email}", body),
            p(f"<b>Date du scan :</b> {history.finished_at:%d.%m.%Y %H:%M}" if history.finished_at else "<b>Date du scan :</b> —", body),
            p(f"<b>Messages analysés :</b> {history.messages_scanned}", body),
            p(f"<b>Services détectés :</b> {history.services_detected}", body),
            Spacer(1, 12),
            Paragraph("Services détectés", heading),
        ]

        if not services:
            story.append(p("Aucun service détecté.", body))
        else:
            data = [[p("Service", body), p("Catégorie", body), p("Confiance", body), p("Traces", body), p("Statut", body)]]
            for service in services:
                data.append([
                    p(service["name"]),
                    p(service["category"]),
                    p(f"{service['score']:.0f} %"),
                    p(service["traces"]),
                    p(service["status"]),
                ])

            table = Table(data, colWidths=[125, 90, 58, 42, 100], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#303846")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B5BBC4")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(table)

            story.append(Spacer(1, 14))
            story.append(Paragraph("Informations de migration", heading))
            for service in services:
                block = [
                    p(f"<b>{service['name']}</b>", body),
                    p(f"Statut : {service['status']}  •  Priorité : {service['priority']}", small),
                    p(f"Adresse de destination : {service['destination'] or 'Non définie'}", small),
                    p(f"Notes : {service['notes'] or 'Aucune'}", small),
                    Spacer(1, 5),
                ]
                story.append(KeepTogether(block))

        doc.build(story)
