import json
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QFrame

SETTINGS_PATH=Path(__file__).resolve().parents[2]/"data"/"settings.json"

class SettingsPage(QWidget):
    changed=Signal(dict)
    def __init__(self):
        super().__init__()
        self.values={"palette":"Obsidienne","animations":True,"toast_notifications":True,"background_scanner":False}
        self._load()
        root=QVBoxLayout(self); root.setContentsMargins(28,28,28,28); root.setSpacing(18)
        title=QLabel("Paramètres"); title.setObjectName("title"); root.addWidget(title)
        subtitle=QLabel("Personnalisez le comportement et l'apparence de Mail Migration."); subtitle.setObjectName("muted"); root.addWidget(subtitle)
        card=QFrame(); card.setObjectName("settingsCard"); card.setStyleSheet("QFrame#settingsCard{background:#171b22;border:1px solid #303846;border-radius:14px;} QLabel.settingTitle{font-size:15px;font-weight:600;} QLabel.settingDescription{color:#9AA2AF;font-size:12px;}")
        form=QVBoxLayout(card); form.setContentsMargins(20,20,20,20); form.setSpacing(18)
        self.palette=self._combo("Palette de couleurs","Choisissez la palette utilisée par l'application.",["Obsidienne","Ardoise","Minuit","Clair"]); self.palette.setCurrentText(self.values["palette"]); self.palette.currentTextChanged.connect(lambda v:self._set("palette",v)); form.addLayout(self._row(self.palette))
        self.animations=self._toggle("Animations","Activer les animations de l'interface.",self.values["animations"]); self.animations.clicked.connect(lambda:self._set("animations",self.animations.isChecked())); form.addLayout(self._row(self.animations))
        self.toasts=self._toggle("Notifications Toast","Afficher les notifications discrètes dans l'interface.",self.values["toast_notifications"]); self.toasts.clicked.connect(lambda:self._set("toast_notifications",self.toasts.isChecked())); form.addLayout(self._row(self.toasts))
        self.background=self._toggle("Scanner en arrière-plan","Autoriser les scans à continuer pendant la navigation.",self.values["background_scanner"]); self.background.clicked.connect(lambda:self._set("background_scanner",self.background.isChecked())); form.addLayout(self._row(self.background))
        root.addWidget(card); root.addStretch()
    def _row(self,control):
        box=QHBoxLayout(); box.setSpacing(20); box.addWidget(control[0],1) if isinstance(control,tuple) else None
        if isinstance(control,tuple): box.addWidget(control[1]); return box
        return box
    def _combo(self,title,description,items):
        label=QLabel(f"{title}\n{description}"); label.setProperty("class","settingTitle"); combo=QComboBox(); combo.addItems(items); combo.setMinimumWidth(180); return (label,combo)
    def _toggle(self,title,description,checked):
        label=QLabel(f"{title}\n{description}"); label.setProperty("class","settingTitle"); button=QPushButton("Activé" if checked else "Désactivé"); button.setCheckable(True); button.setChecked(checked); button.setMinimumWidth(120); button.toggled.connect(lambda state,b=button:b.setText("Activé" if state else "Désactivé")); return (label,button)
    def _set(self,key,value):
        self.values[key]=value; self._save(); self.changed.emit(dict(self.values))
    def _load(self):
        try:
            data=json.loads(SETTINGS_PATH.read_text(encoding="utf-8")); self.values.update({k:v for k,v in data.items() if k in self.values})
        except Exception: pass
    def _save(self):
        try:
            SETTINGS_PATH.parent.mkdir(parents=True,exist_ok=True); SETTINGS_PATH.write_text(json.dumps(self.values,ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception: pass
