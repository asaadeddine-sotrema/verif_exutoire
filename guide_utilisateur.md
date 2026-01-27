# Manuel Utilisateur - Outil de Vérification Exutoire

## 🎯 Objectif de l'outil
Cet outil permet de **rapprocher et contrôler** automatiquement les pesées "Terrain" (vos bons de pesée) avec les factures des exutoires (SUEZ, PICHETA, DUPILLE, VALENE).
L'objectif est d'identifier rapidement :
*   Les écarts de poids (> 20kg ou 0.02t).
*   Les erreurs de facturation (tickets facturés mais inconnus au terrain).
*   Les erreurs d'imputation client (mauvais chantier/déchetterie).

---

## 🚀 Démarrage
Une fois l'application lancée, vous arrivez sur le **Tableau de Bord**.
Utilisez le menu latéral (à gauche) pour naviguer :
1.  **📊 Dashboard** : Vue d'ensemble des indicateurs.
2.  **📥 Imports & Vérifications** : C'est ici que vous ferez le travail principal.
3.  **⚙️ Administration** : Pour gérer la base de données historique (suppression, archivage).

---

## 📝 Procédure de Vérification (Pas à pas)

Allez dans le menu **📥 Imports & Vérifications**.

### Etape 1 : Choisir l'Exutoire
Sélectionnez l'onglet correspondant à l'exutoire que vous voulez traiter :
*   **SUEZ**
*   **PICHTA**
*   **DUPILLE**
*   **VALENE**

### Etape 2 : Charger les Fichiers
Pour **SUEZ** (le plus complet), vous devez charger 3 fichiers Excel :
1.  **Fichier Terrain (CTC)** : Extraction de vos pesées CTC.
2.  **Fichier Terrain (DECH)** : Extraction de vos pesées Déchetterie (optionnel si pas concerné).
3.  **Fichier Facture** : Le fichier Excel envoyé par SUEZ (contient "N° bon de pesée", "Poids", "Adresse service", etc.).

> **Note** : L'outil détecte automatiquement les colonnes. Pas besoin de renommage manuel si le format est standard.

### Etape 3 : Lancer le Traitement
Dès que les fichiers sont chargés, l'outil lance la comparaison automatiquement.
La barre de progression vous indique l'avancement "Traitement en cours...".

---

## 🧐 Analyser les Résultats

Un tableau de synthèse apparaît avec toutes les lignes rapprochées.

### Les Statuts de Contrôle (Colonnes colorées)

L'outil vérifie 3 points clés pour chaque ligne. Si tout est vert, la ligne est validée.

| Colonne | Signification | Statuts Possibles | Action requise |
| :--- | :--- | :--- | :--- |
| **Verif_Exutoire** | La ligne existe-t-elle des deux côtés ? | <span style="color:green">**OK**</span> : Trouvé Terrain & Facture<br><span style="color:red">**Pb.Ext**</span> : Ticket facturé mais **inconnu** chez nous ! | Si **Pb.Ext** : Vérifiez si le ticket n'a pas été perdu ou mal saisi. |
| **Verif_Tonnes** | Le poids est-il identique ? | <span style="color:green">**OK**</span> : Ecart < 10kg<br><span style="color:red">**Pb.T**</span> : Ecart de poids important | Vérifiez si c'est une erreur de saisie ou de pesée. |
| **Verif_Client** | Le chantier/client correspond-il ? | <span style="color:green">**OK**</span> : Le site correspond (ou info manquante)<br><span style="color:red">**Pb.Clt**</span> : Incohérence (ex: Facturé à "Mantes" mais bon "Buchelay") | Vérifiez l'imputation analytique. |

### Codes Couleurs des Lignes
*   **Fond Rouge Clair** : Ligne contenant **au moins une anomalie** (Pb.Ext, Pb.T, Pb.Clt ou Pb.Mat). À traiter en priorité.
*   **Fond Blanc** : Ligne validée (OK partout).

---

## 🔍 Fonctionnalités Utiles

### 1. Filtres Intelligents (SUEZ)
Au dessus du tableau, utilisez les filtres pour cibler votre analyse :
*   **Déchetterie** : Sélectionnez "MANTES JOLIE" pour ne voir que ce site.
*   **Flux** : La liste s'adapte automatiquement (ex: ne montre que les déchets de Mantes).
*   **Ecarts Uniquement** : Cochez cette case pour masquer tout ce qui est "OK" et ne traiter que les problèmes.

### 2. Correction "Smart Match"
L'outil est intelligent :
*   Si le numéro de Ticket diffère légèrement (ex: erreur de saisie), il essaie de retrouver la ligne grâce à la **Date** et au **Poids**.
*   Il gère automatiquement les noms de sites variés (ex: "CTC MLV" est bien reconnu comme "BUCHELAY").

### 3. Exporter
Une fois les vérifications terminées, cliquez sur le bouton **"📥 Télécharger Excel"** pour récupérer le fichier traité avec toutes les colonnes de vérification ajoutées.

---

## ❓ Cas Particuliers Fréquents

**Q: J'ai un statut `Pb.Clt` pour "CTC MLV" vs "BUCHELAY" ?**
R: Cela ne devrait plus arriver. L'outil sait désormais que CTC MLV (Grand Ouest) correspond à Buchelay. Si cela persiste, vérifiez l'orthographe exacte dans le fichier terrain.

**Q: Le poids est différent de 0.005 t (5kg).**
R: C'est considéré comme **OK**. La tolérance est réglée à 0.01 t (10kg) pour absorber les petits écarts de balance.

**Q: Il y a des lignes "A_CORRIGER_XXX" dans le numéro de ticket.**
R: Cela signifie que le numéro de ticket était vide ou illisible ("ST", "NaN"). L'outil a utilisé le numéro de **Bon** pour ne pas perdre la ligne. Il faudra corriger le numéro de ticket dans votre système.
