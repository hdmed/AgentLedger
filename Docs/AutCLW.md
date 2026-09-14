# AutoClaw / OpenClaw — connecteur cible

## Emplacement et statut

Le projet AutoClaw est déjà présent dans [`Docs/AutCLW/`](AutCLW/). Son tableau de bord autonome se trouve dans [`Docs/AutCLW/TDB/`](AutCLW/TDB/) et collecte les métriques OpenClaw sans modifier les bases ou transcripts sources.

OpenCost peut réutiliser ce projet comme deuxième source locale. Le connecteur AutoClaw est intégré via `extract_autoclaw.py` : lecture read-only de `telemetry/journal.js` (agrégé par session) avec repli sur les sessions de `telemetry/latest.js` quand le journal est absent ou vide, sans lancer ni modifier `collect.ps1`. Fusion additive dans le dataset via `(source, source_session_id)` avec `source="autoclaw"`.

Décisions tranchées à l'implémentation :

- `source` = `autoclaw` ; `source_session_id` = `journal:<session>` (primaire) ou `snapshot:<key>` (repli, jamais combiné au journal pour éviter tout double comptage).
- `project` = `agent` AutoClaw (aucun espace de travail dans le journal) ; `agent` = `journal.agent`.
- `model` = `provider/model` (`provider` du journal si le modèle n'est pas qualifié) ; `time_created`/`time_updated` = min/max des `ts` en UTC.
- `tokens_input`/`tokens_output`/`tokens_cache_read` cumulés ; `tokens` non ventilé compté en entrée (fallback contrôlé) ; coût journalier nul avec `cost_source` résolu à la fusion (`pricing` si override, sinon `autoclaw`).
- État séparé `data/autoclaw_sync_state.json`, watermark indépendant, options `--autoclaw-dir`, `--autoclaw-full`, `--autoclaw-since`, `--no-autoclaw` (env `AUTOCLAW_TELEMETRY_DIR`).
- En mode EXE (frozen), le dossier est détecté automatiquement dans l'ordre : `AUTOCLAW_TELEMETRY_DIR`, `telemetry/` à côté de l'EXE, `%LOCALAPPDATA%\OpenCost\telemetry`, `..\Docs\AutCLW\TDB\openclaw-tdb\telemetry` (layout `dist/`), télémétrie embarquée. `launcher --diagnose` liste les candidats et leur existence (`autoclaw_candidat`).

## Sources lues

Le collecteur existant [`Docs/AutCLW/TDB/openclaw-tdb/collect.ps1`](AutCLW/TDB/openclaw-tdb/collect.ps1) utilise :

- la CLI OpenClaw, par défaut `C:\Program Files\AutoClaw\resources\gateway\openclaw\openclaw.mjs` ou `~\.openclaw\openclaw.mjs` ;
- la commande `status --json` pour le snapshot du gateway ;
- les transcripts `~\.openclaw-autoclaw\agents\*\sessions\*.jsonl` pour le journal des actions ;
- les fichiers de sortie `openclaw-tdb\telemetry\` pour le tableau de bord.

La collecte est read-only pour OpenClaw. Les écritures sont limitées au dossier de télémétrie AutoClaw.

## Contrat de données observé

### Snapshot

`telemetry\latest.js` expose `window.TDB_REMOTE` avec notamment :

- `ts`, `model`, `provider`, `runtimeVersion` ;
- `runIn`, `runOut`, `totalTokens`, `costUsd` ;
- `cacheHitPct`, `cachedTokens`, `contextTokens`, `contextLimit` ;
- `sessionsActive`, `sessionsTotal`, `agentsTotal`, `cronsTotal`, `channels` ;
- `sessions[]` avec `key`, `channel`, `model`, `tokens`, `cost`, `status` ;
- `agents[]` avec `id`, `name`, `model`, `active`.

`telemetry\history.jsonl` conserve les snapshots dans le temps. `costUsd` et `sessions[].cost` sont actuellement optionnels et souvent `null`.

### Journal des actions

`telemetry\journal.js` expose `window.TDB_JOURNAL` avec :

- `ts`, `agent`, `session`, `task`, `action` ;
- `provider`, `model`, `durationMs` ;
- `tokens`, `inputTokens`, `outputTokens`, `cacheReadTokens` ;
- `tokenStatus` (`reported`, `estimated` ou `unknown`) ;
- `state`.

`telemetry\stats-aggregates.json` conserve les totaux cumulés, la répartition par modèle et les compteurs d'événements. Ces agrégats ne doivent pas être confondus avec les sessions détaillées utilisées par OpenCost.

## Mapping vers le modèle commun OpenCost

| Modèle commun | Champ AutoClaw candidat | Remarque |
|---|---|---|
| `source` | nom du connecteur AutoClaw | Valeur de provenance à confirmer lors de l'implémentation |
| `source_session_id` | `sessions[].key` ou `journal.session` | La stabilité entre snapshots doit être vérifiée |
| `project` | `agent` ou espace de travail AutoClaw | À confirmer selon l'usage attendu |
| `agent` | `journal.agent` | Identifiant d'agent AutoClaw |
| `model_provider` | partie avant `/` de `model` | Optionnel si le modèle n'est pas qualifié |
| `model_id` | partie après `/` de `model` | Conserver la valeur brute en provenance |
| `time_created` / `time_updated` | `ts` | Normaliser en UTC |
| `tokens_input` / `tokens_output` | `inputTokens` / `outputTokens` | Utiliser `tokens` comme fallback contrôlé |
| `tokens_cache_read` | `cacheReadTokens` | Optionnel |
| `cost` | `costUsd` ou `sessions[].cost` | Requiert une règle de prix si la source est nulle |
| `cost_source` | `source` ou `pricing` | Conserver la provenance du calcul |

Les champs absents doivent rester optionnels. Une session ou action sans coût ne doit pas bloquer l'import des autres sources.

## Stratégie d'intégration recommandée

1. ~~Ajouter un connecteur AutoClaw qui lit les fichiers de télémétrie existants sans lancer ni modifier `collect.ps1`.~~ Fait (`extract_autoclaw.py`).
2. ~~Produire des fixtures à partir de `sample-data/` et de snapshots anonymisés.~~ Fait (`tests/test_autoclaw.py`, dont un test sur les fixtures versionnées).
3. ~~Implémenter la déduplication par source et identifiant stable.~~ Fait (clé `(source, source_session_id)`, watermark indépendant).
4. ~~Fusionner les sessions AutoClaw avec le dataset OpenCost existant.~~ Fait (`launcher.merge_source_result`, filtre `Source` dans le rapport).
5. ~~Ajouter le filtre par source dans le rapport, puis emballer le résultat dans l'EXE.~~ Filtre fait ; EXE via l'import du lanceur (PyInstaller suit `extract_autoclaw`).

Le tableau de bord AutoClaw existant peut rester autonome pendant cette phase. Il constitue déjà une référence fonctionnelle pour les KPI, le journal et les modes de rafraîchissement.

## Critères d'acceptation

- OpenClaw absent, transcripts vides ou schéma partiel : diagnostic explicite et import des autres sources préservé.
- Deux collectes d'une même session ne créent pas de doublon.
- Aucune écriture dans `C:\Program Files\AutoClaw`, `~\.openclaw` ou `~\.openclaw-autoclaw`.
- Le rapport OpenCost reste entièrement hors-ligne après fusion.
- Les champs optionnels et les coûts nuls sont visibles sans faire échouer le build.

## Documentation AutoClaw existante

- [Présentation du projet](AutCLW/README.md)
- [Installation du TDB](AutCLW/TDB/docs/INSTALL.md)
- [Usage du TDB](AutCLW/TDB/docs/USAGE.md)
- [Architecture du TDB](AutCLW/TDB/docs/ARCHITECTURE.md)
