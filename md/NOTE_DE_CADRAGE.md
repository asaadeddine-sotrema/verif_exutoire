# Note de Cadrage : Automatisation de la Vérification des Tonnages

## 0. Résumé Opérationnel
Ce projet automatise le contrôle de facturation des déchets. Il réduit le temps de traitement de plusieurs heures à quelques secondes, sécurise le chiffre d'affaires en détectant 100% des écarts, et garantit la conformité des données (RGPD/Sécurité).

## 1. Contexte et Problématique
La vérification mensuelle des tonnages est une tâche critique pour le suivi de la facturation et de l'exploitation. Actuellement, ce processus est réalisé manuellement en croisant plusieurs sources de données (fichiers "Terrain" internes type ECOREC vs fichiers "Exutoire" externes).

**Problèmes identifiés :**
*   **Chronophage :** Nécessité d'ouvrir et de manipuler plusieurs fichiers Excel.
*   **Risque d'erreur :** La comparaison visuelle ligne par ligne sur des centaines de tickets est faillible.
*   **Hétérogénéité :** Les formats de fichiers varient selon les exutoires (en-têtes, formats de date, nommage des colonnes).

## 2. Objectifs du Projet
L'objectif principal est de développer une suite d'outils pour :
1.  **Automatiser le rapprochement** des tickets de pesée entre les données internes et externes.
2.  **Sécuriser le chiffre d'affaires** et les coûts en identifiant systématiquement les écarts de tonnage et les tickets manquants.
3.  **Gagner du temps** opérationnel en réduisant la tâche de plusieurs heures à quelques secondes.
4.  **Centraliser le reporting** via une sortie standardisée exploitable par une application Web.

## 3. Périmètre
Le projet se décline en plusieurs modules spécifiques propres à chaque exutoire (VALENE, DUPILLE, PICHETA GPSEO et SUEZ).

## 4. Architecture Technique
*   **Langage :** Python 3
*   **Interface Utilisateur (GUI) :** Streamlit (pour une utilisation simple par les opérateurs sans connaissances en code).
*   **Traitement de données :** Pandas, Numpy (pour la performance sur les volumes de données).
*   **Stockage/Sortie :** Base de données centralisée afin de coupler robustesse et fiabilité.
*   **Infrastructure :** Serveur Ubuntu.
*   **Sécurité :** Authentification chiffrée (SHA-256/Bcrypt) et conformité RGPD (traçabilité des actions).

## 5. Fonctionnalités Clés
### 5.1 Importation et Nettoyage
*   **Détection dynamique des en-têtes :** Les scripts scannent les 20 premières lignes pour trouver le début réel des tableaux (mots-clés "Num Ticket", "Description", etc.).
*   **Normalisation :**
    *   **Dates :** Gestion robuste des formats Excel (Serial), texte (JJ/MM/AAAA).
    *   **Matières :** Mapping des désignations variées vers un référentiel commun (ex: "Déchets Ind" = "ORDURES MENAGERES").
    *   **Numériques :** Conversion des poids et tickets, nettoyage des espaces et caractères invisibles.

### 5.2 Algorithme de Matching
*   **Clé de jointure :** `Num Ticket`.
*   **Type de jointure :** *Full Outer Join* (permet de voir les tickets présents chez nous mais pas chez eux, et inversement).

### 5.3 Règles de Vérification
Le système génère 4 statuts de contrôle pour chaque ligne :
1.  **Verif_Tonnes :** "OK" si l'écart (Poids Terrain - Poids Facture) est null ou inférieur à 5kg (0.005t). Sinon "Pb.T".
2.  **Verif_Matiere :** "OK" si la matière correspond. Sinon "Pb.Mat".
3.  **Verif_Exutoire :** "OK" si le ticket est trouvé des deux côtés. Sinon "Pb.Ext" (ou "Manquant").
4.  **Verif_Client :** "OK" si le client correspond (avec gestion de règles spécifiques type GPSO/CCPIF).

## 6. Livrables
1.  **Application Web Centralisée** : Tableau de Bord consolidé avec ingestion des fichiers Excel et visualisation des données.
2.  **Base de Données PostGreSQL** consolidée, mise à jour incrémentalement par l'outil web.
3.  **Documentation** (ce document + documentation utilisateur).

## 7. Planning et Statut
*   **Développement :** En cours.
*   **Phase actuelle :** Développement d'un algorithme permettant de faire correspondre chaque ligne sans numéro de ticket pour SUEZ
*   **Actions en cours :**
    *   **Ajout de l'exutoire SUEZ :** En cours de finalisation.
    *   Amélioration de la robustesse face aux fichiers Excel mal encodés.
    *   Affinement des règles de détection des clients (Code Adresse vs Nom Client).
*   **Réalisé récemment :**
    *   **Sécurisation de l'application :** Mise en place d'une authentification forte.
    
*   **Prochaines étapes :**
    *   Intégration des nouvelles fonctionnalités dans l'outil web.
    *   Tests approfondis et validation des résultats.
    *   Documentation et formation des utilisateurs.
