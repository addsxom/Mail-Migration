# Mail Migration

Application desktop Python/PySide6 qui analyse plusieurs comptes Gmail pour identifier les services liés à vos anciennes adresses e-mail et préparer leur migration.

> **Lecture seule côté Gmail :** l'application ne modifie, n'envoie ni ne supprime d'e-mails et ne migre pas automatiquement vos comptes externes.

## Fonctionnalités

- 🔎 Analyse de plusieurs comptes Gmail via Google OAuth
- 🧠 Détection des services avec score de confiance et plusieurs signaux
- 📋 Inventaire avec recherche et filtres
- 🏷️ Catégories, priorités et statuts : À vérifier, À migrer, Migré, Abandonné
- 📝 Notes et adresse de destination pour chaque service
- 💾 Sauvegarde des analyses terminées
- 📤 Export TXT, SQL et PDF
- 🧹 Nettoyage des données de scan
- 🖼️ Logos des services lorsqu'ils sont disponibles

## Installation

### Windows — recommandé

Lancez :

```text
start.bat
```

Le script crée l'environnement Python, vérifie/installe les dépendances et lance l'application.

### Manuel

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Python est requis.

## Configuration Google

1. Créez un projet dans Google Cloud.
2. Activez **Gmail API**.
3. Configurez OAuth.
4. Créez un client **Desktop app**.
5. Téléchargez les identifiants sous `credentials.json` à la racine du projet.
6. Lancez l'application et ajoutez votre compte dans **Comptes Google**.

Les fichiers `credentials.json`, `tokens/` et `data/*.db` sont locaux et ne doivent pas être publiés.

## Utilisation

**1. Comptes Google** → ajoutez un compte et lancez un scan.

**2. Services** → consultez les détections, recherchez, filtrez et gérez la migration.

**3. Détails** → consultez les traces, le score, les signaux et les informations disponibles.

**4. Sauvegarde** → les scans terminés sont conservés pour être consultés ou exportés.

**5. Exportation** → sélectionnez une analyse sauvegardée, choisissez le chemin et le format (**TXT / SQL / PDF**), puis exportez.

## Détection

Le moteur combine notamment le domaine, l'expéditeur, le nom affiché, le sujet, les mots-clés, les domaines secondaires et certains éléments d'authentification pour calculer un score de confiance.

Le catalogue intégré couvre les jeux, réseaux sociaux, streaming, shopping, finance, cloud, développement, télécom, voyage, services professionnels et autres catégories courantes.

Les services hors catalogue peuvent être identifiés lorsqu'ils présentent suffisamment de signaux récurrents, tout en restant prudents pour limiter les faux positifs.

## Structure

```text
Mail-Migration/
├── app/                 # Application, scanner, base de données et interface
├── assets/              # Logos et ressources visuelles
├── data/                # Base SQLite locale
├── tokens/              # Tokens OAuth locaux
├── credentials.json     # Identifiants Google locaux
├── requirements.txt     # Dépendances
├── start.bat            # Lancement Windows
└── main.py              # Point d'entrée
```

## Technologies

Python · PySide6 · Gmail API · SQLAlchemy · SQLite · ReportLab
