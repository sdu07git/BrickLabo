# BrickLabo by SDU7

**Version 0.1.21 — Windows portable**

Logiciel de création d’étiquettes pour les rangements de briques de construction et de gestion du stock.

## Télécharger la version complète

➡️ **[Télécharger BrickLabo v0.1.21 pour Windows](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.21/BrickLabo_by_SDU7_v0.1.21_Windows_Portable.zip)**

[Consulter la page de la version](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.21)

Le ZIP contient le logiciel, son environnement Python et les ressources nécessaires. **Aucune installation séparée de Python n’est nécessaire.**

## Installation

1. Téléchargez le ZIP Windows Portable.
2. Extrayez **toute l’archive** dans un dossier accessible en écriture.
3. Ouvrez le dossier `BrickLabo` et lancez **`BrickLabo.exe`**, ou `DEMARRER.bat`.
4. Sur une base vide, laissez l’import automatique des ressources se terminer.

Les imports des fichiers inclus ne nécessitent pas de clé API. Certaines fonctions en ligne dépendent de l’accès aux sites concernés.

## Mettre à jour avec la version complète

1. Fermez BrickLabo et sauvegardez votre installation actuelle.
2. Extrayez la nouvelle version dans un **nouveau dossier**.
3. Copiez votre ancien dossier **`Donnees`** dans le nouveau dossier `BrickLabo`, à côté de `BrickLabo.exe`, **avant le premier lancement**.
4. Lancez la nouvelle version et importez les nouveaux fichiers proposés si nécessaire.

`Donnees` contient le stock, les réglages, les images, les notices, les exports et les journaux. Pour déplacer le logiciel, déplacez son dossier complet.

## Nouveautés de la v0.1.21

- **Nouvelle icône** : brique jaune et étiquette blanche dans le lanceur Windows et l’application.
- **Arêtes 3D** : épaisseur jusqu’à **10 px**, par pas de 0,1 px ; réglages généraux, individuels et préréglages enregistrés.
- **Catégorie indépendante** : texte et bandeau coloré dans deux calques distincts. Les anciens modèles sont convertis en conservant leurs coordonnées.
- **Édition de l’étiquette** : boutons Modifier cette étiquette et Réinitialiser la disposition placés sous le réglage de l’angle 3D.
- **Couleurs des contours** : liste des catégories limitée à 300 px pour laisser la place à l’aperçu ; nom complet en infobulle.
- **Boîtes d’origine** : clic droit sur un set → **Afficher la boîte d’origine**, avec une fenêtre redimensionnable et un lien BrickLink.
- **Photos manquantes** : recours à une correspondance BrickLink explicite unique, notamment pour **113578**, sans API BrickLink.
- **Correspondances LDraw** : 6 935 références Rebrickable uniques extraites des en-têtes ; les références ambiguës ne sont pas substituées. Cas **98138pr9996 → 98138pa4.dat** inclus.
- **Aide détaillée** : guide de 129 commandes et gestes, boutons, menus clic droit, raccourcis et réglages.
- **Accès GitHub** : fichier `PROJET_GITHUB.url` à côté du logiciel.

Les améliorations précédentes sont incluses : caches de miniatures limités en mémoire et sur disque, préréglages d’arêtes, zoom indépendant des vues et suppression des marges transparentes.

## Fonctionnalités principales

- Catalogues de pièces, sets et mini-figures avec recherche et filtres.
- Catalogue **BrickArchitect** : 5 500 références relevées sur les 22 pages du classement toutes années le 1er octobre 2026.
- Aperçus 3D LDraw, choix de modèles et variantes, photos Rebrickable/BrickLink en recours.
- Éditeur d’étiquettes, exports PDF/PNG et impression.
- Gestion du stock, des notices et de l’historique.

## Sources et licences

La documentation **`SOURCES_ET_LICENCES.html`** est incluse dans le logiciel et accessible depuis **Sources et licences**. Elle présente les origines des données et ressources : Brick Architect, LDraw, Rebrickable, BrickLink, LEGO et Manuall.

Les modèles LDraw conservent leurs auteurs, mentions de licence et statut officiel ou non officiel. Les textes de licence et registres d’attribution sont inclus dans `licences/LDraw`. Les ressources tierces restent soumises à leurs propres conditions ; l’attribution ne constitue pas à elle seule une autorisation générale de redistribution.

## Aide et validation

Consultez **`AIDE.html`** pour les commandes et **`NOUVEAUTES.txt`** pour l’historique regroupé des changements.

La documentation de la v0.1.21 rapporte **143 tests dans 22 modules Python/Qt sous Linux** et des contrôles visuels. Le lanceur Windows a été contrôlé après insertion de l’icône, mais l’exécutable Windows n’a pas été lancé dans cet environnement. Les scénarios de recours aux photos BrickLink ont été testés avec des réponses simulées, le serveur ayant refusé les téléchargements réels (HTTP 403).

Pour signaler un problème, ouvrez une **[Issue](https://github.com/sdu07git/BrickLabo/issues)** en indiquant la version, les étapes de reproduction et la référence concernée. Les journaux sont accessibles via **Logs** ou `OUVRIR_LOGS.bat`, dans `Donnees/logs`.
