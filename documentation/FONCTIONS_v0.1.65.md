# Les six ajouts de collection — v0.1.65

Le bouton **Outils de collection**, dans **Données et réglages**, donne accès aux inventaires guidés, aux comparaisons de reconstructions, aux lots et à l’assistant. Les menus restent accessibles quand le volet supérieur est réduit.

## 2. Reprendre une proposition de rangement

Dans **Mon rangement → Ranger par catégorie et taille**, préparer la proposition puis choisir **Enregistrer un brouillon…** et lui donner un nom. Le brouillon conserve les critères, l’ordre des catégories, le nombre de tiroirs, les répartitions, les regroupements manuels et les destinations choisies dans le tableau ou par glisser-déposer.

**Reprendre un brouillon…** fonctionne après fermeture et redémarrage. Si le stock ou le rangement a changé, choisir explicitement le recalcul pour reprendre les réglages avec les données actuelles. Les destinations encore disponibles sont conservées autant que possible ; vérifier les quantités et l’aperçu avant application. Une référence disparue ou un meuble supprimé bloque la reprise. Charger un brouillon ne range aucune pièce : seul **Appliquer le rangement proposé** enregistre les changements, en une action annulable.

## 3. Inventaire guidé d’un set ou d’un meuble

Ouvrir **Outils de collection → Inventaire guidé…**, puis **Compter un set…**, **Compter le meuble sélectionné**, ou **Reprendre un comptage…**. Un accès direct existe dans **Mon rangement → Organiser le meuble → Inventaire guidé du meuble…**.

Le tableau affiche référence, couleur, adresse du tiroir, quantité attendue, comptée, manquante et en surplus. Les aperçus utilisent les mêmes images ou rendus que les catalogues. **Non compté** est différent de **0**. Une quantité de tiroir inconnue apparaît avec **?** : elle peut être comptée mais ne produit pas de déficit artificiel. Pour un set, les besoins proviennent de son inventaire local, sans les pièces de rechange.

Les filtres isolent les lignes à compter, les manquants ou les surplus. Les observations sont enregistrées automatiquement après une courte pause de saisie ; **Enregistrer le comptage** force la sauvegarde. **Exporter le comptage…** crée un CSV. Les comptages sont des observations séparées : ils ne corrigent pas automatiquement le stock ou les tiroirs. Un comptage conserve les quantités attendues à sa création ; démarrer un nouveau comptage pour contrôler un inventaire modifié.

## 4. Comparer plusieurs reconstructions

Ouvrir **Comparer plusieurs reconstructions…**, dans Outils de collection ou **Sets réalisables**. Ajouter jusqu’à **16 références de sets**, avec leur nombre d’exemplaires. Chaque ligne est un groupe indivisible : tous ses exemplaires doivent pouvoir être construits.

La comparaison recherche exactement, parmi ces lignes choisies, la combinaison réalisable avec le plus d’exemplaires ; à égalité, elle privilégie le plus de références différentes, puis l’ordre d’ajout. Chaque pièce disponible est utilisée au plus une fois. Les réservations des projets existants sont déduites. Le choix **Choisir le stock utilisable…** permet de retenir du vrac, des inventaires de sets à démonter, ou les deux, sans déplacer ces inventaires dans le vrac. Les options couleurs, minifigurines et équivalences alternatives sont disponibles.

Le résultat distingue les sets retenus et les sets non retenus avec leur manque calculé sur le stock restant après la combinaison proposée. Le stock reste inchangé. Les inventaires locaux complets sont nécessaires. Ce n’est pas une recherche exhaustive de toutes les combinaisons de tout le catalogue LEGO : elle porte sur la sélection de 16 références maximum.

**Créer les projets retenus…** crée les besoins en une opération annulable, sans réserver ni déplacer de pièces. Cette création demande une comparaison respectant les couleurs. Un stock modifié invalide le résultat et impose une nouvelle comparaison.

## 5. Lots d’achat et d’import

Dans **Lots d’achat et d’import…**, créer un lot avec **nom, provenance, prix en euros et commentaire**. **Ajouter au lot…** choisit une référence, une couleur et une quantité. Une pièce va dans le vrac ; un set va dans Mon stock set, avec son inventaire suivi. Les références conservent leurs informations du catalogue.

