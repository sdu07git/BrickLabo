Version 0.1.36 — Catégories par tags, aperçus et tri

- Filtres avancés : sélectionner plusieurs catégories par cases à cocher.
  Les catégories choisies apparaissent comme des tags retirables avec ×.
  OU entre catégories ; ET avec le texte et les autres filtres.
  Exemple : (Briques OU Plaques) ET présentes dans Mon stock.
  Aucune catégorie sélectionnée = toutes les catégories.
  Les tags sont conservés dans les filtres enregistrés. Les anciens réglages
  à une catégorie restent utilisables. La liste simple du catalogue remplace
  les tags lorsqu’on choisit une catégorie depuis cette liste.
- Sets réalisables avec Mon stock : colonne Aperçu 3D / photo dans le tableau
  des pièces. Rendu 3D en priorité, photo si aucun rendu n’est disponible.
  Les miniatures chargent les lignes visibles et respectent la couleur associée.
  Les lignes absentes du catalogue signalent un aperçu indisponible.
- Tri croissant/décroissant par clic sur les en-têtes des résultats de sets,
  des pièces, des MOC et des constructions alternatives. Quantités et pourcentages
  sont triés numériquement. Les aperçus, doubles-clics et menus restent liés
  à la bonne référence après le tri.
- Les fenêtres de MOC affichent les photos des constructions. L’API ne fournit
  pas leurs inventaires détaillés : la colonne de pièces concerne les sets dont
  l’inventaire local est disponible.

Installation : fermer BrickLabo, extraire le ZIP complet dans un dossier neuf,
copier le dossier Donnees de la version précédente dans ce dossier, puis lancer
BrickLabo.exe. Conserver une sauvegarde de l’ancienne version.

Version 0.1.35 : clic droit sur un résultat de « Sets réalisables avec Mon stock »
puis « Voir les constructions alternatives ». La fenêtre affiche les constructions
du set choisi, via la clé API Rebrickable configurée. Le stock reste inchangé.

Version 0.1.34 : table locale des couleurs Rebrickable / BrickLink / LEGO / LDraw.
Choix par pièce pour les couleurs BrickLink 72 et 77. Voir COULEURS.txt.

v0.1.33 — Aperçu des pièces, exports et contours

Dans Sets réalisables avec Mon stock, double-cliquer sur une pièce du tableau inférieur ouvre son aperçu 3D ou sa photo selon les réglages existants. La couleur requise est utilisée lorsqu’elle peut être identifiée sans ambiguïté. Une couleur non imposée est signalée.

Deux boutons exportent le détail du set sélectionné en CSV : pièces manquantes et pièces en stock. L’export en stock indique le stock total et la quantité utilisable pour ce set, limitée à la quantité requise. Les fichiers précisent le set, le nombre d’exemplaires, la source et la référence des pièces, la source et le code couleur, les quantités requises, disponibles et manquantes. En mode couleurs ignorées, le code * est conservé et le mode est indiqué. Ces CSV sont des rapports BrickLabo, pas des fichiers d’import direct Rebrickable. L’export utilise le détail affiché ; relancer la recherche après une modification du stock.

Contours : seules les catégories présentes dans les catalogues de pièces sont proposées. Les thèmes des sets et catégories de mini-figures seules sont exclus.

Installation : extraire le ZIP complet dans un nouveau dossier. Fermer l’ancienne version et copier son dossier Donnees à côté du nouvel exe. Garder l’ancienne installation en sauvegarde.

## v0.1.32 — Recherche FTS5 et sets réalisables

La recherche indexée FTS5 et les filtres avancés de la v0.1.28b sont repris : sources, présence en stock, photo, impressions/stickers, années, dates d’import et couleur. Les critères se combinent avant pagination et peuvent être enregistrés. Le premier lancement construit l’index sur les données existantes ; patienter pendant cette opération. Les imports suivants actualisent automatiquement l’index. Si SQLite ne fournit pas FTS5 trigram, la recherche classique reste disponible.

Dans **Mon Stock → Sets réalisables avec Mon stock**, choisir la source, le pourcentage minimum de pièces possédées (100 % par défaut), le nombre d’exemplaires et le respect ou non des couleurs. Le tableau indique les quantités requises et manquantes. Sélectionner un set affiche ses pièces ; un double-clic ouvre sa fiche.

Le calcul utilise les inventaires locaux disponibles. Importer les inventaires Rebrickable ou BrickLink et compléter les compositions des mini-figures si nécessaire. Un inventaire absent, incomplet ou de couleur inconnue est exclu du calcul exact. Les correspondances BrickLink enregistrées par la conversion de l’export Rebrickable sont réutilisées ; les correspondances ambiguës ne sont pas devinées. Chaque résultat est évalué séparément : les sets proposés ne sont pas nécessairement réalisables simultanément. Le stock n’est ni réservé ni retiré.

