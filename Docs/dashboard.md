# Tableau de bord — structure et navigation

Le rapport `dist/report.html` est une page unique 100 % hors-ligne, organisée en
**onglets**, avec une **barre de filtres sticky** et un **drawer de détail**.
Source : `templates/report_template.html` + dataset inline + Chart.js vendored,
assemblés par `build_report.py`.

## Onglets (vues)

La navigation se fait par les boutons du header (`role="tablist"`).
La vue active est persistée dans l'URL (`?view=...`) et donc partageable
via « 🔗 Partager ». Sans paramètre, la vue d'ensemble s'affiche.

| Onglet (`view=`) | Contenu |
|---|---|
| `overview` (défaut) | KPI, graphes coût/tokens par jour, histogramme coût/session, cache & erreurs, prévision 30j, grille budgets, anomalies |
| `modeles` | Coût par modèle (donut), carte de comparaison multi-modèles, panneau de personnalisation des coûts (`pricing.json`) |
| `projets` | Coût par agent, coût par équipe, panneau d'édition des budgets (`budgets.json`) |
| `sessions` | Recherche naturelle (NLQ) + table détaillée plein-largeur avec exports CSV/JSON |

Fonctions JS : `switchView(v)` (bascule + `resize` des graphes visibles),
`refreshVisibleCharts()` (les canvas des vues cachées ont une taille nulle
à la création, ils sont redimensionnés à l'activation de leur onglet).

## Barre de filtres

`#filterbar` reste collée sous le header (`position: sticky`).
Ligne compacte toujours visible : plage **De/Au**, **recherche titre**,
**Source**, bouton **＋/－ Filtres**, **Réinitialiser**.
Le panneau `#filters-panel` (replié par défaut) contient le détail :
modèles (multi-sélection), agent, projet, équipe, coûts min/max.

Tous les filtres s'appliquent globalement, quelle que soit la vue active :
KPI, graphes, table et exports reflètent la même sélection.
État reflété dans l'URL : `from`, `to`, `models`, `agent`, `proj`, `team`,
`src`, `q`, `cmin`, `cmax` (`pushURL` / `loadFromURL`).

## Drawer de détail session

Un clic sur une ligne de la table (hors boutons de note) ouvre `#drawer`,
panneau latéral avec le détail : titre, source, identifiant stable
(`source_session_id`), date, modèle, agent, projet, équipe, coût et origine
du coût, tokens (entrée/sortie, reasoning, cache lu/écrit).
Fermeture : bouton ✕, clic sur l'overlay, ou Échap.
Fonctions JS : `openDrawer(sessionId)`, `closeDrawer()`.

## Interactions conservées

- **Drill-down** : un clic sur un graphe filtre et navigue vers l'onglet
  pertinent (`model` → Modèles, `agent`/`équipe` → Projets, `day` → dates).
- **Zoom** : clic sur la zone d'un graphe → overlay agrandi ; bouton ⬇ →
  export PNG du graphe.
- **Live pricing/budgets** : saisie en direct avec brouillon `localStorage`,
  export `pricing.json` / `budgets.json` à recopier dans `config/` puis
  `python extract.py --full && python build_report.py` pour pérenniser.
- **Notes** : bouton 🗒️ par ligne, stockées en `localStorage` (non exportées).
- **Thème** clair/sombre persisté ; **impression** = vue active uniquement
  (header, onglets, filtres, drawer et outils de graphe masqués).

## Ajouter un graphe ou une vue

1. Ajouter le `<canvas id="c-...">` dans la section `<section id="view-...">`
   cible (chaque `id` de canvas doit rester unique dans le document).
2. Le construire dans `renderCharts()` via `mkChart('c-...', cfg)` — le
   dictionnaire `charts` sert au `resize` automatique et aux exports PNG/zoom.
3. Pour une nouvelle vue : ajouter un bouton `.tab-btn` (`data-view`),
   une `<section class="view" id="view-...">`, et la déclarer dans `VIEWS`.
4. Vérifier : `node --check` du script extrait, `python -m unittest`,
   `python build_report.py --strict`.

## Fichiers liés

- Template : `templates/report_template.html`
- Build : `build_report.py` (structure non modifiée par la restructuration)
- Tests : `tests/test_launcher.py::test_report_structure_onglets`
- Données : `data/dataset.json` (généré, ignoré par Git)
