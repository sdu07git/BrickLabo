# BrickLabo — v0.1.39

Logiciel de bureau Windows pour les catalogues LEGO, les stocks, les recherches de constructions et les étiquettes. Cette mise à jour reprend la version livrée v0.1.38, issue de la v0.1.28 d’origine ; le dépôt GitHub modifié par erreur n’a pas servi de base.

## Contrôle et corrections v0.1.39

Les lectures courtes de SQLite partagent une connexion en lecture seule, protégée entre les tâches. Les réimports de pièces et changements de visuel identiques évitent les mises à jour inutiles et les réécritures FTS5. Les catégories calculées des mini-figures sont conservées au réimport.

Les photos décodées utilisent un cache RAM borné de 32 Mio ; les textes LDraw un cache de 8 Mio. Les lectures répétées d'une photo ne relisent plus son registre JSON. Les aperçus rapides regroupent les demandes et terminent sur la dernière sélection. Une purge ou un changement de réglage empêche une ancienne tâche de remettre son résultat dans le cache.

Les imports d'inventaires personnels sont atomiques : une erreur annule ensemble leur création et l'ajout au stock. Les ajouts multiples constituent une seule action annulable. Les changements de couleur conservent le total et l'annulation même lorsque deux lignes fusionnent. Les mises à jour BrickArchitect restaurent l'ancien catalogue et son archive si leur publication échoue.

Les téléchargements intermédiaires BrickArchitect utilisent la session de `Donnees/temp` et sont supprimés en cas d'échec. Le bouton **Nettoyer les temporaires de plus de 7 jours** traite aussi l'ancien dossier `Donnees/temporaires`, affiché dans Espace disque s'il existe. Les fichiers référencés, récents et les sessions actives sont protégés. Les sauvegardes complètes excluent ces deux dossiers. La fermeture attend les tâches en cours avant de fermer les archives et nettoyer la session. Consulter les notices ne crée plus de dossiers vides.

Le lanceur est recompilé avec l'icône d'origine en sept tailles au format bitmap Windows classique. La fabrication contrôle que les images intégrées au `.exe` correspondent au `.ico` fourni et que les dépendances du paquet correspondent aux versions fixées dans `app/requirements.txt`. L'affichage dans l'Explorateur Windows reste à confirmer sur un PC Windows.

## Installation

Extraire entièrement le ZIP complet dans un **nouveau dossier accessible en écriture**. Fermer l’ancienne version, conserver une sauvegarde, puis copier son dossier **Donnees** à côté du nouveau **BrickLabo.exe**. Lancer l’exécutable. Ne pas superposer les installations.

La migration conserve les quantités observées et sépare les pièces en vrac des composants suivis des sets. Avant de déplacer d’anciens sets, une copie de la base est conservée dans `Donnees/sauvegardes/avant_v37.sqlite`. Les sets sans suivi ne reçoivent pas de pièces inventées ; un rapport signale les inventaires incomplets.

## Nouvelles fonctions

