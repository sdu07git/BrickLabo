# BrickLabo — v0.1.63

Logiciel de bureau Windows pour les catalogues LEGO, les stocks, les recherches de constructions et les étiquettes. Cette version reprend la v0.1.62 publiée, issue de la v0.1.28 d’origine.

**Téléchargements v0.1.63 :** [version complète Windows](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.63/BrickLabo_v0.1.63_Complet.zip) · [sources avec ressources](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.63/BrickLabo_v0.1.63_Sources.zip) · [notes de release](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.63).

## Réglages des tiroirs dans la proposition — v0.1.63

**Nombre de tiroirs dans le tableau** : Dans Mon rangement → Ranger par catégorie et taille en tenons, régler Nombre de tiroirs directement à côté de Références. Les flèches actualisent la proposition et l’aperçu ; après une saisie, appuyer sur Entrée ou quitter le champ. Le critère Référence est activé automatiquement. Si une ligne réunit plusieurs références de même format, cocher Référence pour disposer d’un réglage par pièce. Les lignes (1/2), (2/2)… partagent le même nombre total ; si les couleurs sont séparées, le nombre s’applique à chaque couleur.

**Conserver les choix et rapprocher les tiroirs** : Changer ce nombre conserve les destinations choisies manuellement, les critères, les couleurs, l’ordre des catégories et le cadrage de l’aperçu. Les placements automatiques peuvent se décaler pour libérer les places voisines. Le logiciel cherche des tiroirs voisins dans le même meuble, de préférence sur la même rangée, en respectant les tiroirs personnalisés, occupés et réservés. Si les destinations restent espacées, un message le signale dans la proposition ; les listes Tiroir proposé restent réglables. Avec Répartir les quantités restantes, 40 pièces dans deux tiroirs donnent 20 + 20. Seul Appliquer le rangement proposé enregistre les emplacements ; le stock global est conservé et le rangement reste annulable en une action.

**Tri par colonne** : Cliquer sur les en-têtes du tableau de proposition ou de Nombre de tiroirs par référence… pour trier dans les deux sens. Quantités et nombres de tiroirs suivent un tri numérique. Les aperçus, champs, sélections et destinations suivent toujours leur référence, y compris après un recalcul. La fenêtre de réglage séparée conserve également les destinations choisies à la main quand elle est validée.


**Validation v0.1.63 :** 893 tests de la suite complète réussis sous Qt/Linux, dont 23 nouveaux contrôles du réglage direct, des destinations conservées, du voisinage et du tri. Interfaces normales et compactes examinées ; archives et lanceur contrôlés par les outils de livraison. [Rapport détaillé](documentation/CONTROLE_v0.1.63.txt). Exécution native Windows à confirmer.

## Formats de meubles et ordre des catégories — v0.1.62

**Dupliquer un format de meuble** : Dans Mon rangement → Organiser le meuble → Dupliquer le format du meuble…, donner un nom à la copie. Le nouveau meuble reprend le nombre de colonnes et de rangées, les positions et les dimensions personnalisées des tiroirs, ainsi que les emplacements laissés sans tiroir. Les tiroirs créés ont un nom et un contenu vides, prêts pour un nouveau rangement. La copie est placée à droite des meubles existants et reste indépendante du modèle. Les stocks et les comptages du meuble original sont conservés. Si le format change pendant la saisie, rouvrir la duplication pour revoir ce format avant de créer la copie.

**Ordre personnalisable des catégories** : Dans Ranger par catégorie et taille en tenons, Ordre des catégories… affiche les catégories des pièces à ranger avec leur position, leur nombre de références distinctes et le nombre de tiroirs nécessaires. Saisir une position puis quitter le champ, ou sélectionner une ligne et utiliser Monter / Descendre. Les autres positions se décalent automatiquement. Ordre alphabétique rétablit cet ordre dans le brouillon. Valider active Catégorie et Taille en tenons ; chaque catégorie est alors traitée dans l’ordre choisi, puis ses formats sont triés par longueur × largeur croissante en tenons. Référence garde le choix d’un tiroir par référence et Séparer les couleurs reste indépendant. Les formats de même surface gardent un ordre déterministe par dimensions. Les dimensions absentes restent signalées ou sont incluses avec Référence, sans taille inventée.

**Enchaîner les catégories dans les meubles** : Avec Tous les meubles, le remplissage continue dans le meuble suivant selon la disposition du rangement. Exemple : 30 références Briques en position 1, puis 23 références Plates en position 2, avec Référence coché. Dans un format de 33 tiroirs, les 30 briques occupent les premiers tiroirs ; les 3 premières plates occupent la suite et les 20 restantes continuent dans le meuble suivant. Si Référence est décoché, plusieurs références de même format peuvent partager un tiroir et le nombre de tiroirs nécessaires est recalculé. Vérifier l’aperçu et les destinations avant Appliquer. Les tiroirs réservés et déjà occupés restent protégés selon les règles de la proposition. L’application du rangement reste annulable en une seule action.

**Retenir un ordre de catégories** : Retenir cet ordre pour les prochains rangements est coché au départ. Valider la fenêtre mémorise l’ordre comme préférence, même si la proposition est ensuite fermée. Décocher cette case utilise l’ordre pour cette proposition seulement ; Annuler conserve les réglages précédents. Les catégories non présentes dans la sélection restent mémorisées après celles qui viennent d’être ordonnées. Les nouvelles catégories sont ajoutées à la suite, par ordre alphabétique. L’ordre est inclus dans Sauvegardes → Autres préférences. Le regroupement libre de références conserve ses affectations manuelles.


**Validation v0.1.62 :** 870 tests de la suite complète réussis sous Qt/Linux, dont 25 nouveaux ; scénario de 30 briques puis 23 plates vérifié sur deux meubles. Interfaces contrôlées en formats normal et compact ; archives et lanceur contrôlés par les outils de livraison. [Rapport détaillé](documentation/CONTROLE_v0.1.62.txt). Exécution native Windows à confirmer.

## Stocks, alternatives et recherche par pièces — v0.1.61

**Rangement dans tous les meubles** : Dans Mon rangement → Pièces à ranger, Meuble de destination propose Tous les meubles pour le glisser-déposer. Dans Ranger par catégorie et taille en tenons, Meubles à utiliser permet aussi de choisir tous les meubles en une opération. L’ordre suit leur position du haut vers le bas, de gauche à droite, puis les tiroirs du haut vers le bas dans chaque meuble. Le tableau indique le nom du meuble et l’adresse du tiroir ; l’aperçu montre tous les meubles retenus. Les tiroirs vides nommés restent protégés. La réorganisation exige une catégorie et conserve les tiroirs mixtes. Une seule action Annuler rétablit l’ensemble.

