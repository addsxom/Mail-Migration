# Mail Migration

Application desktop Python/PySide6 permettant d'inventorier les services associés à des comptes Gmail.

## Principes

- Lecture seule côté Gmail.
- Aucun email envoyé, modifié ou supprimé.
- Les tokens sont séparés par compte.
- Les métadonnées utiles sont stockées, pas le corps complet des emails.
- Les détections sont explicables et accompagnées d'un score de confiance.

## Installation

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Google OAuth

1. Créer un projet dans Google Cloud Console.
2. Activer Gmail API.
3. Configurer l'écran de consentement OAuth.
4. Créer un client OAuth Desktop.
5. Télécharger le fichier et le placer à la racine sous `credentials.json`.
6. Lancer l'application puis utiliser "Ajouter un compte".

Les fichiers `credentials.json`, `tokens/` et `data/*.db` ne doivent jamais être publiés.

## Architecture

- `app/core` : configuration et logs
- `app/database` : SQLite/SQLAlchemy
- `app/google` : OAuth et Gmail API
- `app/scanner` : analyse, détection et scoring
- `app/services` : catalogue intégré
- `app/ui` : interface PySide6
- `tests` : tests unitaires

## Limites de cette V1

Le scanner utilise les métadonnées Gmail et un catalogue local. Le moteur est volontairement modulaire afin de pouvoir ajouter des règles sans modifier l'interface.