- **Mon stock** contient le vrac et les mini-figures. **Mon stock set** contient les sets et leurs composants enregistrés. Le tableau inférieur affiche les quantités totales possédées, les aperçus, le tri par en-tête et le double-clic d’une pièce. Retirer un set peut supprimer ses composants ou les déplacer vers le vrac.
- **Annuler la dernière action / Ctrl+Z** annule le dernier ajout, import, retrait ou changement de quantité / couleur dans les stocks ou la file d’étiquettes. Un import forme une seule action. Le journal survit au redémarrage ; une restauration du stock le réinitialise. Une modification ultérieure incompatible bloque l’annulation.
- **Importer une collection** accepte les listes de pièces ou de sets Rebrickable CSV, et BrickLink CSV, TXT tabulé ou XML. Choisir la source et le stock de destination. Un set destiné au vrac est décomposé ; des pièces destinées au stock set s’attachent à un set existant ou à un inventaire personnel nommé. Les références et inventaires doivent être disponibles localement. Toute référence inconnue ou inventaire incomplet interrompt le lot avant de modifier les quantités.
- **Exporter vers Rebrickable** produit deux CSV, sets possédés et pièces en vrac, sans compter deux fois les composants des sets. Vérifier les correspondances de références et couleurs. Les inventaires personnels ALT ne sont pas assimilés à des sets officiels.
- **Sets réalisables** combine le vrac et les pièces des sets autorisés. Le tableau du haut affiche la photo du set ; toutes ses colonnes, dont **Set**, se redimensionnent en faisant glisser le bord de l’en-tête. Les photos suivent les références lors d’un tri et utilisent le cache partagé. **Choisir le stock utilisable** réserve des sets ou des pièces sans les supprimer. Les résultats sont évalués séparément : ils ne garantissent pas de construire tous les sets simultanément.
- **MOC par mot clé / créateur** est accessible dans les catalogues de sets Rebrickable, BrickLink et alternatifs, ainsi que depuis les écrans de stock. Le bouton reprend le mot clé de la recherche du catalogue : saisir `falcon`, ouvrir cette recherche puis cliquer sur **Rechercher**. Elle consulte tous les MOC et alternatives publiés sur Rebrickable, indépendamment des sets possédés. Le nom exact du profil d’un créateur peut être ajouté ou utilisé seul. Les MOC et alternatives sont inclus par défaut ; **Constructions alternatives uniquement** et **Notices gratuites uniquement** restent facultatifs. Le mode public en ligne charge une page à la fois ; **Charger la suite** continue. Sélectionner un résultat affiche sa photo et les sets de départ indiqués par Rebrickable, avec leurs liens pour préparer un achat. Un MOC original peut ne pas avoir de set de départ. Le mode des résultats déjà consultés est une liste locale non exhaustive. Le bouton Rebrickable ouvre la même recherche dans le navigateur si la page ne peut pas être lue.
- L’API v3 ne fournit pas de recherche globale ni les inventaires complets des MOC. La recherche générale utilise les pages publiques, dont la structure peut changer. Les suggestions depuis le stock utilisent les alternatives des sets reconstituables ; vérifier les pièces et notices sur le site.
- Dans **Éditeur d’étiquettes → Ajouter une pièce**, choisir une autre référence, sa couleur et 3D / photo. Le visuel et la référence ont leurs propres calques ; déplacer, redimensionner, dupliquer, masquer ou supprimer chacun, puis Appliquer pour conserver la composition à la réimpression.
- **Sauvegardes → Exporter les familles choisies** écrit un JSON séparé pour les modèles d’étiquette, couleurs des catégories, vues / rendus 3D, vrac, sets / composants, file d’étiquettes et préférences. Les clés API sont facultatives et décochées par défaut. Restaurer uniquement les familles voulues ; leurs fichiers sont validés et appliqués ensemble. Les réglages utilisent les références, pas les identifiants internes. Les JSON n’incluent pas les photos locales, archives LDraw ou inventaires complets des catalogues ; la sauvegarde ZIP complète reste disponible.
- **Espace disque** règle les limites RAM et disque des miniatures (32 / 256 Mio par défaut). Le disque à **0** garde uniquement la RAM. Les rendus identiques partagent un cache RAM borné de 64 Mio et les demandes simultanées sont regroupées. Les lectures ne réécrivent pas les images ni leur date. La purge protège les sessions actives et les fichiers de données référencés.

## Dossiers et chemins

À la racine : **BrickLabo.exe**, **LISEZ-MOI.txt**, **PROJET_GITHUB.url** et les dossiers **app**, **ressources**, **documentation**, **licences**. **Donnees** est créé au lancement. Aucun BAT n’est nécessaire dans la distribution Windows. Python et les bibliothèques sont dans `app` et `app/lib` ; `app/bootstrap.py` est l’unique point de démarrage.