**Critères de rangement à cocher** : Les cases Catégorie, Taille en tenons et Référence se combinent librement. Catégorie + Taille est le réglage initial ; Catégorie seule réunit la famille, Taille seule peut réunir plusieurs familles de même format, et Référence sépare chaque identité de pièce. Une taille absente du nom n’est jamais devinée : la pièce reste à ranger si seule la taille est demandée, mais reste incluse avec Référence. Séparer les couleurs reste indépendant. Le regroupement libre conserve le choix de plusieurs références dans un tiroir.

**Aperçus et plusieurs tiroirs par référence** : Le tableau de proposition affiche un aperçu 3D ou photo, une quantité proposée et le tiroir de destination. Pour un groupe de plusieurs références, l’image représente la première pièce ; sélectionner la ligne et ouvrir Contenu du tiroir pour voir toutes les références et leurs aperçus. Nombre de tiroirs par référence… permet de choisir 1, 2, 3 tiroirs ou davantage pour chaque référence et coche Référence. Avec Répartir les quantités restantes, les quantités sont réparties aussi également que possible entre ces tiroirs, couleur par couleur, sans modifier le stock global. Par exemple, 40 pièces dans 3 tiroirs donnent 14, 13 et 13. Sans comptage, les associations restent À renseigner. Depuis un catalogue, aucune possession n’est créée. Si Séparer les couleurs est coché, le nombre de tiroirs s’applique à chaque couleur. Tous les tiroirs demandés pour une référence doivent être choisis, ou tous laissés sans emplacement ; une répartition partielle bloque l’application. Pour modifier ensuite les nombres, utiliser l’inventaire du tiroir ou Transférer une quantité…. Décocher Référence ou changer de mode remet les nombres de tiroirs à leur valeur initiale.

**Sets contenant plusieurs pièces** : Dans la fenêtre Sets contenant une pièce, la pièce ouverte est déjà présente avec Toutes les couleurs. Ajouter une pièce… ouvre un catalogue avec recherche, filtres et miniatures ; Ctrl/Maj permet plusieurs choix sur la page. Choisir séparément une couleur ou Toutes les couleurs pour chaque ligne, puis Rechercher. Seuls les sets contenant toutes les pièces et couleurs demandées sont affichés. Une même référence peut être ajoutée deux fois pour demander deux couleurs. Retirer la sélection et Revenir à cette pièce modifient uniquement les critères, puis Rechercher actualise les résultats.

**Pièces des mini-figurines et sous-sets** : La recherche remonte maintenant de la pièce à la mini-figurine, puis au set, et traverse les sous-sets et coffrets. Elle utilise aussi les inventaires chargés par lots via API, respecte les versions et conserve les sources et références exactes. Pour 41850, les exports Rebrickable contrôlés passent de 1 résultat direct à 23 sets, coffrets inclus. Le nombre peut évoluer avec les données. Les inventaires doivent être présents localement ; télécharger/importer les exports complets pour une couverture complète, sans clé API.

**Choisir le stock utilisable** : Le vrac coché et les inventaires des sets cochés constituent deux sources indépendantes. Sets cochés uniquement décoche le vrac et conserve les choix individuels des sets. Un set sélectionné fournit ses composants même lorsque toutes les lignes de vrac sont décochées, sans démontage enregistré ni ajout au vrac. Les comptages personnalisés sont respectés ; les sets sans suivi utilisent leur inventaire local complet avec un avertissement. Les réservations des projets réduisent seulement le vrac. Le tableau affiche les photos des sets et les aperçus des pièces.

**Catalogue alternatif et commentaires** : Le clic droit sur un set propose Copier le set vers le catalogue alternatif… et Copier les pièces du set vers le catalogue alternatif…. La seconde commande copie aussi les références constituant son inventaire, leurs couleurs, quantités, supplémentaires et compositions locales des mini-figurines. Le commentaire facultatif, par exemple marque Lepin, reste modifiable dans Modifier la référence et apparaît dans la colonne Commentaire. Photos, métadonnées, rendus 3D et réglages personnels sont conservés, avec une origine explicite utilisable après renommage. Les anciennes copies identifiables sont réparées sans remplacer leurs visuels personnalisés. Une copie de catalogue ne déclare aucune possession.

**Alternatives dans les recherches et projets** : Autoriser les briques alternatives équivalentes est facultatif, désactivé au départ. Il permet de comparer les copies dont l’origine est connue aux besoins natifs dans les sets réalisables et les pistes de MOC. Dans Nouveau projet, la même option utilise les alternatives libres du vrac en conservant les références et couleurs physiques. Les pièces déjà réservées ne sont pas réutilisées. La création ne réserve rien ; les réservations restent explicites. Pour réserver les pièces d’un set possédé, transférer d’abord son inventaire dans le vrac.

**Vider le stock en une opération** : Vider Mon stock… et Vider Mon stock set… agissent sur toutes les pages et tous les filtres, après une confirmation affichant les quantités. Le vidage du vrac libère ses réservations et met les comptages connus des tiroirs à zéro ; les meubles, associations et quantités inconnues restent conservés. Le vidage des sets ne transfère aucune pièce dans le vrac. Une seule action Annuler/Rétablir restaure le tout, même après redémarrage. Une modification du stock pendant la confirmation bloque le vidage.

**Date et heure du dernier ajout** : Dans les deux catalogues de stock, Dernier ajout au stock apparaît après Référence, avec date et heure locales et tri par colonne. Cette date est distincte de la date d’import du catalogue général. Un ajout à une référence/couleur existante fusionne les quantités et actualise sa date ; Annuler restaure la quantité et la date précédentes. Supprimer une ligne retire sa quantité totale, et non uniquement le dernier ajout.


**Validation v0.1.61 :** 844 tests de la suite complète réussis sous Qt/Linux, puis 29 contrôles de rangement après le dernier ajustement. Interfaces contrôlées en formats normal et compact ; archives et lanceur Windows vérifiés par les outils de livraison. [Rapport détaillé](documentation/CONTROLE_v0.1.61.txt). Exécution native Windows à confirmer.

## Vrac direct et inventaires complets — v0.1.60

**Vrac uniquement en un clic** : dans Sets réalisables, le bouton Vrac uniquement réinclut toutes les pièces et mini-figurines du vrac, exclut tous les composants des sets possédés puis relance la recherche avec les critères actuels. Les inventaires de sets déjà transférés dans le vrac restent utilisables. Les réservations des projets sont respectées.

