# 📖 MANUEL UTILISATEUR - Outil de Vérification Exutoire & Activité V1

> **Développé par :** Amine SAAD-EDDINE (Chargé de Projet DATA - Service Exploitation SOTREMA)

## ℹ️ Introduction
Bienvenue dans le manuel utilisateur de l'application **Verif Exutoire**. Cette Web App a été conçue sur-mesure pour s'intégrer au cœur du service d'exploitation et répondre à des enjeux stratégiques de conformité réglementaire (traçabilité), de maîtrise des coûts et de digitalisation des processus historiques de SOTREMA.

L'application automatise deux processus autrefois chronophages et manuels, pour deux missions principales :
1.  **Le Contrôle Environnement/Exutoires (Contrôle de Gestion Automatisé)** : Remplacer le rapprochement manuel faillible en vérifiant automatiquement que les pesées effectuées par les chauffeurs sur le Terrain correspondent aux factures envoyées par les exutoires (SUEZ, PICHETA, DUPILLE, VALENE). L'objectif est de fiabiliser la facturation entrants/sortants et d'optimiser les coûts associés.
2.  **Le Suivi d'Activité RH (Vérification des Heures)** : Analyser les fichiers d'heures et de planning pour détecter les anomalies de saisie, les manquements aux 35h, et les absences injustifiées.

---

## 🚀 Démarrage et Connexion

### 🌐 1. Accès à l'application
Ouvrez votre navigateur web (Chrome, Firefox, Edge) et accédez à l'adresse du serveur (ex: `http://220.220.220.24`).

### 🔐 2. Authentification
Une page de connexion apparaît.
*   **Identifiant** : Votre nom d'utilisateur (configuré par l'administrateur).
*   **Mot de passe** : Votre mot de passe sécurisé.

---

## 🏗️ MODULE 1 : Vérification des Exutoires (Pesées)

Ce module vous permet de rapprocher vos données internes (Extraction Terrain) avec les données de facturation des prestataires.

### 📍 Étape 1 : Choisir son Exutoire
Dans le menu latéral gauche, cliquez sur **📥 Imports & Vérifications**.  
Une page s'ouvre avec plusieurs onglets en haut comme `SUEZ`, `PICHETA`, `DUPILLE`, `VALENE`.

Cliquez sur l'onglet correspondant à l'exutoire que vous souhaitez vérifier.

### 📂 Étape 2 : Chargement des Fichiers
Chaque exutoire demande des fichiers spécifiques qui sont disponibles dans sous le répertoire **(CONTROLE & POINTAGE / Contrôle Mensuel / Rapports Outil Exutoire)** dans le logiciel métier ECOREC.
Voici les règles pour chacun :

#### 🔹 SUEZ
Vous devez charger **3 fichiers Excel** :
1.  **Fichier Terrain (CTC)** : Extraction de vos pesées CTC.
2.  **Fichier Terrain (DECH)** : Extraction de vos pesées Déchetterie (optionnel mais recommandé).
3.  **Fichier Facture** : Le fichier Excel envoyé par SUEZ.
    *   *Note* : L'application détecte automatiquement les colonnes ("N° Bon", "Poids", etc.).

#### 🔹 PICHETA / VALENE
Vous devez charger **2 fichiers** :
1.  **Fichier Terrain** : Votre extraction interne.
2.  **Fichier Facture** : Le fichier envoyé par le prestataire.

#### 🔹 DUPILLE
Vous devez charger **2 fichiers** :
1.  **Fichier Terrain** : Doit contenir les colonnes "Num Ticket", "Date", "Poids".
2.  **Fichier Facture** : L'outil gère les factures **multi-onglets** (plusieurs feuilles Excel dans un seul fichier). Il fusionnera tout automatiquement.
    *   *Correction automatique* : Si un bon facture regroupe plusieurs tickets terrain (ex: 1 Bon pour 3 voyages), l'outil fera la somme des tickets terrain pour comparer avec le poids unique de la facture.

### ⚙️ Étape 3 : Analyse et Résultats
Une fois les fichiers chargés, le traitement se lance en un clic. Un tableau de synthèse apparaît.

#### Comprendre les Codes Couleurs 🟢🔴
L'outil vérifie 3 points clés pour chaque ligne :

