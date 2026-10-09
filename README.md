# BrickLabo — v0.1.47

Logiciel de bureau Windows pour les catalogues LEGO, les stocks, les recherches de constructions et les étiquettes. Cette version reprend la v0.1.46 livrée, issue de la v0.1.28 d’origine.

**Téléchargements v0.1.47 :** [version complète Windows](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.47/BrickLabo_v0.1.47_Complet.zip) · [code source avec ressources](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.47/BrickLabo_v0.1.47_Sources.zip) · [notes de release](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.47). Cette release inclut les corrections des versions v0.1.46 et v0.1.47.


## Aperçus des arêtes, valeurs par défaut et fermeture — v0.1.47

Dans **Arêtes 3D** et **Disposition de cette étiquette**, **Valeurs par défaut** remet le noir à **86,3 %** et l’épaisseur à **1 px**. Le bouton actualise le brouillon et l’aperçu ; **Appliquer comme réglage général** ou **Appliquer** enregistre le choix. **Annuler** conserve les réglages précédents. Pour une étiquette individuelle, les valeurs par défaut deviennent son réglage propre ; **Utiliser le réglage général** rétablit l’héritage des valeurs générales actuelles.

Les changements de noir et d’épaisseur réutilisent la surface et la profondeur du rendu en mémoire. L’épaisseur est calculée pour l’ensemble des traits visibles ; les intersections et traits en double ne cumulent plus leur opacité. 0 % masque les arêtes ; le calcul conserve les arêtes cachées et conditionnelles. Lors de changements rapides, les anciennes demandes s’arrêtent entre les vues et l’aperçu termine sur le dernier réglage. Ces calculs ne produisent aucun fichier temporaire de rendu.

À la fermeture, la fenêtre reste visible avec **Fermeture : arrêt des tâches en cours…** jusqu’à la fin des tâches. Les nouvelles requêtes et tâches en attente sont arrêtées ; une opération locale déjà commencée termine proprement. Les téléchargements interrompus ferment leurs fichiers et retirent les copies partielles. Le verrou de la session temporaire est libéré avant son nettoyage. Le nettoyage prend en charge les chemins longs et les fichiers temporaires en lecture seule. Un échec réel est inscrit dans les logs ; les anciennes sessions libres sont réessayées au démarrage suivant.

Les photos de secours Rebrickable utilisent désormais **1 278 correspondances de pièces supplémentaires**, explicites et uniques, déjà vérifiées dans les données BrickArchitect fournies. Les liens officiels des pages de sets et de minifigurines peuvent confirmer une correspondance ; les petites photos BrickLink **MN/0** sont prises en charge. Références, variantes, inventaires, modèles 3D et choix de couleurs restent propres à leur catalogue. La provenance de la photo est affichée ; les références identiques ne suffisent pas à inventer une correspondance. Les cas de couleurs ambiguës gardent leur choix explicite. Les photos en cache sont réutilisées sans réécriture.

## Photo du set Rebrickable 030-2 — v0.1.46

Si la photo Rebrickable du set **030-2 — Building Set** est indisponible, l’aperçu utilise la photo BrickLink grâce à une correspondance vérifiée. Aucun import du catalogue BrickLink ni clé API n’est nécessaire pour ce recours. La référence **030-2**, avec son zéro initial, et les données du catalogue Rebrickable sont conservées. La provenance **Photo BrickLink : 030-2** apparaît sous l’aperçu.

Les photos de sets acceptent désormais une correspondance explicite unique dans les métadonnées de photos ; des références similaires ou ambiguës ne sont pas assimilées. La photo Rebrickable garde la priorité lorsqu’elle est disponible. Le recours prend en charge les grandes images et les petites images normalisées BrickLink ; les consultations suivantes réutilisent le cache partagé sans réécrire les images.

## Rangement, actions des sets et nettoyage des mises à jour — v0.1.45

Dans **Mon rangement**, utiliser la **molette** ou les boutons **− / +** pour zoomer. **Maj + molette** fait défiler la vue. **Zoom sur le meuble** isole et cadre le meuble sélectionné ; **Vue complète** réactive **Tous les meubles** et recadre l’ensemble, même après un zoom ou un déplacement de la vue. Le pourcentage indique le zoom courant. Le curseur **Taille des aperçus sur les tiroirs** agrandit ou réduit les miniatures dans la façade disponible ; le réglage est conservé et figure dans les sauvegardes des autres préférences. Les noms, adresses et poignées restent dégagés, y compris sur les tiroirs mélangés ou larges. Ces commandes réutilisent les miniatures du cache partagé.