L’organisation d’origine et les fonctions des versions 0.1.30 et 0.1.31 sont conservées. Installation : extraire dans un nouveau dossier, fermer l’ancienne version, puis copier son dossier Donnees à côté du nouvel exécutable. Conserver l’ancienne installation comme sauvegarde.

# BrickLabo by SDU7 — v0.1.31

## v0.1.31 — export du stock vers Rebrickable

Dans **Mon Stock**, le bouton **Exporter tout mon stock vers Rebrickable** ouvre une fenêtre de contrôle avec deux onglets. L’export porte sur tout le stock, indépendamment de la page, des filtres et des lignes sélectionnées.

Deux listes sont produites :
- **stock_sets.csv** : sets possédés, avec référence Rebrickable et quantité. Importer dans **My LEGO → My Set Lists**, dans une liste dédiée.
- **stock_pieces.csv** : pièces en vrac, avec référence, code couleur Rebrickable et quantité. Importer dans **My LEGO → My Parts Lists**, dans une liste dédiée, au format Rebrickable CSV.

Activer les deux listes dans les calculs de construction sur le site. Ne pas compter une autre copie des mêmes sets/pièces déjà présente sur votre compte. Pour une actualisation, remplacer le contenu des listes dédiées au lieu d’ajouter une nouvelle fois tout le stock. BrickLabo ne transmet rien automatiquement à votre compte.

Les pièces suivies comme appartenant aux sets sont soustraites de la liste des pièces pour éviter les doublons. Les quantités restantes constituent le vrac. Les mini-figs restantes sont décomposées si leur inventaire est disponible ; sinon elles sont signalées, sans être inventées ni assimilées à une pièce ordinaire. Si le suivi historique d’un set manque, ou si l’inventaire/stock a été modifié, l’export demande de vérifier les incohérences.

**Pièces BrickLink :** cliquer sur **Convertir BrickLink (API RB)** avec votre clé Rebrickable configurée. Le service officiel recherche les correspondances des références via bricklink_id et celles des couleurs via external_ids. Elles sont conservées localement pour les exports suivants. Un numéro de couleur BrickLink n’est jamais supposé égal au numéro Rebrickable. Une correspondance multiple reste à choisir : survoler la cellule pour voir les propositions puis saisir la référence/couleur voulue.

Les colonnes Réf. RB et Couleur RB peuvent être corrigées dans la fenêtre ; ces corrections ne changent pas le stock. Les autres colonnes sont en lecture seule. Les références sans équivalent, les couleurs non renseignées et les mini-figs sans inventaire bloquent par défaut l’export. Un export partiel doit être autorisé explicitement ; le fichier **stock_rapport.txt** décrit les exclusions et points à vérifier. Si un set est exclu, ses pièces suivies restent exclues de la liste de vrac : corriger le set puis refaire un export complet.

L’organisation des dossiers reste celle de la v0.1.28 d’origine. Les fonctions de la v0.1.30 (alternatives de sets, caches courts et exports protégés) sont conservées.

Installation : extraire le ZIP complet dans un nouveau dossier, fermer l’ancienne version et copier Donnees à côté du nouvel exe. Conserver l’ancienne installation.

Validation : six tests dédiés (non-double-comptage, couleurs BrickLink différentes, correspondances multiples, mini-figs, stock modifié, génération des deux CSV). Fenêtre inspectée sous Qt/Linux. Connexion réelle avec votre clé et import dans votre compte Rebrickable non effectués ici.

## v0.1.30 — basée exclusivement sur la v0.1.28 d’origine

- Organisation des dossiers conservée : aucune réorganisation App, aucun ajout Poetry.
- Clic droit sur un set → **Voir les constructions alternatives** : fenêtre séparée avec liste Rebrickable, créateurs, nombre de pièces, aperçu photo et accès à la page des notices. Clé API Rebrickable et Internet nécessaires. Charger la suite pour les résultats paginés. La référence peut être corrigée dans la fenêtre ; une référence BrickLink uniquement numérique est proposée avec le suffixe -1, à vérifier sur Rebrickable.
- Cette recherche concerne les constructions alternatives du set choisi. Elle ne compare pas le stock complet, ne télécharge pas automatiquement de notices payantes et ne modifie pas les inventaires.
- Noms des nouvelles miniatures et images téléchargées raccourcis : empreinte SHA-256 complète encodée sur 43 caractères au lieu de 64. Les images déjà téléchargées restent réutilisables. Les miniatures anciennes sont recalculées à la demande ; leur nettoyage reste disponible depuis le logiciel.
- Temporaires d’écriture courts et uniques : 13 caractères, indépendants du nom final. Exports PNG/PDF validés par remplacement après écriture complète. En cas d’échec : message, nettoyage du temporaire et aucun faux ajout à l’historique. Les fichiers déjà terminés d’un lot restent disponibles et leur nombre est indiqué.
- Si une miniature ne peut pas être enregistrée, son aperçu reste en mémoire et l’erreur est consignée dans les logs.
- Ceci augmente la marge de longueur, sans garantir les chemins de longueur illimitée ni modifier les réglages Windows.

