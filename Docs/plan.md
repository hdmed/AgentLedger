# Plan de réalisation

## Objectif

Livrer un exécutable Windows autonome qui consolide localement l'activité et les coûts d'OpenCode, AutoClaw/OpenClaw, Kilo/KiloCode et, ensuite, d'autres agents dans un tableau de bord unique.

## État actuel

La première version autonome OpenCode est emballée avec PyInstaller. Elle fournit un lanceur, des ressources embarquées, un rapport offline et un dossier utilisateur persistant. AutoClaw/OpenClaw possède déjà un TDB autonome et des formats de télémétrie documentés sous `Docs/AutCLW/TDB/`. La consolidation AutoClaw puis Kilo/KiloCode reste une évolution ultérieure.

## Phase 0 — Stabiliser la base actuelle

**Livrables**

- Corriger les avertissements de tests et la documentation du nombre de tests.
- Vérifier les commandes Python directes sur Windows, où `make` peut être absent.
- Conserver les tests d'extraction, de build et d'intégration avec bases factices.

**Critères d'acceptation**

- Compilation et suite de tests vertes sur Python 3.11.
- Génération `--strict` verte avec Chart.js présent.
- Aucun artefact généré n'est versionné.

## Phase 1 — Modèle commun et contrat des connecteurs

**Livrables**

- Définir le modèle d'activité commun et le contrat d'interface des connecteurs.
- Encapsuler la lecture OpenCode existante dans un connecteur réutilisable.
- Ajouter la provenance, les identifiants stables et la normalisation UTC.
- Ajouter des fixtures pour les cas nominaux, vides, supprimés et schéma inconnu.

**Critères d'acceptation**

- Deux imports d'une même session ne créent pas de doublon.
- Une source indisponible ou vide n'efface pas les autres sources.
- Les tests du modèle sont indépendants de la base personnelle de l'utilisateur.

## Phase 2 — Connecteur AutoClaw / OpenClaw

**Livrables**

- Valider les chemins de la CLI, de la configuration et des transcripts AutoClaw.
- Lire les snapshots, le journal et les agrégats de `Docs/AutCLW/TDB/openclaw-tdb/telemetry/` en mode read-only.
- Mapper les champs vers le modèle commun et documenter les champs optionnels.
- Ajouter des fixtures à partir de `sample-data/` et de snapshots anonymisés.

**Critères d'acceptation**

- Import incrémental sans modifier OpenClaw ni ses transcripts.
- Déduplication entre snapshots et sessions réimportés.
- Absence de CLI, transcripts vides ou coût nul : comportement explicite et import des autres sources préservé.

## Phase 3 — Connecteur Kilo/KiloCode

**Objectif**

Ajouter une source locale `kilo` au pipeline OpenCost sans dépendre du cloud, sans écrire dans la base Kilo et sans supposer un schéma qui n'a pas été observé. Le connecteur doit fonctionner seul, puis alimenter le dataset commun avec les autres sources.

### Étape 3.1 — Inventaire de l'installation et du schéma

**Livrables**

- Détection du chemin de la base :
  - priorité à `KILO_DB` ;
  - prise en compte de `XDG_DATA_HOME` et du chemin par défaut Windows `%USERPROFILE%\.local\share\kilo\kilo.db` ;
  - diagnostic via `kilo db path` lorsque la CLI est disponible ;
  - option `--kilo-db <chemin>` pour les installations isolées.
- Ouverture SQLite en `mode=ro` uniquement.
- Inventaire non destructif de `sqlite_master`, `PRAGMA table_info`, `PRAGMA user_version` et du mode journal.
- Vérification de la présence et des colonnes de `session`, `message` et `part`.
- Capture anonymisée du schéma observé dans le diagnostic, sans contenu de conversation ni chemin inutilement sensible.

**Critères d'acceptation**

- La base source n'est jamais modifiée, y compris en présence de WAL/SHM.
- Une base absente, verrouillée, corrompue ou vide est signalée explicitement sans arrêter les autres sources.
- Un schéma inconnu produit une erreur de mapping compréhensible et un rapport de diagnostic.

### Étape 3.2 — Mapping vers le modèle commun

**Livrables**

- Identité stable : `source="kilo"` et `source_session_id` issu de la colonne `session.id`.
- Métadonnées : titre, répertoire de travail, projet, agent/mode si disponible.
- Dates : conversion des horodatages Kilo en UTC ; conservation de `time_created` et `time_updated`.
- Messages : lecture des enregistrements `message` et `part` uniquement pour extraire les métriques nécessaires, sans stocker le contenu brut dans le dataset.
- Modèle et usage : détection des champs ou payloads JSON contenant provider, modèle, tokens, cache et coût ; champs absents laissés optionnels.
- Coût : préférence au coût source Kilo lorsqu'il est exploitable, sinon calcul par `config/pricing.json` avec `cost_source="pricing"`.
- Watermark indépendant : `last_time_updated` conservé par source afin qu'une extraction Kilo n'avance pas le watermark OpenCode ou AutoClaw.

**Critères d'acceptation**

- Deux lectures d'une même session produisent une seule activité après fusion.
- Une session sans coût ou sans tokens est importée avec des valeurs optionnelles explicites.
- Les sessions Kilo sont identifiables dans le dataset et le rapport par leur source.

### Étape 3.3 — Connecteur

**Livrables**