**Choisir le stock utilisable** : Utiliser uniquement le stock en vrac réinclut également les lignes masquées par le filtre et remet la recherche du tableau à vide. Valider avec OK enregistre ce choix ; Annuler conserve les préférences précédentes. Il est ensuite possible de décocher certaines références. Les choix individuels des sets sont conservés pour une réactivation ultérieure.

**Recherches MOC** : une fenêtre déjà ouverte relit la sélection actuelle du stock au prochain lancement de la recherche.

**Ajout d’un inventaire complet** : depuis la fiche d’un set, Ajouter toutes les pièces vérifie désormais que chaque référence existe dans le catalogue. Une erreur nomme les références absentes avant tout ajout. Si l’inventaire a changé depuis l’ouverture, rouvrir la fenêtre du set. L’ajout volontaire des seules pièces sélectionnées reste disponible.

**Validation v0.1.60 :** suite complète de 773 tests réussie sous Qt/Linux, puis 12 tests ciblés après le dernier ajustement ; quatre captures contrôlées en formats normal et compact. [Rapport détaillé](documentation/CONTROLE_v0.1.60.txt). Exécution native Windows à confirmer.

## Vrac uniquement transferts partiels et exclusions — v0.1.59

**Vrac uniquement** : Dans Sets réalisables → Choisir le stock utilisable, décocher Utiliser les pièces de Mon stock set exclut tous les composants des sets possédés, y compris ceux ajoutés plus tard. La recherche utilise seulement les pièces et mini-figurines en vrac, après les réservations des projets. Les détails, exports et suggestions MOC reprennent ce choix. Les exclusions individuelles des sets sont conservées pour une réactivation ultérieure.

**Transfert partiel par glisser-déposer** : Glisser une référence depuis le contenu d’un tiroir vers un autre ouvre Quantités à déplacer pour les comptages connus. Choisir par exemple 20 pièces sur 40 : 20 restent à l’origine et 20 sont déposées à destination. Une sélection de plusieurs références peut être réglée ligne par ligne ; la validation est atomique et annulable. Annuler le dialogue ne change aucun tiroir. Les références sans comptage sont déplacées entièrement, sans inventer de quantité.

**Ajouts au stock et meubles** : Après un ajout au vrac, une référence et une couleur entièrement comptées dans un seul tiroir suivent le nouveau total. Par exemple 40 pièces puis un ajout de 10 donnent 50 dans ce tiroir. Si plusieurs tiroirs partagent la référence, ou si le comptage est partiel ou inconnu, les comptages sont conservés et les nouvelles pièces restent à ranger. Les composants de sets possédés restent distincts du vrac. L’ajout et l’actualisation du tiroir s’annulent et se rétablissent ensemble. Le rangement et les inventaires ouverts s’actualisent ; un rangement masqué est relu à son ouverture.

**Quantité visible sur le meuble** : La façade affiche le nombre de pièces lorsque tous les comptages du tiroir sont connus. Le survol conserve le détail par référence et couleur ; zéro et quantité inconnue restent distincts.

**Exclure un mot de la recherche** : Dans la recherche normale et les filtres avancés, -modulex retire les références contenant modulex dans le nom, la référence ou la catégorie. brick -modulex -duplo combine un mot recherché et plusieurs exclusions. Les thèmes des sets suivent également ce filtre. Les recherches indexées et compatibles sont cohérentes ; les tirets internes des références, comme 75192-1, restent littéraux.

**Validation v0.1.59 :** 762 tests réussis sous Qt/Linux, dont 22 nouveaux ; dialogues et meuble contrôlés en formats normal et compact. [Rapport détaillé](documentation/CONTROLE_v0.1.59.txt). Exécution native Windows à confirmer.

## Projets, inventaire des tiroirs et corrections — v0.1.58

- **Sets réalisables** : bouton et clic droit **Créer un projet avec ce set…**. Le nombre d’exemplaires et l’option **Exclure les minifigurines** sont transmis au nouveau projet.
- **Mes projets** : la sélection affiche le set dans le volet droit ; un double-clic ou **Voir le set** ouvre sa fiche et son inventaire.
- **Choisir un set** : catalogue paginé avec miniatures, aperçu photo, recherche, filtres par thème, année et source, filtres avancés et filtres enregistrés. Le formulaire du projet montre aussi le set choisi.
- **Exclure les minifigurines** : calcul, pourcentages, détails et exports portent sur le modèle. Les figurines intactes en stock ne sont pas démontées pour ce calcul. Les anciens inventaires API sans distinction modèle/figurines demandent un rechargement par lots ; les CSV complets Rebrickable peuvent être utilisés directement.
- **Tiroirs** : le survol donne les références, les couleurs et les quantités de ce tiroir. Un double-clic ouvre **Inventaire du tiroir** pour ajouter, modifier ou retirer une référence, une couleur ou un comptage. Quantité inconnue et zéro restent distincts. Les limites du stock, les conflits de modification et Annuler/Rétablir sont pris en compte.
- **Import CSV Rebrickable** : prise en charge de **Set Number, Quantity, Inventory Ver**. La quantité d’exemplaires et la version d’inventaire sont respectées. Une version absente reste à vérifier ; aucune substitution silencieuse par la dernière version. Les corrections, la reprise et l’annulation restent disponibles.
- **Étiquettes** : **Appliquer à → Tout le catalogue Mini-figs** règle les mini-figurines de toutes les sources, leurs dispositions personnalisées existantes et les futures références. Les couleurs, les angles et les arêtes propres aux étiquettes sont conservés.
- **Stabilité** : les bulles d’aide observent uniquement les boutons construits, puis le nettoyage cyclique Python/Qt est exécuté dans le thread d’interface, uniquement après la fin des tâches natives. Les fenêtres sont détruites explicitement sur ce thread à la fermeture. Cette protection répond aux journaux de corruption de mémoire reçus en v0.1.57 ; sa confirmation sur Windows reste nécessaire.


## Quantités par tiroir, historique des actions et projets — v0.1.57

**Mon rangement → Contenu du tiroir** affiche désormais **Quantité dans ce tiroir**, distincte du **Stock global en vrac**. Sélectionner une référence puis **Quantité dans ce tiroir…** pour déclarer son nombre. La même référence et couleur peut être répartie entre plusieurs tiroirs : avec 100 pièces possédées, 30 dans un tiroir et 70 dans un autre, le stock total reste 100. **Transférer une quantité…** déplace une partie du comptage vers un autre tiroir ou meuble. Glisser une référence depuis un tiroir déplace aussi sa quantité déclarée et la fusionne avec celle de la destination.