| Colonne | Signification | Statut OK (Vert) | Statut Erreur (Rouge) |
| :--- | :--- | :--- | :--- |
| **Verif_Exutoire** | La ligne existe-t-elle des deux côtés ? | Présent partout | **Pb.Ext** : Ticket facturé mais **inconnu** au terrain (Manquant ? Perdu ?) ou l'inverse. On peut distinguer ces cas là si on a un Num Bon ou pas. |
| **Verif_Tonnes** | Le poids est-il identique ? | Ecart = 0 | **Pb.T** : Ecart de poids != 0 |
| **Verif_Matiere** | La matière correspond-elle ? | Même type de déchet | **Pb.Mat** : Incohérence (ex: Facturé en "DIB" mais bon "GRAVATS"). |
| **Verif_Client** | Le chantier/client correspond-il ? | Même site/client | **Pb.Clt** : Incohérence (ex: Facturé pour la DECHETTERIE EPONE mais bon DECHETTERIE GARGENVILLE). |

> **Astuce** : 
- Les lignes sur fond **Rouge Clair** contiennent au moins une erreur. Les lignes blanches sont parfaites.
- Vous pouvez cocher les lignes avec des erreurs pour isoler les cas traités.
*   **Filtres dynamiques** : Utilisez les filtres interactifs (Flux, Déchetterie, Ecarts Uniquement) pour affiner votre vue, pointer les anomalies instantanément et diviser par 4 le temps de rapprochement des tonnages.

### 🗑️ Étape 4 : Suppression de lignes

Pendant votre rapprochement des tonnages, vous pouvez supprimer les lignes qui ne sont pas pertinentes dans la section 'Administration'. Il suffit de reporter le numéro de ticket au dessus du tableau, de repérer le numéro d'identification de la ligne. Ensuite reporter là dans 'Action sur ID : 🗑️ ARCHIVER', saisissez un motif de suppression et ensuite, 'ARCHIVER LA LIGNE'. Vou spourrez toujours récupérer cette ligne en cliquant sur la case 'Voir les lignes archivées 🗑️' dans le haut de la page.


---

## 👥 MODULE 2 : Gestion de l'Activité (RH)

Ce module sert à vérifier la cohérence des heures déclarées par les chauffeurs et le planning.

Accédez-y via le menu latéral (section Module RH si disponible, ou onglet dédié).

### 📥 1. Import des Données
Vous pouvez charger deux fichiers depuis le répertoire (RH / Outil Activité) sur ECOREC:
1.  **Fichier Heures (Obligatoire)** : L'extraction des heures réalisées (Excel).
    *   *Colonnes requises* : `Date`, `Nom Personnel`, `prenom`, `CodeTravail`, `HeureDebut`, `HeureFin`.
2.  **Fichier Planning (Recommandé)** : Le planning prévisionnel (Excel).
    *   *Colonnes requises* : `Date`, `Affectation`, `Qualification`, `Chauffeur`.

### 📊 2. Résultats de l'Analyse

L'outil va générer plusieurs rapports :

#### ⏱️ A. Synthèse des 35h
*   Affiche pour chaque employé le total des heures travaillées vs l'objectif (généralement 35h ou au prorata des jours travaillés).
*   **Alerte** : Signale si un employé a fait moins d'heures que prévu (ex: 32h sur 35h).

#### ⚠️ B. Anomalies Planning (Si fichier Planning fourni)
*   **Comparaison croisée** : L'outil regarde qui était prévu au planning (Chauffeurs/Equipiers) et vérifie s'ils sont présents dans le fichier d'heures.
*   **Absent du fichier Heures** : Signale une personne qui devait travailler mais n'a pas déclaré d'heures (Oubli de saisie ? Absence imprévue ?).

### 🕵️ 3. Onglet "Suivi de Présences" et Recherche
Cet onglet vous permet d'interroger l'historique.
*   Sélectionnez une **période** (Date Début / Fin).
*   L'outil affiche :
    *   La liste des anomalies sur la période.
    *   Un tableau récapitulatif des présences/activités par jour.

---

## ⚙️ Administration & Base de Données

Dans le menu **Administration**, vous pouvez gérer les données archivées.
*   **Nettoyage** : Supprimer les enregistrements très anciens.
*   **Utilisateurs** : (Réservé Admin) Gestion des accès.

---

## ❓ FAQ & Dépannage

**Q : L'import SUEZ ne marche pas.**
*   Vérifiez que vous avez bien mis les 3 fichiers (ou au moins Facture + 1 Terrain).
*   Vérifiez que vos fichiers sont bien des fichiers Excel (.xlsx ou .xls), pas des CSV bruts.

**Q : J'ai plein de "Pb.Clt" (Erreur Client).**
*   Vérifiez si le nom du client dans votre système est écrit exactement comme sur la facture.
*   L'outil gère des synonymes (ex: "CTC MLV" = "BUCHELAY"), mais pas tout. Signalez les nouveaux cas à l'admin pour mise à jour.

**Q : Un employé n'apparait pas dans le contrôle 35h.**
*   Vérifiez que son nom est bien orthographié dans le fichier d'heures.
*   Vérifiez que la colonne "Date" est bien remplie pour ses lignes.

