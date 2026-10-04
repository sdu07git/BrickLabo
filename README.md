# BrickLabo by SDU7

**Version 0.1.36 — Windows portable**

Création d’étiquettes pour les rangements de briques de construction, catalogues et gestion du stock.

## Télécharger

- [Version complète Windows — sans installation de Python](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.36/BrickLabo_v0.1.36_Complet.zip)
- [Code source avec ressources](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.36/BrickLabo_v0.1.36_Sources.zip)
- [Page de la version v0.1.36](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.36)

Le ZIP complet inclut l’exécutable, son environnement Python et les ressources nécessaires. Extraire toute l’archive, puis lancer `BrickLabo.exe`. Choisir un dossier accessible en écriture avec un chemin aussi court que possible.

## Mettre à jour sans perdre son stock

1. Fermer BrickLabo et conserver une sauvegarde de l’ancienne installation.
2. Extraire le ZIP complet dans un nouveau dossier.
3. Copier l’ancien dossier `Donnees` dans le nouveau dossier `BrickLabo`, avant le premier lancement.
4. Lancer `BrickLabo.exe`.

Le stock, les réglages, les images, les notices et les clés API restent dans le dossier du logiciel. Ne pas publier `Donnees` ni ses sauvegardes : ils peuvent contenir des clés API.

## Nouveautés de la v0.1.36

- Recherche avancée par plusieurs catégories sous forme de tags retirables : **OU** entre catégories, **ET** avec le texte et les autres filtres. Les tags sont conservés dans les réglages enregistrés.
- Colonne **Aperçu 3D / photo** dans le tableau des pièces des sets réalisables. Rendu 3D en priorité, photo en recours si disponible.
- Tri par en-tête dans les résultats de sets, pièces, MOC et constructions alternatives, avec tri numérique des quantités et pourcentages.
- Les aperçus, menus et doubles-clics restent associés à la bonne référence après le tri.

## Améliorations incluses depuis la v0.1.27

- Recherche SQLite FTS5 et filtres multicritères, avec recherche compatible si FTS5 est indisponible.
- Recherche des sets réalisables avec les pièces en stock, choix des sets et pièces utilisables sans les supprimer, exports CSV des pièces manquantes et disponibles.
- Export du stock vers Rebrickable en deux listes : sets et pièces en vrac, avec contrôle des correspondances et prévention des doubles comptes.
- Constructions alternatives d’un set et suggestions de MOC via les sets reconstituables avec les pièces disponibles.
- Table locale de 273 couleurs Rebrickable et correspondances BrickLink, LEGO et LDraw. Les ambiguïtés BrickLink 72 et 77 sont choisies par référence de pièce et couleur.
- Noms de fichiers de cache raccourcis et signalement des erreurs de chemins trop longs.

### Limites de la recherche de MOC

Une clé API Rebrickable est nécessaire. L’API v3 permet les alternatives de sets, mais ne fournit pas de recherche exhaustive des MOC par stock ni leurs inventaires détaillés. Les résultats sont des suggestions à vérifier sur Rebrickable, notamment les pièces de rechange et les notices éventuellement payantes. Chaque résultat utilise le même stock indépendamment. Les aperçus de pièces concernent les inventaires de sets disponibles localement.

## Fonctions principales

Catalogues Rebrickable, BrickLink, BrickArchitect et références alternatives ; aperçus LDraw et photos ; éditeur d’étiquettes ; exports PDF/PNG et impression ; stock, inventaires, notices, historique et sauvegardes.

## Sources et lancement

Les modules Python sont consultables dans `atelier/`, les tests dans `tests/`. Avec Python 3.12 sous Windows : `INSTALLER_DEPENDANCES.bat`, puis `DEMARRER.bat`. Pour fabriquer un exécutable : `CONSTRUIRE_EXE.bat`.

Le ZIP Sources contient les ressources volumineuses nécessaires. Le téléchargement automatique « Source code » de GitHub reflète uniquement les fichiers du dépôt.

## Aide, licences et validation

Consulter `AIDE.html`, `NOUVEAUTES.txt`, `RECHERCHE_STOCK.txt` et `COULEURS.txt`. Les sources tierces et leurs conditions figurent dans `SOURCES_ET_LICENCES.html` et `licences/` ; leurs licences et attributions restent applicables.

**50 tests ciblés Python/Qt réussis sous Linux pour la v0.1.36.** Le lancement natif Windows reste à vérifier. L’exécutable portable et son runtime sont conservés ; les modules et ressources sont mis à jour.

Pour signaler un problème, ouvrir une Issue avec la version, les étapes et la référence concernée. Les journaux sont dans `Donnees/logs` ; retirer toute donnée privée avant de les partager.