Dans **Pièces à ranger**, la colonne **Restant à ranger** et la case **Quantités restant à ranger** prennent en compte les comptages déjà enregistrés. Depuis le stock, le glisser-déposer ou **Associer au tiroir sélectionné** place la quantité restante. Pour une répartition partielle, modifier ensuite le comptage du tiroir ou utiliser le transfert. Le rangement automatique propose la case **Répartir les quantités restantes** : vérifier les nombres dans **Meuble proposé → Contenu du tiroir**, puis appliquer. En réorganisation, les quantités déjà déclarées sont conservées. Les associations depuis les catalogues restent possibles sans posséder la pièce ; leur quantité est **À renseigner**.

La migration des rangements v0.1.56 conserve les meubles et associations avec une quantité **À renseigner**, jamais une copie automatique du stock dans chaque tiroir. Une quantité nulle reste distincte d’un comptage inconnu. Le total déclaré par référence, source et couleur ne peut pas dépasser le stock en vrac. Pour diminuer le stock sous une quantité rangée, réduire ou retirer d’abord les comptages concernés. Dans **Mon stock → Colonnes**, les champs **Répartie dans les tiroirs** et **Restant à ranger** permettent de suivre la répartition.

Le volet supérieur propose **Annuler la dernière action / Ctrl+Z**, **Rétablir / Ctrl+Y** et **Historique des actions**. Le journal conserve par défaut 100 actions et survit au redémarrage. La fenêtre liste leur date, leur description et leur état appliqué ou annulé ; **Actions conservées** règle la limite de 1 à 500. Les actions concernent le stock, la file d’étiquettes, les couleurs 3D générales et individuelles, les affectations et comptages des tiroirs, les propositions appliquées et les projets. Les imports et propositions groupés se restaurent en une opération atomique. Les actions s’annulent dans l’ordre inverse et se rétablissent dans l’ordre d’origine. Une nouvelle modification après annulation remplace la suite qui restait à rétablir ; une opération sans changement ou refusée la conserve. Une modification ultérieure incompatible bloque la restauration. La dernière action compatible de la v0.1.56 est reprise sans lui inventer de date.

**Mes projets** apparaît dans la navigation. **Nouveau projet…** propose un **Set du catalogue** ou une **Construction personnelle**. Depuis un catalogue de sets, le clic droit offre aussi **Créer un projet de construction…**. Pour un set, charger son inventaire local complet, choisir le nombre d’exemplaires et l’inclusion éventuelle des pièces supplémentaires. La création enregistre une copie des besoins, sans ajouter ni réserver de stock. Pour une construction personnelle, **Pièces du projet → Ajouter une pièce…** choisit une référence locale, sa couleur et sa quantité nécessaire. Ce menu permet aussi de modifier les besoins, retirer la sélection ou régler sa réservation.

Le tableau des projets affiche l’état **À préparer**, **En cours** ou **Terminé**, les besoins, les réservations et les manquants. Le détail affiche **Nécessaire**, **Réservée**, **Libre en stock** et **Manquante** pour chaque référence et couleur. **Réserver le stock disponible** affecte les pièces encore libres dans la limite des besoins ; **Réserver la sélection** ne traite que les lignes choisies. **Régler la réservation…** permet un nombre précis. Deux projets partagent le même stock libre : une pièce déjà réservée au premier n’est pas offerte au second. Les réservations portent uniquement sur le stock en vrac de la même source, référence et couleur, sans équivalence automatique ni prélèvement dans les composants suivis des sets.

Les réservations conservent la possession et les emplacements physiques. **Mon stock → Colonnes** propose **Réservée aux projets** et **Disponible pour construire** ; les recherches de sets réalisables retirent les réservations des pièces utilisables. Un projet **Terminé** garde ses réservations jusqu’à **Libérer les réservations**. Supprimer le projet les libère également. Pour réduire le stock ou un besoin sous la quantité réservée, libérer d’abord les réservations concernées. Un comptage dans un tiroir et une réservation de projet décrivent la même pièce sous deux angles : ils ne s’additionnent pas pour diminuer le stock.

**Sauvegardes → Projets et réservations** exporte une nouvelle famille JSON ; **Meubles et emplacements** inclut les quantités par tiroir. Restaurer aussi le vrac nécessaire, ou conserver un stock suffisant déjà présent. Une restauration incohérente est refusée entièrement. Les anciennes sauvegardes de rangement restent lisibles avec des quantités à renseigner. Une restauration sélective réinitialise le journal des actions ; la sauvegarde ZIP complète conserve la base et son historique. Ces fonctions utilisent les données locales et ne nécessitent aucune clé API.

## Historique : aperçu du rangement et annulation — v0.1.56

Dans **Mon rangement → Ranger par catégorie et taille en tenons**, choisir le mode **Par catégorie et taille**, **Une référence par tiroir** ou **Regroupement libre de références**. Le premier conserve le tri des plus petites tailles vers les plus grandes. Le deuxième réserve un tiroir à chaque référence : sources et variantes restent distinctes, les couleurs d’une même référence restent ensemble sauf avec **Séparer les couleurs**. En mode libre, sélectionner plusieurs lignes avec Ctrl ou Maj puis **Regrouper la sélection…** pour choisir leur tiroir commun ; les listes **Tiroir proposé** permettent aussi d’ajuster chaque affectation. Les modes par référence et libre incluent les pièces et mini-figurines sans dimensions connues ; aucune taille n’est inventée.

Le panneau **Meuble proposé** montre la façade du meuble et les contenus proposés avant enregistrement. Les tiroirs affectés sont verts ; les conflits sont rouges et bloquent l’application. Cliquer sur un tiroir sélectionne ses groupes, puis double-cliquer ouvre **Contenu du tiroir** avec références, catégories, couleurs, miniatures et quantités. Ces quantités sont le stock global en vrac, et non une répartition physique entre tiroirs ; une référence de catalogue non possédée affiche 0. Les tiroirs réservés ou mixtes restent visibles. Zoomer ou déplacer la séparation entre tableau et aperçu pour examiner le meuble. La colonne **Catégorie** est aussi ajoutée au contenu du tiroir dans la fenêtre principale.

La sélection de **Pièces à ranger** est capturée à l’ouverture de cette fenêtre ; sans sélection, elle utilise les références affichées. **Préparer une proposition** recalcule le brouillon. Les groupes sans place restent signalés et sans emplacement. **Fermer** abandonne la proposition ; seul **Appliquer le rangement proposé** écrit les associations. Si le stock ou le rangement change entre-temps, préparer une nouvelle proposition. Les quantités ne sont pas modifiées.

