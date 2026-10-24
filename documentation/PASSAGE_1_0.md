# Qualification avant la version 1.0

La v0.1.73 prépare cette qualification. Elle ne transforme pas un contrôle Linux
en essai Windows et ne marque pas une impression physique comme réussie à partir
d'un PDF. Le bilan vérifié de chaque livraison se trouve dans le seul
[journal des nouveautés et contrôles](NOUVEAUTES.txt).

| Point | Méthode et preuve attendue |
|---|---|
| Suite complète finale | `tools/run_tests.py` : JSON et JUnit, zéro erreur, arrêt propre Qt, version et OS enregistrés. Matrice Linux/Windows dans Actions. |
| Vrais inventaires | `tools/qualify_release.py` : 10696-1, 10698-1 et 30363-1, inventaires imbriqués inclus, disponibilité du set possédé, vrac, couleurs, réservations et sauvegarde/restauration. |
| Rendus 3D | Session automatisée avec angles renouvelés ; possibilité de quatre heures avec `--duration 14400`. Compléter par une session longue sur le PC où le crash avait été observé. |
| Portable Windows et mise à jour | `tools/verify_portable.py` lance réellement les anciens/nouveaux exécutables et applique une mise à jour à une installation jetable, avec conservation d'un témoin de données. Aucun stock personnel employé. |
| Petits écrans et langues | Captures réelles à 1366 × 768 et 800 × 600, revue française/anglaise, commandes accessibles par défilement. |
| Sauvegarde et restauration | Base SQLite et données cohérentes dans un ZIP vérifié, modification puis restauration dans une collection jetable ; essai supplémentaire de votre propre sauvegarde dans une copie séparée. |
| Étiquettes | PDF A4 et image générés par le moteur réel, 65 × 23 mm. Impression à 100 % à mesurer physiquement sur l'imprimante utilisée. |
| Meubles A4 | Aperçu et PDF du meuble de démonstration ; vérifier physiquement lisibilité, marges, portrait/paysage et disposition sur votre imprimante. |
| Code original | Licence MIT à la racine du dépôt et dans licences/BrickLabo. |
| Contenus externes | `licences/RESOURCE_RIGHTS.json` indique fichiers, empreintes, sources et droits vérifiés ou encore ouverts. Les permissions Rebrickable/BrickLink/Brick Architect et la conformité du runtime portable restent à documenter avant 1.0. |

Le contrôle `python tools/check_release.py --for-final --evidence fichier.json`
refuse une version finale sans preuves de tous les essais et sans résolution
des points de redistribution. Le format d'exemple est
[QUALIFICATION_1_0.json](QUALIFICATION_1_0.json). Ne passer une case à `passed: true`
qu'avec une preuve datée et un lien ou rapport correspondant à la version testée.
Une autorisation inexistante ne peut pas être remplacée par une attribution.

Les rapports JSON/XML d'Actions et les captures de données fictives peuvent être
partagés. Ne jamais publier les bases, sauvegardes et journaux personnels ou clés
API. Aucun message de demande de permission n'est envoyé automatiquement.

## English

Version 0.1.73 prepares, rather than claims, final qualification. The CI matrix
records full-suite Linux/Windows results. Real reference inventories, exclusive
reservations, backup/restore, refreshed 3D angles and small-screen captures use
disposable collections. Native portable validation launches the actual Windows
executables and upgrades a disposable previous installation while preserving a
data marker. These checks do not replace extended testing on the affected PC or
physical 65 × 23 mm/A4 printing. Original code is MIT; external resources retain
their own terms and unresolved permissions remain explicit in RESOURCE_RIGHTS.json.
The final-release gate requires version-specific evidence and resolved rights.
