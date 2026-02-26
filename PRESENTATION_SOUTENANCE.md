# 🎓 Plan de Soutenance Orale (Session Intermédiaire - Semestre 1)
**Candidat :** Amine SAAD-EDDINE | **Date :** 27 Février | **Durée cible :** 15-20 min
**Entreprise :** SOTREMA | **Poste :** Chargé de Projet DATA (Service Exploitation)

---

## 1. L'Entreprise & Enjeux (3-4 min)
*Le contexte d'arrivée (3 mois).*

### 🏢 Identité
*   **SOTREMA** (*Société de Traitement et de Récupération de Matériaux*).
*   **Secteur :** Gestion globale des déchets, transport, et valorisation.

### 🎯 Enjeux Stratégiques
1.  **Conformité réglementaire :** Traçabilité stricte des déchets (qui, quoi, où).
2.  **Optimisation des coûts :** Maîtrise des factures de traitement (Exutoires).
3.  **Digitalisation :** Moderniser des processus d'exploitation historiques (Excel/Papier).

---

## 2. Le Service & Positionnement (3-4 min)
*Mon intégration dans l'équipe.*

### ⚙️ Le Service Exploitation
*   Le "Cœur réacteur" de l'activité : Gestion des tournées, des chauffeurs, et des flux de déchets au quotidien.
*   **Interactions :** Terrain (Chauffeurs/Exploitants) <-> Facturation/Compta <-> Direction.

### 👤 Mon Rôle : Chargé de Projet DATA
*   **Positionnement Transverse :** Apporter la compétence "Data" au sein de l'exploitation pure.
*   **Objectif du Semestre :** Cartographier les flux de données et livrer un premier "Quick Win" (Victoire rapide).

### 🤝 Intégration & Immersion Terrain
> **Point Clé :** J'ai effectué une **immersion totale sur le terrain** pendant les deux premières semaines.
*   **Pourquoi ?** Pour comprendre la réalité du métier avant de coder.
*   **Avec qui ?** J'ai accompagné les **chauffeurs** dans leurs tournées, suivi les **contrôleurs d'exploitation**, et échangé avec les **comptables** et **commerciaux**.
*   **Apport :** Cette phase a été cruciale pour identifier les vrais points de douleur (doubles saisies, pertes d'info) et concevoir un outil adapté aux utilisateurs finaux.

---

## 3. Réalisation du Semestre : "Verif Exutoire V1" (8-10 min)
*La preuve de concept (POC) passée en production.*

### 🏗️ Projet : Automatisation du Contrôle de Gestion
*   **Problématique :** Fiabiliser la facturation entrants/sortants par la Data.

#### 1. Analyse du besoin (Phase Découverte)
*   **Constat d'arrivée :** Processus manuel, faillible et chronophage (Jours de travail).
*   **Action Immédiate :** Proposer une automatisation complète via une Web App.

#### 2. Choix Techniques (Architecture Agile)
*   **Choix Rapides :** Python/Pandas pour le traitement + Streamlit pour l'interface.
*   **Stratégie :** "Fail Fast" -> Développement itératif avec des retours utilisateurs rapides.

#### 3. Réalisation & Challenges (3 premiers mois)
*   **Algorithmes :** Développement d'un moteur de réconciliation "Fuzzy Matching" (Smart Match) pour pallier les erreurs de saisie humaines.
*   **Parsing :** Gestion de fichiers hétérogènes (Excel complexes, multi-onglets).
*   **Résultat à date :** L'outil est fonctionnel et utilisé pour la clôture mensuelle.

### ⏱️ Projet Secondaire : Vérification des Heures
*   Adaptation du moteur pour une première version du contrôle social (RH).

---

## 4. Bilan d'Étape & Feuille de Route (3-4 min)
*Ce qui a été fait vs Ce qui reste à faire pour Septembre.*

### ✅ Bilan d'Intégration (3 mois)
*   **Technique :** Validation de la stack Python en entreprise.
*   **Humain :** Intégration réussie dans l'équipe Exploitation grâce à l'immersion terrain.
*   **Apport Immédiat :** Gain de temps validé sur le contrôle de gestion (divisé par 50).

### 🚀 Feuille de Route (Prochains 6 mois -> Soutenance Septembre)
1.  **Fiabilisation (Industrialisation) :** Passer du mode "Projet" (Script lancé à la main) au mode "Produit Industriel" (Docker, CI/CD).
2.  **Extension :** Couvrir 100% des prestataires (Actuellement ~80%).
3.  **Nouveaux Chantiers :** Analyse prédictive des tonnages ? Optimisation des tournées ?