**Annuler la dernière action / Ctrl+Z** prend maintenant aussi en charge la couleur 3D générale, la couleur individuelle d’une référence, les associations aux tiroirs, les déplacements de références entre tiroirs, leur retrait et les propositions de rangement appliquées. Le journal conserve une seule dernière action et survit au redémarrage. L’annulation d’un rangement rétablit les contenus et les noms de tiroirs concernés, sans modifier le stock. Une nouvelle action sur le stock devient la dernière action ; une modification incompatible ultérieure bloque l’annulation au lieu d’écraser les données.

## Correction du plantage mémoire des tâches — v0.1.55

Cette version corrige la durée de vie des tâches en arrière-plan et de leurs signaux Qt. Les objets restent conservés jusqu’à la fin effective des travaux, puis leurs références et leurs signaux sont libérés dans le thread de l’interface. Les résultats et progressions reviennent explicitement dans ce thread ; les callbacks tardifs sont ignorés après fermeture. Le nettoyage couvre aussi les erreurs, l’annulation et la sortie du logiciel.

Le contrôle de la v0.1.54 a reproduit des destructions de signaux Qt dans les threads de travail pendant l’analyse BrickArchitect. Le correctif supprime ce défaut sans modifier le catalogue, le stock, les meubles ou les étiquettes. Le crash Windows exact reste à retester sur le PC concerné.

## Couleur d’origine et vue arrière des roues — v0.1.55

Dans le volet supérieur, **Couleur 3D → Valeurs par défaut** remet le jaune d’origine (`#f3d55b`) dans le sélecteur. **Appliquer** enregistre ce choix et actualise les aperçus ; **Annuler** conserve la couleur précédente. Les couleurs individuelles et les palettes restent prioritaires.

Le modèle **Vue principale et vue du dessous** montre désormais la face arrière des roues et pneus suivant leur axe, au lieu de leur tranche. Les redirections LDraw d’anciennes références conservent la rotation et le sens de leur axe. L’orientation habituelle du dessous des briques reste conservée, ainsi que les autres vues et les angles personnalisés de la vue principale. La correction est reprise dans l’aperçu et les exports PNG/PDF.

## Petits écrans et volet supérieur réglable — v0.1.54

La recherche des catalogues reste compacte. Recherche, catégories, colonnes, filtres avancés et **Masquer / Réafficher pièces décorées** sont réunis sur une seule ligne. Si la largeur manque, déplacer la barre de défilement horizontale sous ces commandes ; les filtres ne créent plus de rangées supplémentaires. Le bouton **Disposition de la sélection…** rejoint les actions sous le tableau. Les catégories se cochent ou se décochent directement dans leur menu, avec recherche et sélection de toutes les catégories. Aucun bandeau de catégories sélectionnées ne prend de place au-dessus du tableau. Le filtre de référence exacte reste visible séparément lorsqu’il est actif.

**Glisser la bordure horizontale sous les groupes de boutons supérieurs** vers le haut ou le bas pour réduire ou agrandir ce volet. Le choix est conservé au redémarrage et dans les sauvegardes des préférences. Quand le volet est réduit, sa barre de défilement verticale permet d’atteindre tous ses boutons. Les encadrés ont des marges plus petites et s’ajustent à leur contenu. La fenêtre s’ouvre à une taille adaptée à l’écran ; elle peut descendre à 800 × 480.

Pour exclure un groupe, ouvrir **Filtres avancés → Catégories**, cliquer **Sélectionner toutes les catégories**, rechercher par exemple **duplo**, puis **Décocher les résultats**. Seules les catégories trouvées sont retirées ; les autres choix sont conservés. **Cocher les résultats** fait l’inverse. Ces commandes sont aussi disponibles dans le menu de catégories du catalogue. Aucune catégorie cochée retire le filtre et affiche toutes les catégories.

Dans les catalogues de sets, le clic droit propose **Ajouter l’inventaire à Mon stock** pour ajouter les pièces et mini-figurines en vrac, ou **Ajouter le set à Mon stock set** pour posséder le set avec son inventaire suivi. Le bouton **Ajouter au stock…** propose les deux destinations. La sélection multiple est prise en charge ; les couleurs et quantités de l’inventaire sont conservées, les sous-sets sont développés et les pièces supplémentaires sont incluses. Un inventaire manquant ou incomplet interrompt l’ajout entier. Charger les inventaires avant l’ajout ; aucun téléchargement n’est déclenché par ces commandes. L’action s’annule avec Ctrl+Z.

Dans **Mon rangement → Pièces à ranger**, choisir **Meuble de destination**. Ce choix affiche le meuble pour le glisser-déposer et sert à **Rangement automatique…** ainsi qu’à **Ranger par catégorie et taille…**. Le rangement automatique utilise les lignes sélectionnées, ou les références affichées si aucune ligne n’est sélectionnée, depuis le stock ou le catalogue choisi. Il regroupe les catégories puis les tailles en tenons, de la plus petite à la plus grande, et propose les tiroirs depuis le haut, de gauche à droite. Ajuster puis appliquer la proposition ; elle crée des emplacements et conserve les quantités. Les dimensions inconnues, les groupes sans tiroir disponible et les tiroirs déjà utilisés restent signalés.

Un **clic droit sur un tiroir → Retirer une référence du tiroir** permet de choisir la pièce et sa couleur à retirer de cet emplacement. Les autres références, les associations aux autres tiroirs et le stock sont conservés. **Retirer toutes les références du tiroir…** demande confirmation. Pour un tiroir contenant plus de trente lignes, le menu donne aussi accès au tableau de son contenu.

## Bulles d’aide et fonctions API — v0.1.53

Laisser la souris sur un bouton pendant **deux secondes** pour afficher une brève explication. Quitter le bouton, cliquer ou fermer la fenêtre annule la bulle. Chaque nouveau bouton attend son propre délai de deux secondes. L’aide couvre les commandes des différentes fenêtres, les boutons standard, les cases à cocher et les contrôles créés ensuite ; les aides déjà définies sont conservées. Les explications suivent les changements de libellé et la langue FR / EN. Elles ne déclenchent aucune action et ne modifient pas les données. L’aperçu au survol des modèles d’étiquettes conserve son comportement immédiat.

