# Architecture et modèle de données cible

## Périmètre

Le produit cible est un tableau de bord local unique couvrant plusieurs agents. La première version doit rester lisible, offline et portable ; elle ne remplace pas les bases sources.

## Couches proposées

1. **Connecteurs** : ouverture read-only, lecture incrémentale, détection de version et mapping vers le modèle commun.
2. **Modèle commun** : représentation normalisée d'une session et de ses métriques.
3. **Synchronisation** : watermark par source, fusion, déduplication et conservation de l'état local.
4. **Rapport** : filtres, KPI, graphes, table, exports et personnalisation des coûts.
5. **Packaging** : ressources embarquées, configuration utilisateur, diagnostics et lancement Windows.

## Contrat minimal d'une activité

Chaque enregistrement normalisé doit pouvoir transporter :

- `source` : nom du connecteur, par exemple `opencode`, AutoClaw ou `kilo`.
- `source_session_id` : identifiant stable dans la source.
- `project`, `agent`, `model_provider`, `model_id`.
- `time_created`, `time_updated` : horodatages normalisés en UTC.
- `tokens_input`, `tokens_output`, `tokens_reasoning`, `tokens_cache_read`, `tokens_cache_write`.
- `cost`, devise et origine du coût (`source` ou `pricing`).
- une référence ou un champ de provenance permettant le diagnostic sans dupliquer inutilement les données brutes.

Les champs indisponibles dans une source doivent être optionnels ; ils ne doivent pas bloquer l'import des autres sources.

## Connecteurs

### OpenCode

Le connecteur actuel lit la table `session`, joint `project`, utilise `time_updated`/`time_created` comme watermark et ouvre SQLite avec `mode=ro`. Il doit devenir une implémentation du contrat commun plutôt qu'un flux spécialisé dans le rapport.

### AutoClaw / OpenClaw

Le projet [`Docs/AutCLW/TDB/`](AutCLW/TDB/) fournit déjà un collecteur read-only et un tableau de bord autonome. Il lit `status --json`, les transcripts JSONL et écrit des snapshots, un journal et des agrégats dans `telemetry/`. Le connecteur OpenCost doit lire ces fichiers sans relancer ni modifier le collecteur AutoClaw.

Les champs observés et le mapping candidat sont documentés dans [AutoClaw / OpenClaw — connecteur cible](AutCLW.md). Les identifiants de session, le champ projet et la règle de coût doivent être confirmés avant la fusion.

### Kilo/KiloCode

À traiter comme un connecteur distinct. Avant développement, identifier :

- le chemin de la base ou des journaux utilisés par l'installation ;
- le schéma et les identifiants stables ;
- les champs de projet, agent, modèle, tokens, coût et dates ;
- le comportement en cas de version ou de migration de schéma.

Aucune hypothèse sur son format ne doit être intégrée sans fixture réelle ou documentée.

### Autres agents

Un nouveau agent nécessite un adaptateur, des fixtures et une stratégie de déduplication. Le dashboard ne doit pas connaître les détails SQL de chaque source.

## Données et chemins

- Configuration versionnée : `config/pricing.json`, `config/budgets.json`.
- État et dataset : dossier de données local, actuellement `data/`.
- Rapport : `dist/report.html`.
- Télemétrie AutoClaw lue en entrée future : `Docs/AutCLW/TDB/openclaw-tdb/telemetry/`.
- Pour l'EXE, les ressources sont lues depuis le paquet PyInstaller et les données, états, rapports et configurations utilisateur sont écrits sous `%LOCALAPPDATA%\OpenCost` (ou `OPENCOST_USER_DIR`).

## Sécurité et vie privée

- Les données restent locales.
- Les connecteurs ne doivent jamais envoyer les sessions à un service distant.
- Les exports et diagnostics doivent éviter d'inclure des secrets, tokens d'API ou chemins sensibles non nécessaires.
- Les erreurs de schéma doivent être explicites sans exposer le contenu brut des sessions.

## Performance

- Conserver la lecture incrémentale et le watermark par source.
- Prévoir un mode externe ou paginé si le dataset devient trop volumineux pour rester raisonnablement inline.
- Tester avec plusieurs milliers de sessions avant de valider le packaging.
- Mesurer séparément le temps d'extraction, de fusion et de rendu.
- Mesuré le 2026-09-13 (5200 sessions : 3000 OpenCode, 2000 Kilo, 200 AutoClaw) : extraction 0.4/0.5/0.2 s, fusion 1.3 s, rendu 0.2 s (2.9 Mo), 2e passe incrémentale 0.7 s. Les connecteurs ne réécrivent pas leur état quand rien n'a changé.
