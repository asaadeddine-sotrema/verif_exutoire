# Plan de Projet


## Phase 0: Observation (5 décembre 2025)

- Objectif : Observer comment le contrôleur travaille pour trouver des solutions adaptées à ses besoins.

## Phase 1: (10 décembre - 31 décembre 2025)

- Objectif : Prouver que c'est faisable.

- Réalisé : Création d'une pipeline ETL
    - Ingestion des fichiers Excel
    - Extraction des données
    - Nettoyage des données
    - Transformation des données
    - Sauvegarde des données dans une base de données (fichier CSV)
    - Visualisation des données avec Power BI

- Dangers actuels : 
    - Fichier CSV => non robuste, ( à la moindre corruption de fichiers, tout est perdu)
    - Nécessité d'avoir une structure de fichiers fixe pour l"extraction des données
    - Fichier CSV stocké dans le dur, il est nécessaire d'héberger un système de gestion de base de données pour plus de robustesse et de fiabilité.

## Phase 2: Premier Test (6 janvier - 9 janvier 2026)

- Objectif : Confronter l'outil, même si pas encore finalisé, à la réalité.

- Action : Expliquer dans les grandes lignes comment fonctionne l'outil ainsi que les différentes catégories.

### Retour d'expérience

- Problèmes relevés :
    - Sans intervention de ma part, le contrôleur semble un peu perdu ( *Solution :* Fournir une documentation simple et claire)
        => si quelqu'un la remplace, pareil.
    - Nécessité pour chaque utilisateur de l'outil du logiciel Power BI.
    - Des lignes rapportés par le logiciel métier matchent des numéros de tickets avec le mauvais exutoire.
        => Le problème vient du fait qu'un chauffeur peut avoir plusieurs tickets pour plusieurs exutoires avec un seul numéro de bon.
        => Solution : 
            - Ajouter la possibilité de supprimer une ligne de la base de données ou bien de la *rendre inactive* avec un motif d'action.

Mais sinon dans l'ensemble, l'outil répond bien aux besoins du contrôleur.

## Phase 3: Consolidation de l'outil (12 janvier - 3/4 février 2026)

- Objectif : Rendre l'outil persistant.

- Action : Passage de Power BI vers Streamlit pour un accès direct au tableau de bord via un navigateur web.

- Tâches :
    - Gestion d'erreurs: Plus de fenêtre rouge sur le tableau de bord. Chaque fonction doit avoir un système de gestion d'erreurs.
    - Passage à un serveur Ubuntu : Création d'un serveur Ubuntu et mise en place de l'outil sur ce serveur en collaboration avec le responsable IT (S. Gagnant).
    - Qualité des données : Régler définitivement les doublons (contrainte UNIQUE SQL) et les faux positifs (ex. nomenclature des clients).
    - **Sécurité & RGPD :** Mise en place de l'authentification forte (Bcrypt) et anonymisation des mots de passe.
    - Suppression/modification des données : Ajouter la possibilité de supprimer une ligne de la base de données ou bien de la *rendre inactive* avec un motif d'action.
    - Déploiement propre : Création d'un systemd. L'outil doit pouvoir redémarrer avec le serveur sans intervention humaine.

## Phase 4: "Crash Test" Utilisateur (4/5 février - 9 février 2026)

- Objectif : 
    - Vérifier que l'outil est robuste et peut fonctionner sans intervention.
    - Confronter l'outil à la réalité du terrain.
    - => Je ne touche plus au code, je laisse le contrôle à l'utilisateur final.

- Tâches :
    - Faire utiliser l'outil par l'utilisateur final avec les fichiers du mois de janvier 2026.
    - Feedback utilisateur : L'utilisateur final va trouver des cas non prévus (un nouveau format de fichier ou un gros client avec une autre dénomination).
    - Optimisation des performances : Quand la base aura 50 000 lignes, l'outil devra être capable de se charger en moins de 10 secondes.

## Phase 5: Industrialisation de l'outil (10 février - 5 mars 2026)

- Objectif : Rendre le projet transmissible.

- Action :
    - Documentation et présentation.

- Tâches :
    - Documentation technique : Architecture, Sécurité (gestion des utilisateurs), Maintenance serveur (Systemd, SQL).
    - Documentation utilisateur : Guide pas à pas (Ajout fichiers, Gestion erreurs, Connexion).
    - Présentation : Présenter l'outil aux utilisateurs finaux.
    - Rapport final : Présenter le projet au responsable du projet. Préparer un rapport statistique.



