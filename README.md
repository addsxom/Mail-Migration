# Mail Migration

> Application desktop Python/PySide6 qui analyse plusieurs comptes Gmail afin de retrouver les services susceptibles d'utiliser encore vos anciennes adresses e-mail et de préparer leur migration.

Mail Migration répond à une question simple : **« Quels services utilisent encore mon ancienne adresse Gmail ? »**

L'application analyse les traces présentes dans Gmail, identifie les services correspondants, attribue un niveau de confiance et permet ensuite de suivre manuellement leur migration vers une nouvelle adresse.

**Important : Mail Migration est un outil d'inventaire et de suivi. Il ne modifie pas vos comptes Gmail et ne migre pas automatiquement vos comptes externes.**

---

## ✨ Fonctionnalités principales

### 🔎 Analyse des comptes Gmail
- Ajout et gestion de plusieurs comptes Google.
- Connexion via Google OAuth.
- Analyse des métadonnées et traces présentes dans Gmail.
- Détection progressive des services pendant le scan.
- Score de confiance et signaux expliquant les détections.
- Détection de services connus grâce au catalogue intégré.
- Détection prudente de services récurrents absents du catalogue.

### 📋 Inventaire des services
L'onglet **Services** regroupe les services détectés et permet de les rechercher et de les organiser.

Pour chaque service, l'application peut afficher :
- compte Gmail associé ;
- nom et catégorie ;
- niveau de confiance ;
- nombre de traces ;
- statut de migration ;
- priorité ;
- nouvelle adresse de destination ;
- notes ;
- signaux de détection ;
- informations de fiabilité lorsqu'elles sont disponibles.

### 🔄 Suivi de migration
Les statuts disponibles sont :
- **À vérifier** — le service doit encore être vérifié ;
- **À migrer** — le compte doit être migré ;
- **Migré** — la migration a été effectuée ;
- **Abandonné** — aucune migration ne sera effectuée.

Un clic droit sur un service permet d'accéder rapidement aux détails, au changement de statut et à la définition de l'adresse de destination.

### 💾 Analyses sauvegardées
Lorsqu'un scan est terminé, son historique est conservé afin de pouvoir retrouver les analyses précédentes et les utiliser pour l'exportation.

### 📤 Exportation
L'onglet **Exportation** permet de sélectionner une analyse sauvegardée et de choisir son format :
- **TXT** — rapport texte structuré et lisible ;
- **SQL** — données sous forme de commandes SQL ;
- **PDF** — rapport mis en page avec les informations du scan et un tableau des services.

### 🧹 Nettoyage
L'onglet Services possède une fonction de nettoyage permettant de supprimer les données de services et traces issues des scans. Une confirmation est demandée avant la suppression.

---

## 🖥️ Installation

### Méthode recommandée : `start.bat`

Sous Windows, lancez simplement :

```text
start.bat
```

Le script prépare automatiquement l'environnement virtuel, installe/vérifie les dépendances nécessaires puis lance l'application.

### Installation manuelle

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Python doit être installé sur votre ordinateur.

---

## 🔐 Configuration Google OAuth

Avant le premier scan, Mail Migration doit être autorisé à utiliser l'API Gmail.

### 1. Créer les identifiants

Dans Google Cloud Console :
1. créez un projet ;
2. activez **Gmail API** ;
3. configurez l'écran de consentement OAuth ;
4. créez un client OAuth de type **Desktop app** ;
5. téléchargez les identifiants ;
6. placez le fichier à la racine du projet sous :

```text
credentials.json
```

### 2. Ajouter un compte

Lancez l'application, ouvrez **Comptes Google**, choisissez **Ajouter un compte** puis suivez l'authentification Google.

Les fichiers `credentials.json`, `tokens/` et `data/*.db` contiennent des données locales/sensibles et ne doivent jamais être publiés.

---

## 🚀 Utilisation — étape par étape

### 1. Installer

Lancez `start.bat`, ou installez manuellement les dépendances.

### 2. Configurer Google

Placez `credentials.json` à la racine du projet puis ajoutez votre ou vos comptes dans **Comptes Google**.

### 3. Lancer un scan

Dans **Comptes Google** :
1. sélectionnez le compte ;
2. lancez le scan ;
3. laissez l'analyse aller jusqu'à son terme ;
4. une fois terminé, le scan est enregistré dans l'historique.

Les services peuvent apparaître progressivement pendant l'analyse.

### 4. Examiner les services

Ouvrez **Services** pour :
- rechercher un service, un compte ou une catégorie ;
- filtrer par statut ou catégorie ;
- consulter les détails ;
- modifier le statut ;
- définir une adresse de destination ;
- ajouter des notes.