**Organiser le meuble → Renommer le meuble…** change uniquement son nom, sans déplacer ses tiroirs ni changer leurs références. **Retirer les références du tiroir** retire les lignes sélectionnées dans le tableau inférieur. Sans sélection, le logiciel propose de retirer toutes les références du tiroir et demande confirmation. Les pièces, leurs couleurs, leurs quantités et les associations à d’autres tiroirs restent dans le stock.

Dans la fenêtre **Sets contenant**, le clic droit sur un set propose **Afficher la boîte d’origine**, **Voir les constructions alternatives** et **Afficher dans le catalogue de sets**. La recherche d’alternatives ouvre la fenêtre Rebrickable existante ; les conditions de clé API et de disponibilité restent les mêmes. L’action de catalogue bascule la fenêtre principale vers la source du set, retire les filtres qui le masquaient et sélectionne sa référence exacte. Le tag **Référence exacte : … ×** permet de réafficher les résultats de la recherche normale. La fenêtre de consultation reste ouverte ; le tri du tableau conserve la bonne référence dans toutes les actions.

Après une mise à jour intégrée et le démarrage réussi de la nouvelle version, les anciennes copies du logiciel créées par l’installateur dans **Donnees/maj/b…** sont supprimées automatiquement en arrière-plan. Une installation interrompue conserve ses fichiers de retour arrière. Un fichier encore verrouillé est réessayé au démarrage suivant. **Donnees**, les sauvegardes personnelles et les fichiers extérieurs au logiciel sont conservés. Cette fonction ne recherche pas d’anciens dossiers d’installation extraits manuellement ailleurs sur le disque.


## Catégories, tiroirs déplaçables et impression A4 — v0.1.44

**Catégories.** Dans les filtres avancés, cliquer sur **Sélectionner toutes les catégories**, puis décocher les catégories à retirer ou enlever leurs tags avec ×. Le bouton sélectionne aussi les catégories masquées par la recherche. Le compteur indique la sélection ; celle-ci peut être enregistrée dans un préréglage. **Effacer les catégories sélectionnées** rétablit une recherche sans filtre de catégorie.

**Déplacement des tiroirs.** Dans **Mon rangement → Organiser le meuble → Déplacer les tiroirs**, glisser un tiroir vers une autre case. En vue **Tous les meubles**, il peut passer dans un autre meuble. Deux tiroirs de même largeur et hauteur échangent leurs positions, même lorsqu’ils contiennent des références. Un grand tiroir peut utiliser plusieurs cases vides sans nom ; les anciennes cases redeviennent des tiroirs vides. Les emplacements incompatibles et les sorties du meuble sont refusés. Nom, références, couleurs et quantités sont conservés ; le déplacement est enregistré au relâchement. Décocher **Déplacer les tiroirs** pour terminer. Ce mode et **Disposer les meubles** sont exclusifs.

**Impression A4.** Choisir **Organiser le meuble → Imprimer les meubles sur A4…**. L’aperçu indépendant propose le meuble sélectionné, une page par meuble ou une vue d’ensemble respectant leur disposition, en portrait ou paysage. La vue de face utilise un fond blanc, les noms, les adresses colonne / tiroir et jusqu’à trois miniatures par tiroir. Choisir l’imprimante ou **Exporter en PDF…**. Les miniatures proviennent du cache partagé ; les changements de page, d’orientation et les impressions les réutilisent en mémoire. Une référence remplace un visuel indisponible. L’aperçu conserve la disposition à son ouverture : le rouvrir après un changement de rangement.

## Disposition et suppression des meubles — v0.1.43

Dans **Mon rangement**, **Tous les meubles** affiche l’ensemble des meubles à leurs positions et recherche dans tout le rangement. Décocher l’option isole le meuble sélectionné. Cliquer sur un tiroir sélectionne son meuble et affiche son contenu.