Les ressources sont résolues depuis le dossier du logiciel, indépendamment du dossier courant. Python et Qt utilisent une session de `Donnees/temp`, configurée avant Qt ; les sessions abandonnées sont nettoyées. Les fichiers générés ont des noms courts. Toutes les ouvertures SQLite sous Windows utilisent le mode win32-longpath, qui conserve les verrouillages de la base. Les limites de Windows et de certaines bibliothèques subsistent : en cas d’erreur de chemin, déplacer **tout** le logiciel vers un chemin plus court.

L’aide complète se trouve dans [documentation/AIDE.html](documentation/AIDE.html). Les origines et licences sont dans [documentation/SOURCES_ET_LICENCES.html](documentation/SOURCES_ET_LICENCES.html).

## Historique depuis 0.1.27

| Version | Ajouts documentés |
| --- | --- |
| 0.1.27 | Inventaires BrickLink TXT ; sauvegarde et restauration complète. |
| 0.1.28 | Interface et aide en français et anglais. |
| 0.1.30 | Alternatives de sets ; noms de caches et temporaires courts ; exports protégés. |
| 0.1.31 | Exports Rebrickable séparés pour sets et pièces ; correspondances BrickLink. |
| 0.1.32 | FTS5, filtres multicritères enregistrables et sets réalisables. |
| 0.1.33 | Aperçus des pièces ; exports manquantes / possédées ; contours des catégories de pièces. |
| 0.1.34 | Table locale des couleurs Rebrickable / BrickLink / LEGO / LDraw ; choix des ambiguïtés 72 et 77. |
| 0.1.35 | Suggestions de MOC depuis les sets reconstituables ; filtres du stock par sets et pièces. |
| 0.1.36 | Catégories par tags, aperçus et tri des résultats. |
| 0.1.37 | Stocks séparés, annulation, imports de collections, recherche MOC, étiquettes multiples, sauvegardes sélectives, caches bornés et architecture app. |
| 0.1.38 | Photos des sets réalisables, colonnes redimensionnables et recherche globale de MOC / alternatives depuis tous les catalogues de sets, indépendamment du stock. |
| 0.1.39 | Lectures et caches optimisés, imports atomiques, temporaires nettoyés, fermeture des tâches et icône intégrée vérifiée. |

Un seul [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) réunit les notes françaises et anglaises. Les notes de cette branche ne documentent pas de livraison 0.1.29. Les variantes 0.1.28b et Range n’ont pas servi de base. Aucun rapport de tests n’est inclus dans les sources.

## Développement et diagnostic

Le dépôt utilise la même organisation que le ZIP source : `app`, `ressources`, `documentation`, `licences`, `tests` et `tools`. L'archive LDraw `ressources/complete.zip` est exclue de Git car elle dépasse sa limite de taille sur GitHub. Pour retrouver les modèles de la version livrée, copier ce fichier depuis le ZIP source ou complet v0.1.39 téléchargé. Une [archive LDraw officielle](https://library.ldraw.org/library/updates/complete.zip) peut également être placée sous ce nom ; les modèles peuvent évoluer avec sa version. Les tests de premier démarrage et le diagnostic 3D nécessitent cette archive.

Installer Python 3.12, créer un environnement virtuel puis `python -m pip install -r app/requirements.txt`. Lancer `python app/bootstrap.py`. Tester avec `python tools/run_tests.py`. Sous Linux avec MinGW-w64 : `python tools/build_distribution.py chemin/BrickLabo_v0.1.38_Complet.zip dossier_de_sortie`. L’outil reprend les bibliothèques de l’archive complète précédente ; il accepte aussi l’ancienne organisation v0.1.36.

Diagnostic du paquet : `BrickLabo.exe --self-test` écrit `Donnees/diagnostic.json`. En console : `app/python.exe -B app/bootstrap.py --self-test`. Les tests sont réalisés sous Qt/Linux ; le lanceur compilé et la structure des archives sont inspectés ; l’exécution native Windows reste à vérifier sur un PC Windows.

Projet : https://github.com/sdu07git/BrickLabo. Ne pas publier Donnees ni les sauvegardes privées.

Contrôle après fabrication : `python tools/check_distribution.py chemin/BrickLabo`.