**Installation :** extraire entièrement dans un nouveau dossier. Fermer l’ancienne version, copier son dossier **Donnees** à côté du nouvel **BrickLabo.exe**, puis lancer. Conserver l’ancienne installation comme sauvegarde. Ne rien prendre dans v0.1.28_Range.

**Validation :** tests locaux des caches, sauvegardes, notices et espace disque ; tests API simulés (pagination, erreurs, fermeture de fenêtre) ; exports PNG/PDF réels et simulation d’erreur de chemin. Interface vérifiée sous Qt/Linux. Connexion réelle avec une clé Rebrickable et exécution sur Windows à vérifier sur votre PC.

[English](README.en.md) · [Aide complète](AIDE.html) · [Sources et licences](SOURCES_ET_LICENCES.html)

Logiciel Windows portable de catalogues LEGO, stock, création d’étiquettes PDF/PNG et impression. Python, PySide6/Qt, SQLite et rendus LDraw, avec photos Rebrickable/BrickLink si disponibles.

Extraire intégralement le ZIP Windows Portable dans un chemin court et accessible en écriture, puis lancer **BrickLabo.exe**. Python n’est pas à installer séparément. Conserver tous les fichiers et dossiers fournis.

Pour une mise à jour : fermer BrickLabo, extraire dans un nouveau dossier et copier **Donnees** à côté du nouvel exécutable. Garder l’ancienne installation pour revenir en arrière. Le lanceur et la structure de la v0.1.21 sont conservés.

## Français / English

Le bouton **Langue** propose Français et English. Enregistrer, fermer et relancer BrickLabo pour appliquer le choix à toutes les fenêtres. La préférence est dans Donnees/atelier.sqlite. Le français reste la langue par défaut.

L’interface, les menus, sous-menus, clics droits, infobulles et messages sont traduits. Les noms, catégories, références et couleurs importés des bases ne changent pas, ni les textes personnels des étiquettes. Les fenêtres natives de fichiers et d’impression suivent la langue de Windows.

L’aide, le README, les sources/licences et les nouveautés disposent d’une version anglaise avec un nom fixe. Les licences originales des ressources tierces sont conservées telles quelles.

## Fonctions et données

Catalogues Rebrickable, BrickLink, BrickArchitect, mini-figures, pièces et sets alternatifs ; stock, étiquettes et historique. Recherche, filtres par catégorie et année, tri global avant pagination, colonnes masquables et déplaçables. Fenêtres pièces/sets, boîtes originales, photos et notices PDF. Éditeur par calques, texte libre, disposition individuelle, caméra et arêtes 3D avec préréglages. Aperçu avant impression et sélection d’imprimante.

La version portable complète inclut les ressources de bases fournies. Le ZIP Sources contient le code, les tests, la documentation et les ressources complémentaires ; les grandes bibliothèques se trouvent dans le paquet complet ou s’importent depuis vos exports.

## Inventaires BrickLink et sauvegardes

Sélectionner un set BrickLink puis **Ajouter l’inventaire depuis un fichier TXT**. Les références, couleurs, quantités et indicateurs sont enregistrés dans SQLite ; le TXT peut ensuite être supprimé. Les pièces supplémentaires sont incluses ; variantes et équivalents sont conservés mais exclus des ajouts automatiques. Réimporter remplace l’inventaire sans modifier le stock existant. Aucun accès API requis.

**Sauvegardes** crée un ZIP privé et vérifié de Donnees, avec stock, inventaires, réglages, clés API, images et notices. Caches, logs, téléchargements de bases et temporaires sont exclus. Les fichiers extérieurs à Donnees ne sont pas copiés. Garder ces sauvegardes privées et choisir un dossier extérieur à Donnees.

La restauration s’applique au prochain démarrage ; l’état précédent est conservé dans Donnees_avant_restauration_… . Une restauration prévue peut être annulée avant le redémarrage.

## Dossiers, logs et sources

Les données personnelles sont dans **Donnees à côté du .exe**, sans repli dans AppData. **ressources** conserve les ressources fournies. Le dossier PNG/PDF est celui choisi dans le logiciel.

**Logs** ou OUVRIR_LOGS.bat ouvre les diagnostics texte. **Espace disque** mesure les dossiers et propose des nettoyages ciblés, sans nettoyer le Temp global de Windows. Double-cliquer sur une ligne ouvre son dossier.

Pour les sources sous Windows : installer Python 3.12, lancer INSTALLER_DEPENDANCES.bat puis DEMARRER.bat. CONSTRUIRE_EXE.bat construit le dossier PyInstaller. Les messages des scripts sont bilingues. Pour le développement : installer requirements.txt dans un environnement virtuel puis lancer `python main.py`.

Projet : https://github.com/sdu07git/BrickLabo. Ne pas publier Donnees ni les sauvegardes privées.
