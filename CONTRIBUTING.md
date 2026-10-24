# Contribuer à BrickLabo

Python 3.12, puis `python -m pip install -r app/requirements.txt`.
Les dépendances sont fixées sur celles du runtime Windows distribué.

## Un seul journal, pour les prochaines versions aussi

Ajouter les nouveautés en français et anglais en tête de
`documentation/NOUVEAUTES.txt`, avec `## Version X.Y.Z`. Les résultats vérifiés
et les limites de validation appartiennent à la même entrée. Ne plus créer de
rapports CONTROLE ni de fichiers TXT de nouveautés par version.

`python tools/release_notes.py --version X.Y.Z --add --fr chemin/fr.md --en chemin/en.md`
ajoute une entrée sans effacer l'historique et refuse un doublon. Les brouillons
restent hors du dépôt. Sans `--add`, la commande extrait l'entrée à publier.

## Validation

`python tools/prepare_validation.py --output ../validation` récupère une
distribution précédente publique dont le SHA-256 est fixé, puis LDraw.

`python tools/check_release.py` vérifie versions, journal unique et documents.

`python tools/run_tests.py --report ../validation/tests.json --junit ../validation/tests.xml`
exécute la suite complète avec le garde-fou Qt. Les rapports restent hors du dépôt.
Le banc ferme les connexions SQLite et archives appartenant aux collections de
test avant le retrait explicite de leurs dossiers temporaires. Windows refuse
normalement d'effacer un fichier encore ouvert. Les ressources extérieures au
dossier nettoyé restent ouvertes et les erreurs de suppression restent visibles.

`python tools/qualify_release.py --output ../validation/qualification --duration 120`
contrôle les vrais inventaires, les sauvegardes et les rendus. Une session longue
peut employer `--duration 14400`. Les captures proviennent de données fictives.
La matrice GitHub Actions conserve séparément les résultats Linux et Windows, en quatre lots déterministes par plateforme. `--shard 0/4` sélectionne un lot ; sans cette option la suite complète reste exécutée dans un seul processus. Le contrôle de couverture refuse les lots manquants, doublons, recensements différents ou résultats en échec avant de déclarer la suite complète réussie.

Une distribution 1.0 exige `python tools/check_release.py --for-final --evidence PATH`.
Les essais physiques et autorisations externes restent ouverts tant qu'aucune
preuve n'est enregistrée. Une exécution automatisée ne remplace pas l'essai sur
le PC où le crash s'était produit. Les droits du code et des ressources sont
distincts ; voir `licences/RESOURCE_RIGHTS.json`.
