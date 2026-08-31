# Mail Migration

Application desktop Python/PySide6 qui analyse plusieurs comptes Gmail pour identifier les services liés aux anciennes adresses e-mail et préparer leur migration.

> **Lecture seule côté Gmail :** aucun e-mail n'est envoyé, modifié ou supprimé.

## Fonctionnalités

- 🔎 Analyse de plusieurs comptes Gmail via Google OAuth
- 🧠 Détection intelligente des services avec score de confiance
- 🖼️ Récupération des photos de profil via **Google People API** lorsque disponibles
- 📋 Inventaire avec recherche et filtres
- 🏷️ Catégories, priorités et statuts de migration
- 💾 Sauvegarde des analyses
- 📤 Export TXT, SQL et PDF
- 🧹 Nettoyage des données de scan

## Installation Windows

Lancez simplement :

```text
start.bat
```

Le script crée l'environnement Python, installe les dépendances et lance l'application.

Installation manuelle :

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Configuration Google

Dans **Google Cloud Console** :

1. Créez ou sélectionnez un projet.
2. Activez **Gmail API**.
3. Activez **Google People API** 
4. Configurez l'écran de consentement OAuth.
5. Créez un identifiant OAuth **Desktop app**.
6. Téléchargez le fichier d'identifiants sous `credentials.json` à la racine du projet.
7. Lancez l'application et ajoutez votre compte dans **Comptes Google**.

Si vous avez déjà utilisé une ancienne version, supprimez les anciens tokens OAuth dans `tokens/` avant de vous reconnecter afin que les nouvelles autorisations soient demandées.

> `credentials.json`, `tokens/` et `data/*.db` restent locaux et ne doivent pas être publiés.

## Utilisation

**Comptes Google** → ajoutez vos comptes → lancez un scan.

**Services** → consultez les services détectés, leurs catégories, logos/photos et traces.

**Détails** → consultez les informations disponibles pour chaque service.

**Exportation** → sélectionnez une analyse sauvegardée et exportez-la en TXT, SQL ou PDF.

## Détection

Le scanner combine plusieurs signaux : domaine, expéditeur, nom affiché, sujet, mots-clés et autres informations présentes dans les e-mails. Les services inconnus peuvent également être analysés intelligemment afin de réduire les détections « Inconnu ».

## Structure

```text
Mail-Migration/
├── app/                 # Application, scanner, base de données et interface
├── assets/              # Logos et ressources
├── data/                # Base SQLite locale
├── tokens/              # Tokens OAuth locaux
├── credentials.json     # Identifiants Google locaux
├── requirements.txt
├── start.bat
└── main.py
```

## Technologies

Python · PySide6 · Gmail API · Google People API · SQLAlchemy · SQLite · ReportLab
