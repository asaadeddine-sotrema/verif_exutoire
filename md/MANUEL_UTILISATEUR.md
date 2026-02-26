# 📘 Manuel Utilisateur - Vérification des Exutoires

## 1. Introduction
L'application **Verif Exutoire** permet d'automatiser le rapprochement entre les pesées "Terrain" (données internes SOTREMA) et les pesées "Facture" (données envoyées par les exutoires). 

Elle détecte automatiquement les écarts de :
*   ⚖️ **Tonnage** (si différence > 5kg)
*   ♻️ **Matière** (ex: DIB vs OM)
*   🏢 **Client** (ex: GPSEO vs Autre)
*   🏭 **Exutoire** (Ticket manquant ou non trouvé)

---

## 2. Connexion
1.  Accédez à l'URL de l'application.
2.  Entrez votre **Identifiant** et **Mot de passe**.
3.  Cliquez sur **Se connecter**.
> 🔒 La session reste active pendant 3 heures.

---

## 3. Importation des Fichiers
C'est la première étape pour alimenter le système. Allez dans le menu latéral **📥 Import Fichiers**.

### Processus Général
1.  Sélectionnez l'exutoire concerné (DUPILLE, PICHETA GPSEO, VALENE ou SUEZ).
2.  Chargez les fichiers Excel demandés dans les zones correspondantes.
3.  Cliquez sur **Lancer**.
4.  Vérifiez l'aperçu des résultats.
5.  Cliquez sur **💾 Enregistrer tout en Base** pour valider et sauvegarder.

### Détail par Exutoire

#### 🚛 1. DUPILLE
*   **Fichiers Requis :**
    *   `Fichier Terrain` : Export du logiciel de pesée (contient les tickets bruts).
    *   `Fichier Facture` : Excel envoyé par Dupille (peut contenir plusieurs onglets, ex: DECH, PAP).
*   **Particularités :** L'outil gère automatiquement les poids cumulés (ex: 1 Bon Facture pour 3 Tickets Terrain) et fusionne les séquences tickets (hors "ST").

#### 🏗️ 2. PICHETA GPSEO
*   **Fichiers Requis :**
    *   `Fichier CTC` (Optionnel) : Données terrain CTC.
    *   `Fichier DECH` (Optionnel) : Données terrain Déchetterie.
    *   `Export Facture` (Obligatoire) : Fichier de facturation Picheta.
*   **Particularités :** L'outil utilise un "Smart Match" pour retrouver les tickets même si le numéro de bon est manquant, en se basant sur la date et le poids.

#### 🔥 3. VALENE
*   **Fichiers Requis :**
    *   `PAP` : Données Porte-à-Porte.
    *   `PAV` : Données Point d'Apport Volontaire.
    *   `SOTREMA2` : Autres flux SOTREMA.
    *   `Export Facture` (Obligatoire) : Fichier de facturation Valène (Onglet RPT_RecherchePeseeDetaillee).
*   **Particularités :** Vérification stricte des matières normalisées. Le poids est arrondi à 2 décimales.

#### 💧 4. SUEZ
*   **Fichiers Requis :**
    *   `Fichier CTC` : Données Site CTC.
    *   `Fichier DECH` : Données Déchetterie.
    *   `Listing GPSEO` : Le fichier de facturation (Listing détaillé).
*   **Particularités :** L'outil filtre automatiquement sur le client 'GPSEOAUB'. Il tente de reconstruire les correspondances tickets via une recherche par Date + Poids + Client si le lien direct échoue.

---

## 4. Tableau de Bord (Analyse)
Rendez-vous dans **📊 Tableau de Bord** pour analyser les écarts.