### 5. Vérifier les détections

Un service détecté ne constitue pas une preuve absolue qu'un compte externe existe encore. Consultez le score, les traces et les signaux avant de décider de le migrer.

### 6. Suivre la migration

Utilisez le cycle :

```text
À vérifier → À migrer → Migré
```

ou **Abandonné** lorsqu'aucune migration n'est nécessaire.

### 7. Exporter

Ouvrez **Exportation** :
1. sélectionnez une analyse sauvegardée ;
2. choisissez le chemin du fichier ;
3. choisissez **TXT**, **SQL** ou **PDF** ;
4. cliquez sur **Exporter**.

Chaque format est généré comme un véritable fichier correspondant à son extension et reste lisible lors de son ouverture.

---

## 🧠 Comment fonctionne la détection ?

Le moteur combine plusieurs signaux afin d'obtenir une détection plus fiable :
- domaine de l'expéditeur ;
- adresse de l'expéditeur ;
- nom affiché de l'expéditeur ;
- sujet ;
- mots-clés du catalogue ;
- domaines secondaires et sous-domaines ;
- `Reply-To` lorsque `From` n'est pas disponible ;
- SPF, DKIM et DMARC lorsqu'ils sont présents dans `Authentication-Results`.

Ces signaux contribuent au **score de confiance** affiché dans l'inventaire.

### Services hors catalogue

Le catalogue intégré n'est pas une liste fermée. Lorsqu'un domaine inconnu apparaît suffisamment souvent, il peut être ajouté comme candidat. Les détections inconnues restent volontairement conservatrices afin d'éviter les faux positifs liés aux newsletters et expéditeurs ponctuels.

Certains fournisseurs de messagerie personnels courants (`gmail.com`, `outlook.com`, `icloud.com`, etc.) sont ignorés dans ce processus.

---

## 📚 Catalogue intégré

Le catalogue couvre notamment :
- jeux et plateformes ;
- streaming ;
- shopping ;
- réseaux sociaux et communication ;
- finance et paiements ;
- cloud et développement ;
- productivité et sécurité ;
- voyage, transport et livraison ;
- télécom et services suisses ;
- assurances ;
- emploi et services professionnels ;
- applications et IA.

Les définitions sont principalement dans :

```text
app/services/builtin_catalog.py
```

---

## 🗂️ Structure du projet

```text
Mail-Migration/
├── app/
│   ├── core/          # Configuration, état et logs
│   ├── database/      # SQLite et modèles SQLAlchemy
│   ├── google/        # OAuth et Gmail API
│   ├── scanner/       # Analyse, détection et scoring
│   ├── services/      # Catalogue des services
│   └── ui/            # Interface PySide6
├── assets/            # Ressources visuelles et logos
├── data/              # Base de données locale
├── tokens/            # Tokens OAuth locaux
├── tests/             # Tests
├── credentials.json   # Identifiants Google locaux
├── requirements.txt   # Dépendances Python
├── start.bat          # Lancement sous Windows
└── main.py            # Point d'entrée
```

---

## 🔒 Confidentialité et sécurité

Mail Migration est conçu pour fonctionner en **lecture seule côté Gmail**.

L'application :
- n'envoie pas d'e-mails ;
- ne modifie pas vos e-mails ;
- ne supprime pas vos e-mails ;
- ne modifie pas automatiquement vos comptes externes ;
- conserve les tokens séparément pour les comptes ;
- stocke principalement les métadonnées nécessaires à l'inventaire plutôt que le corps complet des e-mails.

La migration reste **manuelle** : l'utilisateur garde le contrôle de chaque compte.

---

## ⚠️ Limites

Le scanner analyse des traces et métadonnées Gmail. Il ne peut donc pas garantir qu'un compte externe existe toujours.

Un score élevé signifie que plusieurs indices concordent ; ce n'est pas une preuve absolue.

Les services hors catalogue doivent être vérifiés manuellement.

---

## 🛠️ Technologies

- **Python**
- **PySide6** — interface graphique
- **Gmail API** — accès aux données Gmail autorisées
- **SQLAlchemy** — accès à la base de données
- **SQLite** — stockage local
- **ReportLab** — génération des PDF

---

## 📌 État du projet

Le cycle principal est actuellement :

**Comptes Google → Scan → Inventaire des services → Vérification → Suivi de migration → Sauvegarde → Exportation**

Le projet continue d'être amélioré principalement sur la précision des détections, les performances, la stabilité et l'interface utilisateur.

---

## 📄 Licence

Voir les fichiers du dépôt pour les informations de licence du projet.