**Disposer les meubles** permet de glisser un meuble entier, par sa façade ou son nom, à côté ou au-dessus des autres. Cliquer sur **Terminer le placement** pour sélectionner de nouveau les tiroirs. La position est enregistrée uniquement au relâchement de la souris, puis conservée au redémarrage. Les déplacements, la rotation et le zoom ne génèrent aucun fichier de rendu.

Pour un placement précis, utiliser **Organiser le meuble → Positionner le meuble…**. Choisir un meuble de référence puis **À gauche**, **À droite**, **Au-dessus** ou **En dessous**, régler l’écart et enregistrer. Les coordonnées sont mesurées en tiroirs standards ; une valeur verticale négative place le meuble au-dessus de l’origine. Cette fenêtre permet aussi de modifier le nom du meuble. Deux meubles ne peuvent pas se chevaucher ; agrandir un tiroir jusqu’à un meuble voisin est refusé et demande de déplacer ce meuble d’abord.

**Organiser le meuble → Supprimer le meuble** demande confirmation, puis retire ce meuble, ses tiroirs et leurs associations de rangement. Les pièces en vrac, les sets et leurs quantités sont conservés. Les fenêtres de modification propres au meuble supprimé se ferment. Les positions figurent dans les sauvegardes **Meubles et emplacements** ; les anciens meubles et anciennes sauvegardes sans coordonnées sont disposés côte à côte.

## Mises à jour depuis GitHub — v0.1.42

Dans **Mise à jour des données → Rechercher une mise à jour du logiciel**, consulter les versions stables publiques du dépôt BrickLabo. Les versions identiques, anciennes et les préversions sont ignorées. La recherche est manuelle et ne demande aucune clé API. Les notes de la version proposée s’affichent dans une fenêtre indépendante.

**Télécharger le ZIP complet** prépare la distribution Windows et vérifie son SHA-256 fourni par GitHub, sa version, les exécutables 64 bits et son contenu. Les ZIP sources, fichiers incomplets, chemins dangereux et archives contenant `Donnees` sont refusés. **Annuler le téléchargement**, ou fermer la fenêtre avant l’installation, supprime la préparation sans changer le logiciel. La distribution Windows complète est nécessaire pour installer automatiquement ; le mode source peut consulter les releases.

**Installer et redémarrer** ferme BrickLabo après les tâches en cours et la fermeture de SQLite. Fermer les autres instances ; une restauration de données en attente doit être terminée ou annulée. Un petit runtime isolé du logiciel permet de remplacer les fichiers sans utiliser les DLL encore ouvertes. Les fichiers personnels, stock, modèles, rangement, réglages et clés du dossier **Donnees** restent en place. Une erreur de remplacement ou de lancement de l’exécutable rétablit les anciens fichiers. Un démarrage qui échoue ensuite dans la nouvelle version reste à diagnostiquer avec les logs et une sauvegarde compatible.

Les anciens fichiers restent dans **Donnees/maj/b…** pendant le remplacement. Depuis la v0.1.45, ces anciennes copies reconnues sont supprimées automatiquement après le démarrage réussi de la nouvelle version ; un verrou temporaire entraîne un réessai au démarrage suivant. Les fichiers de travail restent dans **Donnees/temp/u…**, avec des noms courts et des accès Windows adaptés aux chemins longs. Le ZIP et la copie décompressée sont supprimés après une installation réussie ; les restes inactifs du petit runtime sont nettoyés au prochain démarrage ou par la purge. La purge protège les installations actives et les préparations nécessaires à la réparation d’une interruption. **Donnees** et les sauvegardes personnelles sont conservés.

En cas de coupure pendant le remplacement, fermer toutes les instances, consulter `Donnees/maj/transaction.json` et son champ `stage`, puis ouvrir un terminal dans le dossier `Donnees/temp/u…` correspondant et exécuter `r\python.exe -I -B i.py --recover`. Cette réparation vérifie le plan conservé, remet les anciens fichiers et relance le logiciel. Si la préparation est perdue, restaurer les fichiers du dossier `Donnees/maj/b…` dans le dossier d’installation, sans déplacer `Donnees`, depuis l’Explorateur et avec toutes les instances fermées. Pour revenir volontairement à une ancienne version, utiliser aussi une sauvegarde compatible si le format des données a évolué.