### Les Indicateurs
Le tableau utilise des codes couleur et des statuts :
*   ✅ **OK** : Tout correspond.
*   🔴 **Pb.T** (Problème Tonnage) : Écart de poids > 0.1 Tonne.
*   🔴 **Pb.Mat** (Problème Matière) : La matière déclarée ne correspond pas à la facturée.
*   🔴 **Pb.Ext** (Problème Exutoire) : Ticket introuvable chez l'un ou l'autre (Manquant).
*   🔴 **Pb.Clt** (Problème Client) : Incohérence de facturation client (ex: Facturé à GPSEO alors que c'est un privé).

### Validation des Ecarts
Il arrive qu'un écart soit justifié ou acceptable (ex: légère tolérance acceptée exceptionnellement). Vous pouvez le "Valider" pour qu'il ne soit plus considéré comme une erreur dans les statistiques.

1.  Allez dans l'onglet correspondant au problème (ex: `⚖️ Tonnage`, `🏭 Exutoire` ou `🏢 Client`).
2.  Cochez la case **✅ Validé** sur la ligne concernée.
3.  Cliquez sur le bouton **💾 Sauvegarder** qui apparaît dans l'onglet.
> La ligne restera dans la base mais sera masquée des compteurs d'erreurs critiques.

### Filtres
Utilisez le volet de gauche ou le bandeau d'expansion **🔎 Filtres** pour affiner la vue par :
*   📅 **Date** (Période)
*   🏭 **Exutoire**
*   🏢 **Client**
*   ♻️ **Matière**
*   **Numéro de Ticket ou Bon** (Recherche textuelle)

---

## 5. Administration
Section réservée aux utilisateurs avancés : **⚙️ Administration**.

*   **Correction Manuelle** : Vous pouvez modifier n'importe quelle valeur d'une ligne (ex: corriger un numéro de ticket mal saisi) directement dans le tableau. N'oubliez pas de **💾 Sauvegarder les modifications**.
*   **Archivage / Suppression** : 
    *   **Action sur ID** : Pour retirer une ligne unique (ex: doublon), repérez son `ID`, entrez-le dans la zone "Action sur ID", et cliquez sur **🗑️ ARCHIVER**.
    *   **Archivage Périodique** : Pour traiter un ensemble de données (ex: erreur d'import massive), utilisez la section "Archivage par Critères". Sélectionnez l'exutoire, la période, et validez.
*   **Traçabilité** : Chaque modification conserve le nom de l'utilisateur et la date de la dernière action.

---

## 6. Foire Aux Questions (Q/R)

### ❓ Pourquoi mon import affiche un tableau vide ?
*   **Format de fichier :** Vérifiez que vous importez bien des fichiers **Excel (.xlsx, .xls)** et non des CSV.
*   **En-têtes :** Si l'exutoire a changé le nom de ses colonnes, l'outil peut ne pas les reconnaître. Contactez le support.
*   **Onglets :** Pour Valène ou Dupille, vérifiez que les données ne sont pas sur un nouvel onglet non prévu.

### ❓ J'ai un "Pb.T" (Ecart Tonnage) alors que la différence est minime.
*   L'application alerte dès qu'il y a plus de **100 kg (0.1 T)** d'écart (ou 5kg pour certains flux précis).
*   Si cet écart est une tolérance acceptée par SOTREMA, cochez simplement la case **✅ Validé + Sauvegarder** pour clore le dossier.

### ❓ Je ne retrouve pas une ligne dans le Tableau de Bord.
*   Vérifiez le filtre **📅 Date** dans la barre latérale gauche. Par défaut, il peut restreindre la vue.
*   Vérifiez que vous n'avez pas filtré sur un **Exutoire** ou un **Client** spécifique.

### ❓ Que signifie "A_CORRIGER" dans le numéro de ticket ?
*   Cela apparaît (surtout chez SUEZ) quand le ticket est "ST" (Sans Ticket) et que l'outil n'a pas réussi à retrouver le numéro de ticket original via le Bon de Pesée. Il faut corriger manuellement via l'onglet **Administration**.

### ❓ Comment supprimer un doublon ?
*   Ne supprimez pas directement. Utilisez l'onglet **Administration**, repérez l'ID de la ligne en trop, et utilisez la fonction **ARCHIVER**. Cela permet de garder une trace en cas d'erreur.

---

## 🆘 Support
En cas de bug, d'erreur serveur (écran rouge) ou de changement de format de fichier (colonnes modifiées par l'exutoire), contactez l'administrateur technique.
