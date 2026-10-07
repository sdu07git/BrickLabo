# Scripts du projet

Ce dossier centralise les outils de lancement, maintenance et utilisation locale du projet.

## Points d’entrée recommandés

```bash
python -m pip install -e .
bricklabo
```

```bash
python -m pip install -r requirements.txt
python scripts/run_dev.py
```

## Organisation

- `scripts/run_dev.py` : point d’entrée principal pour le développement local
- `scripts/windows/` : lanceurs Windows de compatibilité et maintenance
- `packaging/` : scripts de build, packaging et exécution portable
- `main.py` : point d’entrée minimal de compatibilité pour les anciens lancements
- les fichiers `.bat` à la racine restent seulement pour compatibilité avec les utilisateurs de la version portable

## Règles de structure

- Le code applicatif est dans `atelier/`.
- Les outils de démarrage et d’assistance sont dans `scripts/`.
- Les scripts de build sont séparés de l’application.
- La racine du dépôt reste épurée et accueille uniquement les éléments de compatibilité et de distribution.
- Les ressources runtime (`Donnees/`, `Exports/`, caches, logs, données utilisateur) ne sont pas traitées comme du code source.
