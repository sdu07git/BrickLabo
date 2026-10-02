# BrickLabo by SDU7

**Version 0.1.27 — Windows portable**

Logiciel de création d’étiquettes pour les rangements de briques de construction et de gestion du stock.

## Télécharger la version complète

➡️ **[Télécharger BrickLabo v0.1.27 pour Windows](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.27/BrickLabo_by_SDU7_v0.1.27_Windows_Portable.zip)**

[Consulter la page de la version](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.27)

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

## Nouveautés de la v0.1.27

- **Inventaires BrickLink** : bouton **Ajouter l’inventaire depuis un fichier TXT** dans le volet droit des sets et dans la fenêtre de composition. Import également depuis **Mise à jour des données**, pour les fichiers S-référence.txt, sans clé API.
- **Inventaire conservé** : références, couleurs, quantités et indicateurs enregistrés dans SQLite ; le TXT d’origine peut ensuite être supprimé. Réimport remplace l’inventaire et conserve le stock existant.
- **Stock et étiquettes** : les inventaires manuels servent aux ajouts et à la recherche des sets contenant une pièce. Pièces supplémentaires incluses ; variantes et équivalents conservés en base, exclus des ajouts automatiques pour éviter le double compte.
- **Sauvegardes** : ZIP privé et vérifié de Donnees avec base SQLite cohérente. Caches, temporaires et fichiers extérieurs à Donnees exclus. **Les clés API sont incluses : gardez ces sauvegardes privées.**
- **Restauration** : application au prochain démarrage, avec copie de l’état précédent et possibilité d’annuler avant redémarrage.

## Améliorations des versions récentes incluses

### v0.1.26 — Ouverture des dossiers

Double-cliquez sur une ligne du tableau **Espace disque** pour ouvrir le dossier correspondant dans l’Explorateur Windows. Le chemin complet apparaît en infobulle ; les dossiers inexistants sont signalés. Les exports ouvrent le dossier de sortie réellement choisi.

### v0.1.25 — Espace disque et date d’import

- **Espace disque** : mesure des données, miniatures, images, notices, archives LDraw, téléchargements, exports et ressources, en arrière-plan.
- Nettoyage manuel des miniatures et temporaires anciens de Donnees/temp. Fichiers récents et référencés conservés ; aucun nettoyage du Temp global de Windows.
- Réutilisation des archives LDraw identiques et suppression manuelle des copies au contenu identique, avec conservation de l’archive active et des versions différentes.
- Colonne **Date d’import**, masquable, déplaçable et triable avant pagination. La première date est conservée lors des réimports ; les anciennes références sans date indiquent **Inconnue**.

### v0.1.24 — Photos et boîtes d’origine

Bouton **Rechercher les photos Rebrickable** : images des inventaires, fiche et couleurs avec clé API, liens de la page lorsque le site autorise l’accès. Le choix reste propre à la référence et actualise l’étiquette et la miniature. Les variantes présentes sur la page ne sont pas assimilées à la pièce sélectionnée. Les photos connues, l’ajout de lien direct et l’import local restent disponibles si le site refuse l’accès.

Dans **Sets contenant** (pièces et mini-figures), clic droit sur un set → **Afficher la boîte d’origine**. Commande désactivée sans boîte répertoriée dans Original Boxes.txt. Le clic droit utilise le set visé même en sélection multiple ; les anciennes réponses de chargement sont ignorées.

Les améliorations précédentes sont incluses : nouvelle icône, arêtes 3D jusqu’à 10 px et préréglages, texte de catégorie et bandeau dans deux calques distincts, correspondances LDraw explicites, caches de miniatures limités, zoom indépendant des vues et suppression des marges transparentes.

## Fonctionnalités principales

- Catalogues de pièces, sets et mini-figures avec recherche et filtres.
- Catalogue **BrickArchitect** : 5 500 références relevées sur les 22 pages du classement toutes années le 1er octobre 2026.
- Aperçus 3D LDraw, choix de modèles et variantes, photos Rebrickable/BrickLink en recours.
- Éditeur d’étiquettes, exports PDF/PNG et impression.
- Gestion du stock, des notices, de l’historique et des sauvegardes.

## Sources et licences

La documentation **SOURCES_ET_LICENCES.html** est incluse dans le logiciel et accessible depuis **Sources et licences**. Elle présente les origines des données et ressources : Brick Architect, LDraw, Rebrickable, BrickLink, LEGO et Manuall.

Les modèles LDraw conservent leurs auteurs, mentions de licence et statut officiel ou non officiel. Les textes de licence et registres d’attribution sont inclus dans **licences/LDraw**. Les ressources tierces restent soumises à leurs propres conditions ; l’attribution ne constitue pas à elle seule une autorisation générale de redistribution.

## Aide et validation

Consultez **AIDE.html** pour les commandes et **NOUVEAUTES.txt** pour l’historique regroupé des changements. **PROJET_GITHUB.url** donne accès au dépôt depuis le dossier du logiciel.

La documentation de la v0.1.27 rapporte **184 tests dans 28 modules Python/Qt sous Linux**, dont l’inventaire 75192-1 de 765 lignes. L’exécutable Windows d’origine est conservé ; son lancement et l’ouverture réelle de l’Explorateur restent à vérifier sur Windows. Les essais API/page de la recherche de photos utilisent des réponses simulées ; les photos de **100097** n’ont pas été vérifiées en ligne dans cet environnement (HTTP 403).

Pour signaler un problème, ouvrez une **[Issue](https://github.com/sdu07git/BrickLabo/issues)** en indiquant la version, les étapes de reproduction et la référence concernée. Les journaux sont accessibles via **Logs** ou **OUVRIR_LOGS.bat**, dans **Donnees/logs**.

## Code source de la v0.1.27

Les fichiers sources sont consultables directement dans ce dépôt : `main.py`, `atelier/`, `tests/`, `scripts/`, `packaging/` et `ressources/`. Les licences et attributions sont dans `licences/LDraw/`.

Le ZIP `BrickLabo_by_SDU7_v0.1.27_Sources.zip` est également disponible sur la [page de la version](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.27).

### Lancer les sources sous Windows

1. Installez Python 3.12, puis récupérez le dépôt complet.
2. Lancez `INSTALLER_DEPENDANCES.bat` pour créer l’environnement et installer les dépendances.
3. Lancez `DEMARRER.bat` pour ouvrir BrickLabo depuis les sources.
4. Pour fabriquer l’exécutable Windows, lancez `CONSTRUIRE_EXE.bat`.

Pour utiliser le logiciel sans installer Python, téléchargez la version Windows Portable indiquée en haut de cette page.