La clé **Rebrickable** est nécessaire pour les accès suivants : actualisation de la photo et des correspondances externes d’une référence RB par API ; téléchargement des inventaires de sets RB par lots ; chargement des pièces d’une mini-figurine RB depuis l’API ; téléchargement des alternatives d’un set ; **MOC avec les pièces disponibles…** (alternatives des sets reconstituables avec le stock, sans vérification de l’inventaire propre au MOC) ; conversion automatique en ligne des références et couleurs BrickLink vers Rebrickable avec **Convertir BrickLink (API RB)** lors de l’export du stock.

Les **quatre identifiants BrickLink** (Consumer Key, Consumer Secret, Token, Token Secret) sont nécessaires pour ces accès : actualisation de la photo d’une référence BL et chargement de sa palette par API ; téléchargement des inventaires des sets et mini-figurines BL depuis l’API, y compris les sets par lots ; chargement par API des couleurs disponibles pour une référence avec **Charger via l’API BrickLink (facultatif)**.

Les fonctions d’import CSV / TXT, exports complets publics Rebrickable, recherche de MOC par mot-clé / créateur, notices publiques, LDraw, stock, rangement, édition et impression d’étiquettes restent disponibles sans ces clés. Le calcul des sets réalisables utilise les inventaires locaux et ne nécessite pas de clé lorsque les données nécessaires sont présentes. L’export CSV vers Rebrickable reste possible sans clé avec des références connues ou corrigées manuellement ; seule la conversion automatique par API exige la clé. Les recherches de photos restent accessibles sans API ; les clés peuvent apporter des photos et correspondances complémentaires. Les identifiants ne sont jamais affichés dans les nouvelles bulles.


## Modèles personnalisés, catégories et sélection — v0.1.52

Dans **Éditeur d’étiquettes → Modèles d’étiquette**, le menu propose les trois dispositions prédéfinies et les modèles enregistrés avec **Enregistrer un modèle…**. Survoler une ligne du menu affiche son étiquette à côté, sans changer le brouillon. Cliquer choisit le modèle ; déplacer ou redimensionner les calques, puis **Appliquer** pour enregistrer. **Supprimer ce modèle** retire le choix du menu et conserve les dispositions déjà appliquées. Les fichiers JSON restent disponibles avec Charger / Enregistrer sous.

**Appliquer à → Catégorie** associe le brouillon à la catégorie choisie, dans tous les catalogues et pour les nouvelles références de cette catégorie. Priorité : disposition individuelle, modèle de catégorie, modèle général. Les couleurs des catégories restent celles du réglage général. Le format physique suit la taille générale de la feuille ; les dispositions sont mises à l’échelle. **Suivre le modèle général** retire l’association de la catégorie.

Dans **Impression Étiquettes**, un catalogue de pièces, le stock ou l’historique, sélectionner plusieurs lignes avec Ctrl / Maj puis cliquer **Disposition de la sélection…**, aussi disponible au clic droit. Le brouillon commun reprend la première ligne sélectionnée. Choisir un modèle ou régler les calques librement, puis **Appliquer**. Les lignes sont capturées à l’ouverture, y compris sur plusieurs pages ; une sélection supprimée entre-temps interrompt l’application. Toutes les dispositions sont enregistrées ensemble. Les quantités, le stock, les couleurs, les angles et les arêtes individuelles restent conservés. Une sélection du catalogue règle les références ; une sélection dans Impression Étiquettes règle uniquement ces entrées et couleurs. Réinitialiser une disposition individuelle revient au modèle de sa catégorie, puis au général si aucun modèle de catégorie n’existe.

**Mise à jour des données → Mettre à jour LDraw (complete.zip)** télécharge la bibliothèque officielle depuis LDraw, vérifie le ZIP et construit les correspondances explicitement indiquées dans ses en-têtes. Un échec conserve la bibliothèque active. La précédente archive gérée dans Donnees est retirée après activation de la nouvelle si elle n’est pas référencée ailleurs. Le complete.zip fourni avec l’application et les fichiers externes sont conservés. L’import manuel de complete.zip reste disponible et conserve ses anciennes versions.

Les fichiers d’assemblage LDraw chargent récursivement leurs pièces, stickers, sous-pièces et primitives, en appliquant les positions et rotations inscrites dans les fichiers. Une pièce nue ne reçoit pas un sticker arbitraire. Les correspondances Rebrickable / BrickLink issues des en-têtes sont utilisées uniquement si elles sont explicites et uniques. Une dépendance absente ou un motif TEXMAP non pris en charge entraîne le recours à la photo. Exemple vérifié : **87552d02.dat**, officiel UPDATE 2026-09, charge **87552.dat** et **6177954b.dat**, avec la référence BrickLink **87552pb065R**. La bibliothèque officielle 2026-09 est fournie dans cette version. Les dispositions, modèles nommés et associations de catégories entrent dans les sauvegardes sélectives des modèles.


## Deux nouveaux modèles d’étiquettes — v0.1.51

Dans **Éditeur d’étiquettes → Modèles d’étiquette**, choisir **Vue principale centrée** pour une seule vue centrée, sans dessus ni côté. La catégorie et les dimensions en tenons sont placées dans le bandeau supérieur, et les références restent en bas. **Vue principale et vue de dessous** place la vue principale à gauche et une vraie vue du dessous à droite. Le modèle de base avec dessus et côté reste disponible.

Le choix modifie le brouillon : ajuster les calques si nécessaire puis **Appliquer** pour enregistrer. Les modèles sont aussi proposés dans **Disposition de cette étiquette**. Le format courant, les couleurs, la transparence et les réglages d’arêtes sont conservés. Les commandes **Annuler / Rétablir**, les modèles JSON et la sauvegarde sélective des modèles conservent la nouvelle disposition.

La vue de dessous est calculée depuis LDraw et conserve son orientation lors de la rotation de la vue principale. Son calque peut être ajouté, déplacé, redimensionné, recadré et zoomé. Une photo seule ne fournit pas de dessous : le logiciel le signale dans l’aperçu. Seules les vues demandées par le modèle sont calculées. PNG, PDF et impression utilisent la même disposition.




## Associer directement les catalogues aux tiroirs — v0.1.50

Dans un catalogue de pièces ou de mini-figs, sélectionner une ou plusieurs références puis cliquer **Associer à un tiroir…**, dans les boutons ou le menu du clic droit. Choisir le meuble et le tiroir, puis **Associer les références au tiroir**. Cette opération crée des liens de rangement sans ajouter les pièces au stock, sans demander de quantité et sans imposer de couleur. Elle permet de préparer un tiroir même pour une référence que l’on ne possède pas encore.