- `extract_kilo.py` ou module `connectors/kilo.py` avec une interface réutilisable : découverte, lecture incrémentale, mapping, diagnostic.
- Arguments CLI dédiés : `--kilo-db`, `--kilo-full`, `--kilo-since` et option de désactivation `--no-kilo`.
- État de synchronisation séparé : `data/kilo_sync_state.json` ou section `kilo`.
- Fixtures SQLite :
  - schéma nominal avec plusieurs messages/parts ;
  - session sans usage ;
  - session mise à jour ;
  - base vide ;
  - schéma inconnu ;
  - base verrouillée ou corrompue.
- Tests unitaires du mapping et tests d'intégration avec bases factices, indépendants de la base personnelle de l'utilisateur.

**Critères d'acceptation**

- Les fixtures couvrent les cas nominaux, vides, supprimés, corrompus et schéma inconnu.
- Les tests vérifient la déduplication, le watermark, les dates UTC, les tokens/cache/coût et la provenance.
- L'extraction Kilo peut être exécutée sans OpenCode ni AutoClaw présents.

### Étape 3.4 — Fusion et rapport

**Livrables**

- Clé de déduplication `(source, source_session_id)` dans le modèle commun.
- Fusion additive : l'absence ou l'échec d'une source ne supprime pas les sessions des autres sources.
- Ajout du filtre `source` dans le rapport, avec filtres projet, agent, modèle et date conservés.
- Affichage de l'origine du coût et des champs manquants dans les exports et le diagnostic.
- Mise à jour de `Docs/architecture.md` avec le schéma Kilo observé et les règles de fallback.

**Critères d'acceptation**

- Une session OpenCode, une session AutoClaw/OpenClaw et une session Kilo sont visibles dans le même tableau.
- Le rapport reste fully offline et ne charge aucun contenu distant.
- Les exports et graphes restent cohérents avec les totaux du dataset fusionné.

### Étape 3.5 — Packaging et robustesse

**Livrables**

- Ajout du connecteur et des fixtures aux ressources PyInstaller.
- Diagnostic `launcher.py` : chemins, tests, état et rapport de diagnostic.
- Journal sans messages, tokens d'API, chemins sensibles ou données de conversation.
- Tests de performance avec plusieurs milliers de sessions Kilo.
- Documentation de sauvegarde/réinitialisation de `data/kilo_sync_state.json` et du dataset.

**Critères d'acceptation**

- L'EXE one-file et one-folder lit Kilo en read-only.
- Une mise à jour du schéma Kilo ne bloque pas silencieusement les autres sources.
- Le build, les tests et le rapport `--strict` restent reproductibles sur Windows.

## Phase 4 — Dashboard unifié

**Livrables**

- Fusionner les datasets des connecteurs dans une vue unique.
- Ajouter le filtre par source et conserver les filtres existants par projet, agent, modèle et date.
- Afficher les KPI, graphes, budgets, table et exports avec l'origine des données.
- Conserver le rendu offline et le mode dataset externe optionnel.

**Critères d'acceptation**

- Une session OpenCode, AutoClaw/OpenClaw et Kilo/KiloCode est visible dans le même tableau.
- Les filtres et exports fonctionnent sur le dataset fusionné.
- Le rapport reste exploitable sans réseau.

## Phase 5 — Exécutable autonome multi-sources

**Livrables**

- Choisir PyInstaller et fournir un build reproductible en one-file et one-folder.
- Emballer scripts, modèle HTML, Chart.js et ressources nécessaires.
- Utiliser un dossier utilisateur pour configuration, dataset, watermark et rapports.
- Ajouter un lanceur avec diagnostic, ouverture du rapport et modes d'extraction.

**Critères d'acceptation**

- L'EXE fonctionne sur une machine sans Python ni dépendances installées.
- Aucune écriture n'est requise dans un dossier protégé.
- Le rapport et les ressources critiques sont présents après packaging.
- Le build est rejouable depuis la ligne de commande.

## Phase 6 — Connecteurs unifiés et robustesse

**Livrables**

- Tests de performance avec plusieurs milliers de sessions.
- Gestion des migrations, corruption partielle et bases verrouillées.
- Journal de diagnostic sans données sensibles.
- Instructions de mise à jour, sauvegarde et réinitialisation.
- CI Windows pour compilation, tests, build du rapport et build de l'EXE.

**Critères d'acceptation**

- Les scénarios d'erreur sont testés et compréhensibles.
- Une mise à jour de version de source ne bloque pas silencieusement le dashboard.
- Le livrable peut être reproduit et vérifié par la CI.

## Prochaines décisions à trancher

1. Identifiant stable AutoClaw, champ projet et règle de coût.
2. Emplacement et format exacts des données Kilo/KiloCode.
3. Politique de conservation des données et taille maximale du dataset fusionné.
4. Taille, démarrage et stratégie de mise à jour de l'EXE multi-sources.
5. Périmètre du prochain release : OpenCode + AutoClaw/OpenClaw, puis Kilo/KiloCode.

## Ordre recommandé

Conserver l'EXE OpenCost actuel comme livrable autonome OpenCode. Pour l'évolution unifiée, valider d'abord le connecteur AutoClaw/OpenClaw à partir des fixtures de télémétrie existantes, puis inventorier Kilo/KiloCode, stabiliser le modèle commun et repackager le dashboard fusionné.
