# WorkBuddy — connecteur

WorkBuddy AI (application desktop, constaté sous
`%LOCALAPPDATA%\Programs\WorkBuddyAI`) est intégré via
`extract_workbuddy.py` : lecture SQLite **read-only** (`mode=ro`) de
`~\.workbuddy-ai\workbuddy.db`, sans écrire ni verrouiller la base
(qui reste utilisable par l'application en cours d'exécution).

## Schéma observé (inventaire non destructif)

- `sessions` : `id`, `cwd`, `title`/`custom_title`, `status`, `created_at`,
  `updated_at`, `last_activity_at`, `deleted_at` (**millisecondes**),
  `mode` (ex. `craft`), `model` (**nom nu**, ex. `deepseek-v4.1-flash`),
  `project_id` (souvent `NULL`).
- `session_usage` : `session_id`, `used`/`size` (remplissage de la fenêtre
  de contexte), `updated_at`, `credit_json` (`{uuid: montant}`).
- Tables ignorées : `workspaces` (vide), `automations`, `buddy_snapshots`,
  `*_outbox`, migrations.

## Mapping vers le modèle commun

| Modèle commun | Champ WorkBuddy | Remarque |
|---|---|---|
| `source` | `workbuddy` | constant |
| `source_session_id` | `sessions.id` | stable |
| `project` | basename de `cwd` | `project_id` étant `NULL`, repli `?` |
| `agent` | `mode` | ex. `craft` |
| `model_provider` | `?` | noms de modèles non qualifiés |
| `model_id` | `sessions.model` | valeur brute conservée |
| `time_created` / `time_updated` | `created_at` / `max(updated_at, last_activity_at)` | ms → s UTC |
| `tokens_input` | `session_usage.used` | **fallback contrôlé** : remplissage contexte, pas des tokens facturés |
| `tokens_output` / autres | `0` | indisponibles dans la source |
| `cost` | somme de `credit_json` | **crédits du plan WorkBuddy, PAS des USD** (cf. ci-dessous) |
| `cost_source` | `pricing` si override, sinon `workbuddy` | résolu à la fusion |
| `archived` | `deleted_at IS NOT NULL` | sessions supprimées conservées avec flag |

## Avertissement unités de coût

WorkBuddy facture au **Token Plan** (quota de crédits), pas au token :
les montants importés sont des **crédits**, mélangés aux USD dans les totaux
du dataset. Le `cost_source="workbuddy"` et la colonne Coût du rapport
permettent de les distinguer ; ne pas comparer frontalement aux coûts USD
des autres sources. Une session sans crédits est importée à `0.0` explicite.

## Fonctionnement

- Watermark indépendant sur `updated_at` (secondes), état séparé
  `data/workbuddy_sync_state.json` (sessions mises en cache, pas de
  réécriture si rien de nouveau).
- `session_usage` absente → tokens et coût à `0`, import préservé.
- Base absente, verrouillée, corrompue ou schéma inconnu → statut
  `missing`/`error` explicite, autres sources préservées.
- Options : `--workbuddy-db`, `--workbuddy-full`, `--workbuddy-since`,
  `--no-workbuddy` (env `WORKBUDDY_DB`). Chemin par défaut Windows :
  `%USERPROFILE%\.workbuddy-ai\workbuddy.db` (fonctionne aussi en EXE).
- `launcher --diagnose` affiche `workbuddy_database(_exists)` et `workbuddy_state`.

## Fichiers liés

- Connecteur : `extract_workbuddy.py`
- Tests : `tests/test_workbuddy.py` (fixtures fidèles au schéma observé)
- Fusion : `launcher.merge_source_result` (clé `(source, source_session_id)`)
