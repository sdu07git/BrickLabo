# BrickLabo by SDU7

**Version 0.1.24 — Windows portable**

Logiciel de création d’étiquettes pour les rangements de briques de construction et de gestion du stock.

## Télécharger la version complète

➡️ **[Télécharger BrickLabo v0.1.24 pour Windows](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.24/BrickLabo_by_SDU7_v0.1.24_Windows_Portable.zip)**

[Consulter la page de la version](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.24)

Le ZIP contient le logiciel, son environnement Python et les ressources nécessaires. **Aucune installation séparée de Python n’est nécessaire.**

## Installation

1. Téléchargez le ZIP Windows Portable.
2. Extrayez **toute l’archive** dans un dossier court accessible en écriture, par exemple C:\LEGO.
3. Ouvrez le dossier **BrickLabo** et lancez **BrickLabo.exe**, ou **DEMARRER.bat**.
4. Sur une base vide, laissez l’import automatique des ressources se terminer.

Les imports des fichiers inclus ne nécessitent pas de clé API. Certaines fonctions en ligne dépendent de l’accès aux sites concernés.

## Mettre à jour avec la version complète

1. Fermez BrickLabo et sauvegardez votre installation actuelle.
2. Extrayez la nouvelle version dans un **nouveau dossier court**.
3. Copiez votre ancien dossier **Donnees** dans le nouveau dossier **BrickLabo**, à côté de **BrickLabo.exe**, **avant le premier lancement**.
4. Lancez la nouvelle version et importez les nouveaux fichiers proposés si nécessaire.

**La structure de la v0.1.21 est conservée.** La v0.1.22 avec le dossier Programme est abandonnée : ne superposez pas cette archive à cette version. Conservez votre v0.1.21 d’origine.

Donnees contient le stock, les réglages, les images, les notices, les exports et les journaux. Pour déplacer le logiciel, déplacez son dossier complet.

## Nouveautés de la v0.1.24

- **Photos Rebrickable** : nouveau bouton **Rechercher les photos Rebrickable** pour les pièces Rebrickable et les correspondances BrickArchitect uniques.
- **Sources de photos** : images connues dans les inventaires ; avec une clé Rebrickable, fiche et couleurs avec pagination ; liens d’images de la page de la pièce lorsque le site autorise l’accès.
- **Choix individuel** : les photos rejoignent la liste existante. Le choix reste propre à la référence sélectionnée et actualise l’étiquette et la miniature.
- **Références conservées** : les variantes et autres pièces présentes sur la page ne sont pas assimilées à la pièce sélectionnée. Aucun nom de fichier de photo supplémentaire n’est inventé.
- **Sites inaccessibles** : les photos connues restent disponibles et un message indique les sources refusées. L’ajout d’un lien direct et l’import d’une image locale restent possibles.
- **Sets contenant** : clic droit sur un set → **Afficher la boîte d’origine**, depuis les fenêtres des pièces et des mini-figures. La commande est désactivée sans boîte répertoriée dans Original Boxes.txt.
- **Correctif des boîtes inclus** : le clic droit utilise le set visé même en sélection multiple ; les réponses d’un ancien chargement sont ignorées.

Les améliorations précédentes sont incluses : nouvelle icône, arêtes 3D jusqu’à 10 px et préréglages, texte de catégorie et bandeau dans deux calques distincts, correspondances LDraw explicites, caches de miniatures limités, zoom indépendant des vues et suppression des marges transparentes.

## Fonctionnalités principales

- Catalogues de pièces, sets et mini-figures avec recherche et filtres.
- Catalogue **BrickArchitect** : 5 500 références relevées sur les 22 pages du classement toutes années le 1er octobre 2026.
- Aperçus 3D LDraw, choix de modèles et variantes, photos Rebrickable/BrickLink en recours.
- Éditeur d’étiquettes, exports PDF/PNG et impression.
- Gestion du stock, des notices et de l’historique.

## Sources et licences

La documentation **SOURCES_ET_LICENCES.html** est incluse dans le logiciel et accessible depuis **Sources et licences**. Elle présente les origines des données et ressources : Brick Architect, LDraw, Rebrickable, BrickLink, LEGO et Manuall.

Les modèles LDraw conservent leurs auteurs, mentions de licence et statut officiel ou non officiel. Les textes de licence et registres d’attribution sont inclus dans **licences/LDraw**. Les ressources tierces restent soumises à leurs propres conditions ; l’attribution ne constitue pas à elle seule une autorisation générale de redistribution.

## Aide et validation

Consultez **AIDE.html** pour les commandes et **NOUVEAUTES.txt** pour l’historique regroupé des changements. **PROJET_GITHUB.url** donne accès au dépôt depuis le dossier du logiciel.

La documentation fournie rapporte **154 tests dans 24 modules Python/Qt sous Linux**. Les essais API/page utilisent des réponses simulées. Les photos de **100097** n’ont pas été vérifiées en ligne dans cet environnement (HTTP 403). L’exécutable Windows d’origine est conservé ; son lancement reste à vérifier sur Windows.

Pour signaler un problème, ouvrez une **[Issue](https://github.com/sdu07git/BrickLabo/issues)** en indiquant la version, les étapes de reproduction et la référence concernée. Les journaux sont accessibles via **Logs** ou **OUVRIR_LOGS.bat**, dans **Donnees/logs**.
