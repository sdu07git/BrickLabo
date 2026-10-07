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

- `scripts/run_dev.py` : point d’entrée principal du développement
- `scripts/windows/` : lanceurs Windows de compatibilité et de maintenance
- `packaging/` : scripts de build autonome et exécutable
- les fichiers `.bat` racine restent présents uniquement pour compatibilité avec les utilisateurs portables

## Règle de structure

Le flux de développement standard passe par `pyproject.toml` et `scripts/` ; la racine du dépôt reste propre et ne contient que les fichiers de compatibilité et les actifs de distribution.
