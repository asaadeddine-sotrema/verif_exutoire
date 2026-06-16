# Rapport de Projet : Vérification des Tonnages Exutoires

## 1. Objectif

Ce document présente **l’application de vérification des tonnages exutoires** développée pour Sotrema.

### But principal
- Comparer les pesées terrain (fichiers SOTREMA) avec les facturations des prestataires.
- Détecter automatiquement les écarts de tonnage, de client et de matière.
- Faciliter le contrôle et réduire les vérifications manuelles (gain de temps, fiabilité accrue).

### Portée
L’application est déjà utilisée pour plusieurs prestataires et peut être étendue à d’autres :
- Suez
- Valène
- Dupille
- Azalys
- Satel
- Vert Compost
- Autres prestataires futurs

---

## 2. Comment fonctionne l’application ?

### 2.1 Vue d’ensemble du flux

1. **Upload des fichiers**
   - Fichier terrain (pesées SOTREMA, format Excel)
   - Fichier facturation (format Excel fourni par chaque prestataire)

2. **Normalisation**
   - Les colonnes sont renommées en colonnes canoniques (Date, Num Ticket, Client, Poids, Matière, etc.)
   - Les formats sont nettoyés (dates, numéros, majuscules, accents, etc.)
   - Les valeurs incohérentes sont détectées (valeurs manquantes, formats inattendus)

3. **Matching**
   - Correspondance entre terrain et facture via : ticket / bon / date / client (site) / poids
   - Matching multi-niveau :
     - **Match “Ticket”** (clés exactes)
     - **Match “Bon”** (si ticket absent)
     - **Matching tolérant** (date ± tolérance, poids ± tolérance)
   - Calcul des écarts de tonnage (terrain vs facture)

4. **Validation**
   - Vérifications automatiques : client (INT vs EXT), matière, exutoire
   - Production d’un statut (OK / Pb.*) pour chaque ligne

5. **Reporting**
   - Tableau de résultats affiché dans l’interface Streamlit
   - Export possible vers CSV
   - Enregistrement en base PostgreSQL (optionnel) pour historique et suivi

---

## 3. Structure technique du projet

### 3.1 Application principale

- **`app.py`** : point d’entrée Streamlit
  - Authentification (login / logout)
  - Gestion de la base de données PostgreSQL (via SQLAlchemy)
  - Chargement des fichiers et appel des modules de vérification
  - Affichage des résultats (tableaux, filtres, KPI)

### 3.2 Modules de prestataires

Chaque prestataire a son propre module dans `modules/` :
- `modules/verif_suez.py`
- `modules/verif_valene.py`
- `modules/verif_dupille.py`
- `modules/verif_azalys.py`
- `modules/verif_satel.py`
- `modules/verif_vert_compost_smirtom.py`

Chaque module :
1. Lit les fichiers (terrain + facture) en adaptant l’en-tête pour le format papier du prestataire.
2. Normalise les colonnes (renommage, nettoyage, conversions).
3. Applique des règles métier spécifiques (ex: mapping de codes, corrections de noms, formats de date).
4. Lance le moteur de matching (générique ou spécifique).
5. Retourne un DataFrame avec les résultats et les statuts de vérification.

### 3.3 Moteur générique de matching

Le module `modules/verif_generique.py` contient :
- des utilitaires de nettoyage (`nettoyer_texte`, `convertir_date_robuste`)
- une fonction de traitement dynamique (`charger_prestataire_dynamique`) permettant de charger n’importe quel prestataire en fournissant un **mapping de colonnes**
- une fonction `process_generique()` qui effectue un matching standard (ticket / bon) et calcule les écarts

Ce moteur est utilisé comme base pour tous les prestataires et peut être personnalisé avec des règles spécifiques.

### 3.4 Modèles et configurations

- **`modules/models_prestataires.py`** : contient des mappings, des listes de colonnes attendues, des constantes et des configurations par prestataire.
- **Dictionnaires de correction** : utilisés pour normaliser les noms de clients / sites (ex : transformer des codes internes en noms lisibles).

---

## 4. Principaux défis rencontrés (tous prestataires)

### 4.1 Formats hétérogènes des fichiers

- Chaque prestataire fournit des colonnes différentes, parfois avec des noms variables (ex : `Num Ticket`, `N° PESEE`, `Ticket`)
- Les formats de date changent (JJ/MM/AAAA, MM/JJ/AAAA, ISO)
- Des colonnes dupliquées ou mal formatées (ex : `N° adresse de service` présent plusieurs fois)

**Réponse** : normalisation via mappings, fonctions de conversion robustes, gestion des doublons.

### 4.2 Matching client / site

- Les factures peuvent utiliser des codes (ex : `CTCAUBER001`) tandis que le terrain utilise des noms lisibles.
- Le fil conducteur est de retrouver l’exutoire (site) en comparant :
  - les codes / champs de service,
  - les noms normalisés,
  - les corrections via dictionnaires.

**Réponse** : dictionnaires de correction + règles de priorité (ex : prendre le code `N° adresse de service` si disponible). Cela permet de limiter les `Pb.Clt` et d’avoir un matching stable.

### 4.3 Correspondances partielles / données manquantes

- Certains tickets sont absents ou mal renseignés.
- Des factures peuvent regrouper plusieurs tickets.

**Réponse** : matching multi-niveaux (ticket, bon, date), agrégation des poids et tolérance sur écarts.

---

## 5. Utilisation de l’application

### 5.1 Déploiement

```bash
cd verif_exutoire
source .venv/bin/activate
streamlit run app.py
```

### 5.2 Mode opératoire

1. **Se connecter** (login sécurisé)
2. **Sélectionner le prestataire**
3. **Importer le fichier terrain** (SOTREMA)
4. **Importer le fichier facture** (prestataire)
5. **Lancer la vérification**
6. **Analyser les résultats** (tableaux, filtres)

### 5.3 Points de contrôle à surveiller

- Présence des colonnes attendues dans les fichiers factures (voir liste des colonnes dans l’interface)
- Valeurs de `EXT Client` et `INT Client` (doivent correspondre)
- Statut `Verif_Tonnes` (OK / Pb.T)
- Statuts `Verif_Client`, `Verif_Matiere`, `Verif_Exutoire`

---

## 6. Recommandations d’amélioration

- **Tests unitaires** : ajouter des tests automatiques sur les jeux de données types pour chaque prestataire.
- **Extensions** : ajouter un mode de configuration “prestataire” pour charger des mappings JSON/XLS de façon dynamique.
- **Monitoring** : créer un dashboard historique (évolution des écarts, nombre de lignes non matchées).
- **API** : exposer un endpoint pour automatiser les uploads et récupérer les rapports sans UI.

---

## 7. Fichiers clés et points d’entrée

- `app.py` : interface utilisateur et orchestration.
- `modules/verif_generique.py` : moteur de matching générique.
- `modules/models_prestataires.py` : configuration et mappings.
- `modules/verif_<prestataire>.py` : logique par prestataire (adaptation des colonnes, corrections, règles spécifiques).

---

## 8. Annexes

- Exemple de configuration / mappings par prestataire (dans `models_prestataires.py`).
- Exemples de corrections :
  - Codes de site → noms lisibles
  - Normalisation des noms de déchetteries

---