Pour passer d’une version antérieure à v0.1.42, installer une fois le ZIP complet dans un nouveau dossier et y recopier **Donnees**, comme indiqué ci-dessous. L’option servira ensuite pour les futures releases publiées. La v0.1.47 est disponible dans les [releases GitHub](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.47), avec le ZIP Windows complet et le ZIP des sources.

## Fond transparent des étiquettes — v0.1.41

Dans **Éditeur d’étiquettes** ou **Modifier cette étiquette**, cocher **Fond transparent**, puis **Appliquer**. Le réglage est conservé dans le modèle général ou individuel, les modèles JSON et la sauvegarde des modèles d’étiquette. Décocher l’option rétablit la couleur de fond choisie. Les anciens modèles gardent leur fond opaque.

Les PNG conservent leur canal alpha ; les PDF et l’impression ne remplissent pas le fond de l’étiquette. Le damier de l’éditeur sert uniquement à visualiser la transparence. Les textes, contours et bandeaux restent visibles. Une photo avec un fond blanc conserve ce fond ; les rendus LDraw gardent leurs zones transparentes.

Pour du vinyle autocollant, utiliser un support prévu pour une imprimante à jet d’encre, suivre les indications du fabricant et vérifier son épaisseur. Le fond transparent laisse apparaître le support ; il ne crée pas d’encre blanche. Imprimer à la taille réelle / 100 % pour conserver les dimensions. Le type de papier et la qualité se règlent dans les propriétés de l’imprimante.

## Mur de rangement et inventaires par lots — v0.1.40

**Mon rangement**, en bas de la navigation de gauche, représente tes meubles en volume ou de face. Dans **Organiser le meuble**, créer un meuble, ajouter un tiroir ou modifier son nom, sa position, sa largeur et sa hauteur. Une unité correspond à un tiroir standard ; agrandir un tiroir réunit les voisins vides, sans déplacer automatiquement des tiroirs contenant des références. Les meubles peuvent s’étendre à de nouvelles colonnes et rangées.

Sélectionner un tiroir puis **Ajouter des références du stock** : sélectionner plusieurs lignes du stock en vrac, avec leurs couleurs. Plusieurs références et couleurs peuvent partager un tiroir ; une référence peut être liée à plusieurs tiroirs. Ces associations ne changent aucune quantité. La façade montre jusqu’à trois aperçus et un nom libre ; le tableau inférieur affiche tout le contenu. La colonne **Stock global en vrac** montre le total possédé, pas un comptage par tiroir. Une référence à zéro reste localisable.

Rechercher par référence, nom, dimensions, couleur ou nom du tiroir. `1x1` et `1 x 1` sont équivalents. **Tous les meubles** recherche dans tout le rangement ; choisir un résultat affiche et surligne son tiroir, par exemple **Colonne 3 · Tiroir 5**. Régler l’angle ou la vue de face ; **Ctrl + molette** zoome et **Vue complète** recadre. Le mur utilise les miniatures partagées ; ses rotations et déplacements ne produisent aucun fichier de rendu. **Sauvegardes → Meubles et emplacements** exporte cette famille séparément ; la sauvegarde complète contient aussi le rangement.

Les fenêtres de consultation, recherches de constructions, inventaires, notices, aperçus et éditeurs s’ouvrent indépendamment : le logiciel et les fenêtres précédentes restent accessibles. Lors d’un changement du stock, les anciens résultats de construction sont invalidés et demandent une nouvelle recherche. Les confirmations, choix de fichier et certaines saisies ponctuelles attendent toujours une réponse.

Dans **Mise à jour des données → Charger les inventaires de sets par lots**, afficher des sets Rebrickable ou BrickLink par référence / nom / thème, sélectionner les lignes ou saisir des références connues du catalogue. **Préparer la sélection** enregistre une file. **Sets par lot** est réglable de 10 à 1000 ; **Charger le prochain lot** s’arrête après ce lot et **Enchaîner les lots** continue jusqu’à une pause. Les inventaires déjà complets sont conservés par défaut ; l’actualisation volontaire se règle à la préparation. La file, les réussites et les erreurs sont conservées après fermeture ; **Réessayer les erreurs** remet seulement les erreurs en attente. Une interruption ne publie pas une page partielle d’inventaire. Les clés API de la source sont nécessaires pour les téléchargements. Les requêtes Rebrickable sont espacées ; un refus d’authentification ou une limitation arrête le lot et conserve la file.

