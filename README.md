# Mail Migration

Application desktop Python/PySide6 permettant d'inventorier les services associés à des comptes Gmail.

## Principes

- Lecture seule côté Gmail.
- Aucun email envoyé, modifié ou supprimé.
- Les tokens sont séparés par compte.
- Les métadonnées utiles sont stockées, pas le corps complet des emails.
- Les détections sont explicables et accompagnées d'un score de confiance.
- La migration reste volontairement manuelle.

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

## Détection actuelle

Le moteur combine plusieurs indices :

- domaine de l'expéditeur ;
- adresse de l'expéditeur ;
- nom affiché de l'expéditeur ;
- sujet ;
- mots-clés du catalogue ;
- domaines secondaires et sous-domaines ;
- `Reply-To` en solution de repli lorsque `From` est absent ;
- informations SPF/DKIM/DMARC lorsqu'elles sont présentes dans `Authentication-Results`.

### Services absents du catalogue

Le scanner peut aussi repérer des **candidats inconnus**. Lorsqu'un domaine non catalogué apparaît plusieurs fois, il peut être ajouté à l'inventaire sous la forme `Inconnu — domaine.tld`, avec une confiance volontairement basse et le statut `À vérifier`.

Un seul email provenant d'un domaine inconnu n'est pas enregistré comme service afin d'éviter que les newsletters et expéditeurs ponctuels remplissent l'inventaire.

Le système ignore également plusieurs fournisseurs de messagerie personnels courants (`gmail.com`, `outlook.com`, `icloud.com`, etc.) pour éviter les faux candidats.

## Personnaliser le catalogue

Les définitions sont dans `app/services/builtin_catalog.py`. Une définition peut contenir notamment :

```python
{
    "name": "Exemple",
    "category": "Jeux",
    "domains": ["example.com"],
    "senders": ["noreply@example.com"],
    "keywords": ["Exemple", "compte"],
    "aliases": ["Example Service"],
}
```

Les `aliases` sont désormais pris en charge par l'index de détection, même si le catalogue actuel n'en utilise pas encore partout.

## Phase actuelle

La phase Catalogue / Détection est en cours de finalisation. Le moteur sait maintenant identifier les services connus avec plusieurs signaux et faire remonter prudemment des domaines inconnus récurrents. L'objectif est de terminer les réglages de précision avant de passer à une nouvelle grosse fonctionnalité.

## Limites

Le scanner utilise les métadonnées Gmail et ne prétend pas déterminer avec certitude qu'un compte externe existe. Un score élevé signifie seulement que plusieurs indices concordent. Les candidats inconnus sont volontairement conservateurs et doivent être vérifiés manuellement.
