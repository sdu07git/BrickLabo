# Documentation BrickLabo

## Vue d’ensemble

BrickLabo est un logiciel Python/Qt pour gérer un stock de briques LEGO, explorer plusieurs catalogues, trouver des sets réalisables et générer des étiquettes PDF/PNG.

## Arborescence cible

- `atelier/` : logique applicative du logiciel
- `tests/` : validations automatiques
- `scripts/` : lancement, maintenance et outils de développement
- `scripts/windows/` : lanceurs Windows de confort
- `packaging/` : scripts de build portable / exécutable
- `ressources/` : catalogues et fichiers de données livrés
- `docs/` : documentation du projet et du fonctionnement
- `main.py` : point d’entrée de compatibilité minimal

## Règle de conception

La racine du dépôt doit contenir uniquement les éléments essentiels au portage et à la distribution, tandis que les outils de maintenance et la documentation sont volontairement déplacés vers des dossiers dédiés.

## Workflow recommandé

```bash
python -m pip install -e .
bricklabo
```

Les scripts Windows legacy restent disponibles pour la compatibilité, mais le standard de développement du projet passe par `pyproject.toml` et `scripts/`.
