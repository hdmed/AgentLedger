# Dashboard — structure and navigation

The `dist/report.html` report is a single 100% offline page organized in
**tabs**, with a **sticky filter bar** and a **detail drawer**.
Source: `templates/report_template.html` + inline dataset + vendored
Chart.js, assembled by `build_report.py`.

## Tabs (views)

Navigation uses header buttons (`role="tablist"`).
The active view persists in the URL (`?view=...`) and is therefore shareable
via "🔗 Share". Without a parameter, the overview shows.

## Language (EN/FR)

The header `FR`/`EN` button (`#lang-toggle`) switches the whole UI between
English and French. Choice persists in `localStorage` (`agentledger_lang`),
can be forced via `?lang=fr|en`, and is included in shared links. Default:
URL param, then saved choice, then browser language. Implementation:
`I18N` dict + `t(k)` / `tf(k, params)` in the template; static text uses
`data-i18n` (plus `-html`/`-ph`/`-title`/`-aria` variants). `tests/test_i18n.py`
fails the build if a used key is missing in either language.

| Tab (`view=`) | Contents |
|---|---|
| `overview` (default) | KPIs, trio row (anomalies + cost/session histogram + cache & errors sharing 100%), cost/tokens per day charts, 30-day forecast, budgets grid |
| `modeles` | Cost-by-model donut, multi-model comparison card, cost customization panel (`pricing.json`) |
| `projets` | Cost by agent, cost by team, budgets editing panel (`budgets.json`) |
| `sessions` | Natural-language search (NLQ) + full-width detail table with CSV/JSON exports |

JS functions: `switchView(v)` (switch + resize of visible charts),
`refreshVisibleCharts()` (hidden views' canvases have zero size at creation
and are resized when their tab activates).

## Filter bar

`#filterbar` sticks under the header (`position: sticky`).
Always-visible compact row: **From/To** range, **title search**,
**Source**, **＋/－ Filters** button, **Reset**.
The `#filters-panel` (collapsed by default) holds the detail: multi-model,
agent, project, team, min/max cost.

All filters apply globally whatever the active view: KPIs, charts, table
and exports reflect the same selection.
State mirrored in the URL: `from`, `to`, `models`, `agent`, `proj`, `team`,
`src`, `q`, `cmin`, `cmax` (`pushURL` / `loadFromURL`).

## Session detail drawer

Clicking a table row (outside note buttons) opens `#drawer`, a side panel
with: title, source, stable id (`source_session_id`), date, model, agent,
project, team, cost and cost origin, tokens (in/out, reasoning, cache
read/written).
Close: ✕ button, overlay click, or Escape.
JS functions: `openDrawer(sessionId)`, `closeDrawer()`.

## Kept interactions

- **Drill-down**: clicking a chart filters and navigates to the relevant tab
  (`model` → Models, `agent`/`team` → Projects, `day` → dates).
- **Zoom**: clicking a chart area opens the enlarged overlay; ⬇ exports the
  chart as PNG.
- **Live pricing/budgets**: live typing with `localStorage` draft,
  `pricing.json` / `budgets.json` export to copy into `config/` then
  `python extract.py --full && python build_report.py` to persist.
- **Notes**: 🗒️ button per row, stored in `localStorage` (not exported).
- **Theme** persisted light/dark; **print** = active view only (header, tabs,
  filters, drawer and chart tools hidden).

## Adding a chart or a view

1. Add the `<canvas id="c-...">` inside the target
   `<section id="view-...">` (each canvas `id` must stay unique).
2. Build it in `renderCharts()` via `mkChart('c-...', cfg)` — the `charts`
   dict drives automatic resize and PNG/zoom exports.
3. For a new view: add a `.tab-btn` (`data-view`), a
   `<section class="view" id="view-...">`, and declare it in `VIEWS`.
4. Verify: `node --check` on the extracted script, `python -m unittest`,
   `python build_report.py --strict`.

## Related files

- Template: `templates/report_template.html`
- Build: `build_report.py` (structure untouched by refactors)
- Tests: `tests/test_launcher.py::test_report_structure_onglets`
- Data: `data/dataset.json` (generated, Git-ignored)
