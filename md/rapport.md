# DOCUMENTATION TECHNIQUE & OPÉRATIONNELLE
## PROJET : AUTOMATISATION DU CONTRÔLE FACTURATION DÉCHETS

**Date :** 23/12/2025  
**Auteur :** Amine SAAD-EDDINE   
**Sujet :** Automatisation du contrôle des tonnages et des matières  

---

### 1. OBJECTIF DU PROJET

L'objectif de cette solution est de fiabiliser le contrôle de gestion sur les flux de déchets entrants et sortants avec nos partenaires (Dupille, Valene).

**Problèmes résolus :**
* **Suppression du risque d'erreur humaine :** Le pointage manuel sur Excel (centaines de lignes) est remplacé par une vérification algorithmique.
* **Détection instantanée des écarts :** Identification immédiate des tonnages facturés mais non reçus sur site.
* **Gain de temps :** Le traitement mensuel passe de plusieurs heures à quelques minutes.

---

### 2. ARCHITECTURE DE LA SOLUTION

La solution se présente comme une suite logicielle composée de 3 briques interconnectées :

1.  **Les Modules Connecteurs :** Applications autonomes qui lisent, nettoient et croisent les fichiers Excel bruts.
2.  **La Base de Données Centrale :** Un stockage unique et sécurisé qui consolide l'historique.
3.  **Le Tableau de Bord de Pilotage (Power BI) :** L'interface visuelle pour la validation et la prise de décision.

---

### 3. GUIDE DES MODULES D'IMPORTATION

Deux modules spécifiques ont été développés pour traiter les formats de nos prestataires. Ils sont conçus pour être utilisés sans compétences techniques particulières.

#### Le Module "DUPILLE / VALENE" (`app_dupille` / `app_valene`)

* **Fonction :** Ce module automatise le rapprochement des pesées. Il compare ligne par ligne le fichier "Terrain" (nos pesées) avec le fichier "Facture" (envoyé par le prestataire).
* **Mode opératoire simplifié :**
    1.  L'utilisateur ouvre l'application.
    2.  Il sélectionne le fichier Excel interne (Extraction Terrain).
    3.  Il sélectionne le fichier Excel externe (Extraction Facture Dupille ou Valene).
    4.  Il clique sur **"Lancer l'Analyse"**.
* **Résultat :** Le logiciel croise les données via le numéro de ticket unique, calcule les écarts, et injecte le résultat dans la base de données.

---

### 4. LE TABLEAU DE BORD DE PILOTAGE

Le rapport final est l'outil quotidien de la contrôleuse. Il transforme les données brutes en plan d'action.

#### Zone 1 : La Synthèse Financière (KPIs)
En haut du rapport, une vue synthétique permet de juger la santé financière du mois en un coup d'œil :
* **Volumétrie :** Comparaison macroscopique "Total Terrain" vs "Total Facturé".
* **Écart Financier :** Le chiffre clé (ex: **-300 Tonnes**). Si ce chiffre apparaît en rouge, cela indique une perte potentielle nécessitant investigation.

#### Zone 2 : Les Alertes Prioritaires
Le rapport filtre automatiquement les anomalies pour guider le travail de la contrôleuse :
1.  **Alertes Poids :** Isole les tickets où le tonnage facturé est supérieur au tonnage pesé.
2.  **Alertes Matière :** Identifie les tickets où la qualification du déchet diffère (ex: "Déchets Verts" facturés en "DIB", impactant le prix).
3.  **Alertes Manquants :** Isole les tickets présents sur la facture mais inconnus dans notre système (risque de facturation abusive).

#### Zone 3 : Le Détail Opérationnel
Le tableau central liste les anomalies ligne par ligne :
* **Code Couleur :** Les lignes en **ROUGE** signalent une divergence critique.
* **Lecture Rapide :** Les colonnes "Poids Terrain" et "Poids Facture" sont juxtaposées pour faciliter la validation visuelle.

---

### 5. FIABILITÉ & SÉCURITÉ DES DONNÉES

Pour garantir des chiffres incontestables, le système intègre des sécurités techniques :

1.  **Unicité des Tickets :** Le système empêche physiquement d'importer deux fois le même ticket. Les doublons sont automatiquement bloqués pour ne pas fausser la comptabilité.
2.  **Traçabilité :** Chaque ligne importée conserve la trace de sa source (Fichier Terrain ou Facture) et de sa date d'importation.

### 6. CONCLUSION

Cet outil permet de passer d'un contrôle administratif passif à un **contrôle de gestion actif**. Il offre à la direction une visibilité immédiate sur la rentabilité des flux Dupille et Valene, tout en réduisant drastiquement la charge de travail administrative.