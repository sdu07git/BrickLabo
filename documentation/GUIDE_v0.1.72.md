# BrickLabo v0.1.72

## Fluidité et inventaires en arrière-plan — v0.1.72

Les requêtes des catalogues, filtres, stocks, projets et meubles réutilisent les résultats encore valides et évitent des recherches répétées par pièce. Les onglets masqués sont actualisés lorsqu’on les ouvre. Les comptages tiennent toujours compte des réservations et des sets affectés ; Annuler/Rétablir et les imports invalident les résultats concernés. Le premier démarrage construit une fois les nouveaux index et données de recherche.

Mesures sur la même collection de contrôle : **253 628 entrées de catalogue, 1 558 072 lignes d’inventaire, 10 000 lignes de stock, 100 projets et 10 000 tiroirs**. Premier appel de chaque scénario, sous Linux, avec le même environnement Python ; ce ne sont pas des mesures promises pour tous les PC Windows.

| Opération | v0.1.71 | v0.1.72 |
|---|---:|---:|
| Catalogue : première page | 60 ms | 6 ms |
| Catalogue : page 50 | 132 ms | 6 ms |
| Masquer les pièces décorées | 2 033 ms | 54 ms |
| Rechercher une pièce du catalogue à ranger | 1 830 ms | 66 ms |
| Rechercher dans le vrac à ranger | 79 ms | 12 ms |
| Lire le contenu des meubles | 100 ms | 40 ms |
| Rechercher des sets sur tout le catalogue Rebrickable | 7,41 s | 4,93 s |

Une requête identique de catalogue déjà en cache prend environ 1 ms sur ce banc. Le rafraîchissement général avec Mon stock visible passe d’une médiane de 165 à 9 ms, sans téléchargement ni rendu d’images dans cette mesure d’interface. Les **18 scénarios** renvoient exactement les mêmes résultats que la v0.1.71. [Mesures détaillées et conditions](PERFORMANCES_v0.1.72.json).

**Mise à jour des données → Charger les inventaires de sets par lots** continue maintenant après la fermeture de cette fenêtre et de la fenêtre de mise à jour. BrickLabo doit rester ouvert. La barre d’état affiche **Inventaires : traités/total** ; cliquer dessus retrouve le travail en cours et **Pause**. Une seule tâche charge la file, même avec plusieurs fenêtres. **Charger le prochain lot** s’arrête après un lot ; **Enchaîner les lots** poursuit la file. Quitter BrickLabo arrête proprement les requêtes ; les lignes restantes restent enregistrées pour une reprise. Les droits API et leurs limites de requêtes restent applicables, sans paralléliser les appels. Aucun ajout au stock par ce chargement.


---

## Faster queries and background inventory loading — v0.1.72

Catalogue, filter, stock, project and cabinet reads reuse valid results and avoid repeated per-part lookups. Hidden tabs refresh when opened. Counts still respect reservations and assigned owned sets; imports and Undo/Redo invalidate affected results. The first launch builds the new query accelerators once.

Same disposable benchmark: **253,628 catalogue items, 1,558,072 inventory rows, 10,000 stock rows, 100 projects and 10,000 drawers**. These are first calls per scenario on Linux, not guaranteed Windows timings.

| Operation | v0.1.71 | v0.1.72 |
|---|---:|---:|
| First catalogue page | 60 ms | 6 ms |
| Catalogue page 50 | 132 ms | 6 ms |
| Hide decorated parts | 2,033 ms | 54 ms |
| Find catalogue parts to store | 1,830 ms | 66 ms |
| Search loose stock to store | 79 ms | 12 ms |
| Read cabinet contents | 100 ms | 40 ms |
| Search the entire Rebrickable set catalogue | 7.41 s | 4.93 s |

Repeated cached catalogue requests take about 1 ms on this benchmark. General refresh with My stock visible improves from a median of 165 to 9 ms; image downloads and rendering are disabled for this UI measurement. All **18 scenarios** return identical results to v0.1.71. [Full measurements and conditions](PERFORMANCES_v0.1.72.json).

**Data updates → Load set inventories in batches** now continues after closing its window and the data update window, while BrickLabo stays open. The status bar shows **Inventories: processed/total**; click it to reopen progress and **Pause**. Multiple windows share one worker. **Load next batch** stops after one batch; **Continue through batches** processes the queue. Quitting BrickLabo cancels requests safely and retains pending rows for resumption. API credentials and request limits still apply; requests remain sequential. Loading catalogue inventories adds no owned stock.


## Banc de mesure / Reproduction

```text
python tools/benchmark_queries.py --database dossier_neuf/benchmark.sqlite --prepare --output resultat.json --full
python tools/benchmark_ui_refresh.py --database dossier_neuf/benchmark.sqlite --output interface.json
```

Utiliser exclusivement une base de contrôle neuve. `--source-root` permet de mesurer un autre checkout avec le même script. Les résultats détaillent le premier appel, la médiane de deux répétitions, le nombre de requêtes observées et les empreintes des résultats. Les appels de métadonnées très courts restent des lectures directes. Le cache de résultats est limité à 8 Mio de données estimées et 256 entrées, avec copie indépendante pour chaque appelant ; les grandes réponses ne sont pas conservées. La reconnaissance photo et les QR codes ne sont pas inclus.