Dans **Mon rangement → Pièces à ranger**, le choix **Origine des pièces à ranger** donne accès au **Stock en vrac**, à **Tous les catalogues**, ou aux catalogues Rebrickable, BrickLink, BrickArchitect, Briques Alternatives et Mini-Figs. Rechercher ou filtrer, sélectionner des lignes, puis les glisser sur un tiroir. **Ajouter depuis un catalogue** ouvre aussi cette vue. La colonne de quantité est masquée en mode catalogue. **Sans emplacement uniquement** masque les références déjà associées ; décocher cette option pour les placer dans plusieurs tiroirs.

Le contenu des tiroirs reste déplaçable, recherchable, imprimable et sauvegardé même sans stock possédé. Les variantes et sources restent distinctes. La colonne de stock du contenu reste informative et ne crée aucune possession. Sans couleur imposée, elle montre le total possédé toutes couleurs confondues. Une catégorie déjà liée à ce meuble peut être réorganisée par taille en tenons même sans quantité en stock. L’onglet **Stock en vrac** garde sa validation des références et couleurs réellement possédées.

## Commandes espacées, exports libres et rangement assisté — v0.1.49

Les boutons supérieurs sont plus espacés, avec des marges dans leurs groupes. **Dossier PNG / PDF** accepte un dossier sur n’importe quel disque du PC ; ce choix est conservé au redémarrage. Un disque momentanément indisponible ne bloque pas l’ouverture du logiciel : une erreur d’écriture est indiquée lors de la génération.

Les réglages de noir et d’épaisseur des arêtes s’appliquent aux grands rendus, à l’aperçu de droite et aux étiquettes. Les miniatures des tableaux et des tiroirs conservent des arêtes fines, même après redémarrage ou un changement d’étiquette individuelle. Modifier seulement les arêtes ne relance pas les tableaux.

Dans **Mon rangement → Pièces à ranger**, rechercher et filtrer le stock, sélectionner plusieurs lignes avec Ctrl ou Maj, puis les glisser sur un tiroir dans la vue du meuble. Le tiroir cible est surligné. Les pièces déjà rangées sont masquées par défaut ; décocher **Sans emplacement uniquement** pour les afficher. Le bouton **Associer au tiroir sélectionné** offre aussi une commande au clavier. Depuis **Contenu du tiroir**, glisser une sélection vers un autre tiroir déplace uniquement ses liens de rangement. Les autres emplacements et toutes les quantités sont conservés.

**Ranger par catégorie et taille…** propose des tiroirs par catégorie puis par dimensions en tenons écrites dans les noms des pièces : par exemple 1 × 1, 1 × 2, 2 × 2, puis les plus grandes. Les dimensions en hauteur restent distinctes lorsqu’elles sont indiquées. Choisir **Bricks** / **Briques**, selon le catalogue, pour un meuble de 30 tiroirs ; chaque taille partage ses couleurs et ses variantes, avec l’option **Séparer les couleurs**. Les références restent distinctes. Ajuster les tiroirs dans le tableau avant **Appliquer le rangement proposé**.

La proposition utilise par défaut les pièces sans emplacement et les tiroirs vides sans nom. Elle montre les groupes qui manquent de place ; ils restent sans emplacement. Les pièces sans dimensions sont à ranger manuellement. **Réorganiser cette catégorie dans ce meuble** peut refaire ses associations dans les tiroirs contenant uniquement cette catégorie ; elle exige que tous les contenus existants trouvent une place. Les tiroirs mixtes et les autres meubles sont préservés. Si le stock ou le rangement change après la prévisualisation, préparer une nouvelle proposition. Les pièces physiques restent à déplacer selon le plan choisi.

## Assistant de correction des imports et boutons lisibles — v0.1.48

Dans **Mon stock** ou **Mon stock set → Importer une collection**, ouvrir une liste Rebrickable CSV ou BrickLink CSV / TXT / XML. Le logiciel enregistre un travail d’import dans **Donnees**, avec les lignes d’origine. **Ajouter les lignes prêtes** ajoute les références, couleurs et quantités valides ; les autres lignes restent en attente. Une référence inconnue, une quantité incorrecte, une couleur absente de la palette ou un inventaire de set incomplet ne bloque plus les lignes valides.

Sélectionner une ligne en attente, corriger **Source / type**, **Référence**, **Couleur** et **Quantité**, puis **Enregistrer la correction**. **Rechercher dans le catalogue…** permet de choisir une référence locale par nom, référence ou catégorie. Le changement de source demande un nouveau choix de couleur : les codes BrickLink et Rebrickable restent distincts. Les variantes ne sont pas assimilées automatiquement. Si l’inventaire d’un set est chargé entre-temps, utiliser **Revérifier les lignes**.

Fermer et rouvrir l’assistant, choisir le travail dans **Imports en attente…**, puis **Reprendre cet import**. Le fichier d’origine n’est plus nécessaire. Les lignes déjà ajoutées sont marquées et ne sont pas ajoutées une seconde fois ; les pièces corrigées plus tard rejoignent le même inventaire personnel. La destination est conservée après le premier ajout. Si seuls des sets ont été ajoutés, la destination des pièces en attente peut encore être choisie. Si l’inventaire de destination a été supprimé, choisir explicitement un autre inventaire ou en créer un nouveau ; les lignes déjà ajoutées ne sont pas réimportées. **Annuler la dernière action / Ctrl+Z** rétablit ensemble les quantités et les lignes en attente du dernier ajout. Les travaux sont inclus dans la sauvegarde complète de **Donnees**.

Le volet droit est plus large. Les actions longues sont réparties sur plusieurs rangées selon la largeur disponible ; les boutons de liens photo sont séparés. Les catalogues, notices, imports et meubles gardent un défilement sur les petites fenêtres pour atteindre toutes les commandes. Le bouton des notices Rebrickable affiche son texte sur plusieurs lignes si nécessaire. Les contrôles de rangement restent accessibles à **950 × 650** et **1366 × 768**.

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

Pour passer d’une version antérieure à v0.1.42, installer une fois le ZIP complet dans un nouveau dossier et y recopier **Donnees**, comme indiqué ci-dessous. L’option servira ensuite pour les futures releases publiées. La v0.1.50 est publiée sur GitHub, avec les ZIP complets et sources livrés et vérifiés.

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

