# Compte-rendu de projet : Outil d'Automatisation Contrôle Tonnage Valène

**De :** Amine SAAD-EDDINE
**Date :** 12/12/2025
**Sujet :** Automatisation de la vérification des tonnages (Exutoire de Valène)

> 📘 **Documentation Mise à Jour (Février 2026)**
>
> Consultez le **[MANUEL UTILISATEUR](MANUEL_UTILISATEUR.md)** pour la documentation complète de la nouvelle version Web (Streamlit) incluant SUEZ, PICHETA, DUPILLE et le module RH.


---

## 1. Le Besoin Initial

La vérification mensuelle des tonnages est une tâche fastidieuse et répétitive. Il fallait ouvrir manuellement quatre fichiers différents (les fichiers opérationnels PAP, PAV, SOTREMA2 et le fichier global de facturation), puis comparer les lignes une par une.

Ce fonctionnement posait deux problèmes majeurs :
* **Perte de temps :** Le processus est long et bloque du temps qui pourrait être mieux utilisé.
* **Risque d'erreurs :** En comparant visuellement des centaines de lignes, il est facile de rater un écart ou un ticket manquant.

Mon objectif était de créer un outil capable de faire ce croisement automatiquement pour sécuriser les données et gagner en efficacité.

## 2. La Solution Technique

J'ai choisi de développer un script en **Python**, car c'est le langage le plus adapté et le plus puissant pour le traitement de données.

### Les choix techniques
* **Langage :** Python
* **Pandas :** J'ai utilisé cette bibliothèque pour manipuler les fichiers Excel comme des bases de données (c'est le moteur du script).
* **Tkinter :** Pour créer une interface graphique (fenêtre) afin que l'outil soit utilisable par n'importe qui dans l'équipe, sans avoir besoin de toucher au code.
* **XlsxWriter :** Pour générer un fichier Excel propre et formaté en sortie.

### Fonctionnement du script
Le programme suit cette logique en 4 étapes :

1.  **Lecture intelligente :** J'ai codé une fonction (`trouver_ligne_en_tete`) qui scanne les 20 premières lignes des fichiers pour trouver où commence réellement le tableau, car les en-têtes ne sont pas toujours sur la première ligne selon les exports.
2.  **Nettoyage :** Le script uniformise les colonnes, transforme les numéros de tickets en format numérique strict et écarte les lignes vides.
3.  **Croisement (Merge) :** Il fusionne les 3 fichiers terrain, puis les compare au fichier de référence en utilisant le "Numéro de Ticket" comme clé unique.
4.  **Calculs :** Il soustrait le poids terrain au poids facturé pour trouver les écarts.

## 3. Ce que l'outil produit (Livrables)

Une fois l'analyse lancée, l'outil génère automatiquement un fichier Excel (`Resultat_Analyse_Tonnage.xlsx`) à l'endroit choisi par l'utilisateur. Il contient 3 onglets séparés pour faciliter le travail de correction :

1.  **Ecarts_Tonnage :** Ne montre que les tickets où il y a une différence de poids réelle (> 1kg) entre notre pesée et celle du client.
2.  **Bons_Manquants :** Liste les tickets que le client nous facture mais dont nous n'avons pas trace dans nos fichiers terrain (PAP/PAV/SOTREMA2).
3.  **Tickets_Non_Conformes :** Isole les lignes illisibles ou sans numéro de ticket, pour qu'elles ne faussent pas les calculs et puissent être corrigées manuellement.

## 4. Difficultés rencontrées et solutions

Durant le développement, j'ai dû résoudre plusieurs points bloquants :

* **Problème :** Les fichiers Excel sources n'ont pas toujours la même structure (logos en haut, lignes vides).
    * *Ma solution :* J'ai développé une détection dynamique qui cherche des mots-clés comme "Description" pour savoir où démarrer la lecture des données.
* **Problème :** Certains tickets étaient au format "Texte" et d'autres "Nombre", ce qui empêchait la comparaison informatique.
    * *Ma solution :* J'ai forcé la conversion en numérique (`to_numeric`) avec une gestion des erreurs pour assurer la jointure des fichiers.
* **Problème :** Rendre le script utilisable sur les PC de l'entreprise sans installer Python partout.
    * *Ma solution :* J'ai compilé le code en un fichier exécutable (`.exe`) autonome.

## 5. Bilan

L'outil est aujourd'hui fonctionnel et permet de réaliser le contrôle des tonnages en quelques secondes. Il est conçu pour être robuste : si un fichier est manquant ou si l'utilisateur annule l'enregistrement, le programme gère l'erreur proprement sans planter.

Je reste disponible pour expliquer le fonctionnement du code ou ajouter des fonctionnalités si de nouveaux besoins apparaissent.