Charger ces inventaires ne déclare pas les sets possédés et n’ajoute aucune pièce au stock. Ils alimentent **Sets réalisables**, puis les suggestions d’alternatives des sets reconstituables. Le chargement de sets officiels ne constitue pas un catalogue complet d’inventaires de MOC : l’API v3 ne fournit pas leurs inventaires généraux. La comparaison exacte d’un MOC nécessite son propre inventaire. Pour obtenir tout le catalogue Rebrickable, privilégier les fichiers CSV existants.

La v0.1.47 est disponible dans les [releases GitHub](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.47), avec le ZIP Windows complet et le ZIP des sources.

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
| 0.1.40 | Mur de rangement, fenêtres indépendantes et inventaires par lots. |
| 0.1.41 | Fonds transparents des étiquettes, exports et impression. |
| 0.1.42 | Mises à jour GitHub vérifiées, installation après fermeture et retour arrière. |
| 0.1.43 | Suppression des meubles et disposition persistante côte à côte ou superposée. |
| 0.1.44 | Sélection de toutes les catégories, glissement des tiroirs avec échanges et impression / PDF A4 des meubles avec miniatures. |
| 0.1.45 | Zoom et miniatures du rangement, renommage et retrait des références, actions des sets contenant et nettoyage des anciennes copies après mise à jour. |
| 0.1.46 | Photo BrickLink vérifiée pour le set Rebrickable 030-2, provenance affichée et petites photos normalisées de sets. |
| 0.1.47 | Aperçus des arêtes accélérés en RAM, valeurs par défaut, fermeture visible et nettoyage des temporaires renforcé ; correspondances de photos vérifiées entre catalogues. |

Un seul [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) réunit les notes françaises et anglaises. Les notes de cette branche ne documentent pas de livraison 0.1.29. Les variantes 0.1.28b et Range n’ont pas servi de base. Aucun rapport de tests n’est inclus dans les sources.

## Développement et diagnostic

Installer Python 3.12, créer un environnement virtuel puis `python -m pip install -r app/requirements.txt`. Lancer `python app/bootstrap.py`. Tester avec `python tools/run_tests.py`. Sous Linux avec MinGW-w64 : `python tools/build_distribution.py chemin/BrickLabo_v0.1.43_Complet.zip dossier_de_sortie`. L’outil reprend les bibliothèques de l’archive complète précédente ; il accepte aussi l’ancienne organisation v0.1.36.

Diagnostic du paquet : `BrickLabo.exe --self-test` écrit `Donnees/diagnostic.json`. En console : `app/python.exe -B app/bootstrap.py --self-test`. Les tests sont réalisés sous Qt/Linux ; le lanceur compilé et la structure des archives sont inspectés ; l’exécution native Windows reste à vérifier sur un PC Windows.

Projet : https://github.com/sdu07git/BrickLabo. Ne pas publier Donnees ni les sauvegardes privées.

Contrôle après fabrication : `python tools/check_distribution.py chemin/BrickLabo`.

Pour publier une future mise à jour compatible : créer une release publique stable avec un tag `vX.Y.Z`, des notes de version et le fichier **BrickLabo_vX.Y.Z_Complet.zip** produit par cet outil. GitHub doit exposer le champ `digest` SHA-256 de cet asset dans son API. Les archives Sources générées automatiquement par GitHub ne sont pas installables. Le logiciel consulte au maximum les 100 releases les plus récentes et ne publie aucun fichier.

Pour développer depuis ce dépôt, reprendre `ressources/complete.zip` depuis le ZIP Sources joint à la release : cette archive LDraw dépasse la limite de taille des fichiers GitHub. Les archives automatiques « Source code » ne contiennent ni cette ressource ni le runtime Windows. Les deux ZIP joints sont ceux de la version livrée et testée ; les README du dépôt sont adaptés à la publication.

**Validation v0.1.47 :** 487 tests réussis sous Qt/Linux ; cohérence des archives, versions des dépendances et icône intégrée au lanceur vérifiées. L’exécution native du paquet reste à vérifier sur Windows.