La v0.1.50 est publiée sur GitHub, avec les ZIP complets et sources livrés et vérifiés.

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
- **Annuler / Rétablir / Historique des actions** restaure plusieurs actions de stock, file d’étiquettes, couleurs 3D, contenus et quantités des tiroirs, ou projets et réservations. Ctrl+Z annule ; Ctrl+Y rétablit. Le journal persiste après redémarrage et se réinitialise lors d’une restauration sélective. Une modification incompatible bloque la restauration.
- **Importer une collection** accepte les listes de pièces ou de sets Rebrickable CSV, et BrickLink CSV, TXT tabulé ou XML. Choisir la source et le stock de destination. Un set destiné au vrac est décomposé ; des pièces destinées au stock set s’attachent à un set existant ou à un inventaire personnel nommé. Les lignes valides sont ajoutées ; les références inconnues, couleurs ou quantités incorrectes et inventaires incomplets restent en attente dans l’assistant de correction. Enregistrer les corrections puis reprendre les lignes prêtes, même après fermeture.
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
| 0.1.48 | Imports partiels avec correction, sauvegarde et reprise, protection contre les doublons et annulation ; boutons et défilement adaptés aux petites fenêtres. |
| 0.1.49 | Commandes supérieures espacées, exports externes, miniatures à arêtes fines, glissement des pièces et rangement assisté par catégorie et taille. |
| 0.1.50 | Association directe de références des catalogues aux tiroirs, sans ajout au stock ni quantité ; choix des catalogues dans Pièces à ranger. |
| 0.1.51 | Modèles avec vue principale centrée ou vue principale et dessous ; calque de dessous LDraw et calcul des seules vues utilisées. |
| 0.1.52 | Modèles nommés avec aperçu, catégories et sélection ; mise à jour officielle LDraw. |
| 0.1.53 | Bulles d’aide après deux secondes et documentation des accès API. |
| 0.1.54 | Petits écrans, catégories, stocks de sets et meuble de destination pour le rangement. |
| 0.1.55 | Durée de vie des tâches Qt, couleur d’origine et face arrière des roues. |
| 0.1.56 | Aperçu des propositions, un tiroir par référence ou regroupement libre, colonne Catégorie et annulation des couleurs 3D et placements. |
| 0.1.58 | Projets et aperçus, inventaires des tiroirs, CSV versionnés, modèles Mini-figs et protection mémoire. |
| 0.1.57 | Quantités par tiroir et transferts partiels, historique Annuler/Rétablir persistant, projets avec besoins, réservations et manquants. |

Un seul [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) réunit les notes françaises et anglaises. Les notes de cette branche ne documentent pas de livraison 0.1.29. Les variantes 0.1.28b et Range n’ont pas servi de base. Le [rapport de contrôle v0.1.63](documentation/CONTROLE_v0.1.63.txt) décrit les vérifications de cette livraison.

## Développement et diagnostic

Installer Python 3.12, créer un environnement virtuel puis `python -m pip install -r app/requirements.txt`. Lancer `python app/bootstrap.py`. Tester avec `python tools/run_tests.py`. Sous Linux avec MinGW-w64 : `python tools/build_distribution.py chemin/BrickLabo_v0.1.43_Complet.zip dossier_de_sortie`. L’outil reprend les bibliothèques de l’archive complète précédente ; il accepte aussi l’ancienne organisation v0.1.36.

Diagnostic du paquet : `BrickLabo.exe --self-test` écrit `Donnees/diagnostic.json`. En console : `app/python.exe -B app/bootstrap.py --self-test`. Les tests sont réalisés sous Qt/Linux ; le lanceur compilé et la structure des archives sont inspectés ; l’exécution native Windows reste à vérifier sur un PC Windows.

Projet : https://github.com/sdu07git/BrickLabo. Ne pas publier Donnees ni les sauvegardes privées.

Contrôle après fabrication : `python tools/check_distribution.py chemin/BrickLabo`.

Pour publier une future mise à jour compatible : créer une release publique stable avec un tag `vX.Y.Z`, des notes de version et le fichier **BrickLabo_vX.Y.Z_Complet.zip** produit par cet outil. GitHub doit exposer le champ `digest` SHA-256 de cet asset dans son API. Les archives Sources générées automatiquement par GitHub ne sont pas installables. Le logiciel consulte au maximum les 100 releases les plus récentes et ne publie aucun fichier.

Pour développer depuis ce dépôt, reprendre `ressources/complete.zip` depuis le ZIP Sources joint à la release : cette archive LDraw dépasse la limite de taille des fichiers GitHub. Les archives automatiques « Source code » ne contiennent ni cette ressource ni le runtime Windows. Les deux ZIP joints sont ceux de la version livrée et testée ; les README du dépôt sont adaptés à la publication.

Le [rapport de contrôle v0.1.63](documentation/CONTROLE_v0.1.63.txt) décrit les vérifications de cette livraison. Exécution native Windows à confirmer.



**Validation v0.1.54 :** 617 tests couverts sous Qt/Linux, dont 153 tests des fonctions modifiées revérifiés avec succès. Lanceur Windows, icône, dépendances et ZIP contrôlés. Exécution native Windows à confirmer.


**Validation v0.1.55 :** 627 tests de stabilisation réussis sous Qt/Linux, puis 141 tests ciblés réussis après les ajouts couleur / roues, dont 11 nouveaux tests ; 800 tâches supplémentaires contrôlées dans huit processus. Les signaux sont détruits dans le thread GUI, sans objets résiduels après nettoyage. Lanceur, dépendances et ZIP contrôlés. Le crash Windows exact reste à retester sur le PC concerné.


**Validation v0.1.56 :** 657 tests de la suite complète réussis, puis 86 tests ciblés après l’ajout de l’annulation des couleurs individuelles et 49 après les derniers ajustements visuels et d’aide. Les 21 nouveaux tests couvrent les propositions, le regroupement, les miniatures, la colonne Catégorie et l’annulation persistante. Contrôle visuel à 1360 × 790 et 800 × 540. Lanceur Windows et intégrité des deux ZIP contrôlés ; exécution native Windows à confirmer.


**Validation v0.1.57 :** 695 tests réussis sous Qt/Linux (Python 3.12, PySide6 6.11.2), dont 36 nouveaux tests des comptages, transferts, projets, sauvegardes et historique persistant. Essai supplémentaire de 183 références dans 183 tiroirs avec réservation, redémarrage et Annuler/Rétablir. Contrôle visuel à 1360 × 790 et 800 × 540. La fabrication vérifie le lanceur Windows et les deux archives ; exécution native Windows à confirmer.

**Validation v0.1.58 :** 740 tests de la suite complète réussis sous Qt/Linux, dont 45 nouveaux tests. Contrôle des imports versionnés, projets, inventaires et modèles Mini-figs ; 120 rendus 3D et 120 parcours de fenêtres sans erreur. [Rapport détaillé](documentation/CONTROLE_v0.1.58.txt). Le plantage exact reste à confirmer sur Windows.
