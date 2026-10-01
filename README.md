# BrickLabo by SDU7

**Version 0.1.18 — Windows portable**

Logiciel de création d’étiquettes pour les rangements de briques de construction et de gestion du stock.

## Télécharger la version complète

➡️ **[Télécharger BrickLabo v0.1.18 pour Windows](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.18/BrickLabo_by_SDU7_v0.1.18_Windows_Portable.zip)**

[Consulter la page de la version](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.18)

Le ZIP contient le logiciel, son environnement Python et les ressources nécessaires. **Aucune installation séparée de Python n’est nécessaire.**

## Installation

1. Téléchargez le ZIP Windows Portable ci-dessus.
2. Extrayez **toute l’archive** dans un dossier accessible en écriture.
3. Ouvrez le dossier `BrickLabo` et lancez **`BrickLabo.exe`**. Vous pouvez aussi utiliser `DEMARRER.bat`.
4. Au premier lancement sur une base vide, laissez l’import automatique des ressources se terminer.

Les imports des fichiers inclus ne nécessitent pas de clé API. Certaines fonctions en ligne dépendent de l’accès aux sites concernés.

## Mettre à jour avec la version complète

1. Fermez BrickLabo et conservez une sauvegarde de votre installation actuelle.
2. Extrayez la nouvelle version dans un **nouveau dossier**.
3. Copiez le dossier **`Donnees`** de votre ancienne installation dans le nouveau dossier `BrickLabo`, à côté de `BrickLabo.exe`, avant le premier lancement.
4. Lancez la nouvelle version.

Le dossier `Donnees` contient notamment le stock, les réglages, les images, les notices, les exports et les journaux. Pour déplacer le logiciel, déplacez son dossier complet.

## Nouveautés de la v0.1.18

- **Arêtes 3D** : nouveau bouton dans le bandeau d’édition de l’étiquette, avec trois niveaux — **Normal**, **Accentué** et **Très accentué**. Les niveaux renforcés rendent les traits plus noirs et plus épais.
- **Aperçu avant application** : contrôle du rendu de la pièce et de l’étiquette. Annuler conserve le réglage précédent.
- **Réglage enregistré** : le même niveau s’applique aux miniatures, aux vues, aux exports et aux impressions. Les photos restent inchangées ; les arêtes cachées restent masquées.
- **Photos des variantes** : correction héritée de la v0.1.17 pour les références à plusieurs correspondances, notamment **m3007**. Le volet droit permet de choisir la référence photo et indique la variante affichée.

## Fonctionnalités principales

- Catalogues de pièces, sets et mini-figures, avec recherche et filtres.
- Catalogue **BrickArchitect** : 5 500 références issues des 22 pages du classement toutes années, relevées le 1er octobre 2026.
- Aperçus 3D LDraw, choix des modèles et variantes, photos Rebrickable/BrickLink en recours.
- Éditeur d’étiquettes, exports PDF/PNG et impression.
- Gestion du stock, des notices et de l’historique.
- Mise à jour du catalogue BrickArchitect avec progression et annulation.

Cette version reprend la base v0.1.9 avec le catalogue BrickArchitect. Le catalogue BrickLabels n’est pas inclus.

## Sources et licences

La documentation **`SOURCES_ET_LICENCES.html`** est incluse dans le dossier du logiciel et accessible depuis son bouton **Sources et licences**. Elle présente les origines des données et ressources : Brick Architect, LDraw, Rebrickable, BrickLink, LEGO et Manuall.

Les modèles LDraw conservent leurs auteurs, leurs mentions de licence et leur statut officiel ou non officiel. Les textes de licence et les registres d’attribution sont inclus dans `licences/LDraw`.

Les ressources tierces restent soumises à leurs propres conditions. La documentation de la version précise qu’une attribution ne constitue pas à elle seule une autorisation générale de redistribution, notamment pour les données dérivées de Brick Architect.

## Validation et assistance

L’historique de la v0.1.18 rapporte **120 tests réussis dans 19 modules Qt/Python sous Linux**, avec comparaison du rendu LDraw 3001 aux trois niveaux d’arêtes. Le binaire Windows n’a pas été exécuté dans cet environnement de validation.

L’historique détaillé est inclus dans `docs/HISTORIQUE_CORRECTIFS.txt`. Pour signaler un problème, ouvrez une **[Issue](https://github.com/sdu07git/BrickLabo/issues)** avec la version, les étapes de reproduction et la référence concernée.

Les journaux sont accessibles par le bouton **Logs** ou `OUVRIR_LOGS.bat`, dans `Donnees/logs`.
