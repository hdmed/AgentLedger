# OpenCost — documentation

## Positionnement

OpenCost extrait les sessions d'OpenCode depuis une base SQLite locale et génère un tableau de bord HTML autonome, sans appel réseau.

L'objectif d'évolution est de fournir un exécutable local unique pour suivre l'activité et les coûts d'OpenCode, AutoClaw/OpenClaw, Kilo/KiloCode et d'autres agents, sans synchronisation cloud.

## Architecture actuelle

- `extract.py` lit `opencode.db` en mode SQLite read-only, applique les prix et budgets, puis écrit les données générées.
- `build_report.py` assemble le dataset, `templates/report_template.html` et `assets/chart.umd.min.js` dans `dist/report.html`.
- `launcher.py` orchestre extraction, génération, diagnostic et ouverture du rapport, aussi bien depuis les sources que depuis l'EXE.
- `resources.py` sélectionne les chemins des ressources et du dossier utilisateur selon le mode source ou frozen.
- `build_exe.py` produit un exécutable Windows PyInstaller one-file ; `--onedir` permet un dossier de diagnostic.
- Le projet AutoClaw/OpenClaw et son TDB autonome sont documentés dans [`AutCLW.md`](AutCLW.md) et [`Docs/AutCLW/TDB/`](AutCLW/TDB/).
- `config/pricing.json` contient les prix USD par million de tokens, clés `providerID/modelID`.
- `config/budgets.json` contient les plafonds globaux, par projet et par modèle sur 30 jours glissants.
- `data/dataset.json`, `data/sync_state.json` et `dist/report.html` sont des artefacts générés et ignorés par Git.

Flux actuel OpenCost :

```text
OpenCode SQLite -> extract.py -> dataset généré -> build_report.py -> rapport HTML
```

Flux AutoClaw/OpenClaw déjà disponible :

```text
CLI OpenClaw + transcripts -> collect.ps1 -> telemetry/ -> TDB HTML autonome
```

OpenCost doit lire la sortie `telemetry/` comme source additionnelle, sans modifier le collecteur AutoClaw.

## Architecture cible

```text
Bases locales / sources
  OpenCode | AutoClaw/OpenClaw | Kilo/KiloCode | autres agents
              |
        connecteurs read-only
              |
       modèle d'activité commun
              |
       synchronisation + déduplication
              |
        dataset unifié local
              |
        tableau de bord offline
              |
        exécutable autonome
```

Les schémas et emplacements de Kilo/KiloCode doivent être inventoriés avant d'écrire son connecteur. AutoClaw/OpenClaw dispose déjà d'un collecteur et de formats de télémétrie documentés sous `Docs/AutCLW/TDB/` ; son intégration doit tout de même respecter le contrat commun et rester read-only.

## Invariants

- Lire les bases sources en read-only ; ne jamais les modifier pour produire le rapport.
- Conserver l'origine de chaque session et un identifiant stable pour la déduplication.
- Normaliser les dates en UTC et les coûts en USD.
- Conserver le mode offline comme comportement par défaut.
- Séparer configuration, données utilisateur et artefacts générés.
- Ajouter des fixtures de bases factices pour chaque connecteur avant le packaging.
- Emballer le périmètre OpenCode autonome dès que ses ressources et ses chemins utilisateur sont validés ; ne repackager le dashboard unifié qu'après stabilisation du contrat des connecteurs et du modèle commun.

## Commandes courantes

```powershell
python -m py_compile extract.py build_report.py resources.py launcher.py build_exe.py
python -m unittest discover -s tests -v
python build_report.py --strict
python launcher.py --diagnose
python launcher.py --no-open --full
python build_exe.py --confirm
```

`make test`, `make report`, `make all`, `make watch`, `make open` et `make clean` restent disponibles lorsque `make` est installé. Sur Windows, les commandes Python directes sont le fallback vérifiable.

## Vérification

La CI utilise Python 3.11, compile les entrypoints, exécute les tests puis lance `build_report.py --strict`. Le mode `--strict` vérifie la présence de Chart.js. Le mode `--external` crée un dataset adjacent et nécessite un serveur HTTP : il n'est pas entièrement autonome. L'EXE utilise `%LOCALAPPDATA%\OpenCost` pour les données et la configuration utilisateur, et conserve les bases sources en lecture seule.

## Index

- [Architecture et modèle de données cible](architecture.md)
- [Tableau de bord — structure et navigation](dashboard.md)
- [AutoClaw / OpenClaw — connecteur cible](AutCLW.md)
- [WorkBuddy — connecteur](WorkBuddy.md)
- [Plan de réalisation](plan.md)