Chaque nouvel import réalisé par l’assistant de collection crée automatiquement un lot, nommé d’après le fichier. Les reprises d’un même import cumulent les contributions dans son lot actif sans importer deux fois les lignes déjà validées. Les ajouts historiques antérieurs à cette version ne sont pas reconstitués.

**Corriger la quantité du lot…** corrige une contribution sélectionnée, sans toucher aux autres lots. Pour un set, les composants suivent le nombre d’exemplaires quand l’inventaire représente des exemplaires complets. Un inventaire attaché ou non divisible doit être annulé puis réimporté après correction.

**Annuler les apports du lot…** retire seulement les quantités suivies de ce lot. Si le stock restant ne suffit plus à couvrir les tiroirs ou les réservations, l’opération est refusée entièrement ; corriger d’abord les répartitions ou libérer les réservations. L’historique conserve le lot marqué annulé. Les corrections et annulations de quantités sont annulables avec le bouton général. Le prix et les commentaires restent des informations de gestion : ils ne valorisent pas automatiquement chaque pièce.

## 6. Prélever les pièces d’un projet

Dans **Mes projets**, sélectionner un projet puis **Liste de prélèvement…**. L’onglet **À prélever** montre meuble, tiroir, référence, couleur et quantité à prendre. Les besoins peuvent être répartis sur plusieurs tiroirs. Les lignes sans emplacement compté sont signalées ; renseigner le rangement avant de les prélever dans cette fenêtre.

**Prélever la ligne…** demande la quantité réellement prise. La quantité du tiroir diminue ; une réservation protège les pièces du projet. Le stock possédé ne diminue pas : les pièces sont désormais suivies comme prélevées pour ce projet. Les mêmes unités ne peuvent pas être à la fois comptées dans un tiroir et prélevées. Un autre projet ne peut pas les réserver. L’onglet **Déjà prélevées** conserve le détail, même après préparation complète. **Exporter la liste…** exporte adresses et quantités en CSV.

**Retourner tous les prélèvements** demande de confirmer le retour physique, puis remet les quantités dans leurs tiroirs d’origine. La réservation du projet reste en place : la libérer ensuite si nécessaire. Il faut retourner les prélèvements avant de supprimer le projet, de supprimer un tiroir d’origine, de libérer les quantités concernées ou de vider Mon stock. Prélèvements et retours sont annulables ; l’annulation doit correspondre au mouvement physique réellement effectué.

## 7. Assistant de démarrage

L’assistant présente quatre étapes : **catalogues**, **LDraw**, **stock**, **meubles**. Les boutons ouvrent les fenêtres existantes pour effectuer l’action. Il apparaît au premier démarrage d’une collection vide, après l’import automatique des ressources fourni si celui-ci a lieu. Il reste disponible dans **Outils de collection → Assistant de démarrage…**. **Reprendre plus tard** ferme l’assistant ; **Terminer** mémorise sa fin. Il ne télécharge et n’importe rien sans action de l’utilisateur, hors import automatique déjà présent des ressources fournies.

## Aligner les meubles

Dans **Mon rangement → Organiser le meuble → Aligner les meubles…**, choisir **Horizontalement** ou **Verticalement**, puis l’écart entre les meubles, exprimé en unités de tiroir standard. Tous les meubles sont alignés dans leur ordre actuel de lecture, depuis la position du premier. Les formats, tiroirs, références et quantités restent inchangés. L’alignement est annulable en une action. Une modification concurrente des meubles demande de rouvrir le réglage.

La vue des meubles est désormais toujours de face : le contrôle d’angle et la vue inclinée ne sont plus affichés. Les réglages de vues des pièces et des étiquettes ne sont pas concernés.

## Conservation des données

Toutes ces données sont locales et persistent dans la base BrickLabo. La sauvegarde complète comprend les brouillons, comptages, lots et prélèvements. Les exports sélectifs existants gardent leur périmètre : utiliser une sauvegarde complète pour transférer aussi les nouveaux suivis. Aucun service de reconnaissance de référence par photo n’est ajouté dans cette version.
