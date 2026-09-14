# Contributing to AgentLedger

## Ground rules

- **Python 3.10+ stdlib only.** No new runtime dependencies — the frozen
  EXE must work on a machine without Python or packages.
- **Read-only sources.** Connectors open databases with `mode=ro` and never
  write to source folders (SQLite, transcripts, telemetry).
- **Additive merge.** A missing or failing source must never delete other
  sources' sessions. Dedup key: `(source, source_session_id)`.
- **Fixtures first.** Every connector ships dummy-database fixtures covering
  nominal, empty, deleted, corrupt and unknown-schema cases
  (`tests/test_<source>.py`).
- **English default, 10 locales.** `en` is the fallback; the report UI ships
  EN, FR, ES, PT, ZH, HI, AR, BN, RU, ID. Never hardcode user-facing text —
  see [Translating](#translating) below.

## Setup

```sh
git clone https://github.com/hdmed/AgentLedger.git
cd AgentLedger
python -m unittest discover -s tests        # all green before you start
python launcher.py --no-open                # builds dist/report.html
```

Useful targets (`make`): `test` (compile + unittest), `check-js`
(`node --check` on the template JS), `report`, `all`, `watch`,
`open-app`, `exe` (frozen build), `clean`.

## Workflow

1. Create a branch from `main`.
2. `python -m unittest discover -s tests -v` — all green before pushing.
3. `python build_report.py --strict` — report builds offline.
4. New connector? Follow `extract_workbuddy.py` (smallest full example):
   `default_db_path()` (+ env override), `inspect_schema()`,
   `fetch_sessions()`, `extract()`, `max_time()`, separate
   `data/<source>_sync_state.json`, `--no-<source>` launcher flag,
   `Docs/<Source>.md` with the observed schema and fallbacks.
5. Template change? Run `make check-js` and keep canvas `id`s unique
   across views. User-facing text goes through `t()`/`tf()` or
   `data-i18n*` — never raw literals.
6. Open a pull request against `main`; CI (`test` on Linux, `test-windows`
   with EXE build + smoke test) must be green.

## Translating

UI strings live in `locales/<lang>.json` (UTF-8, one key per line, same key
order as `en.json`) and are inlined into the report by `build_report.py`
(`/*__LOCALES__*/`) — the HTML stays a single offline file.

- **Fix a translation:** edit the value in `locales/<lang>.json`, keep
  `{placeholders}` byte-identical, keep `<b>`/`<code>` markup and leading
  emoji (📊 🔗 ＋ …). JSON needs no apostrophe escaping — just write `'`
  and `’` directly. Never introduce `</script`.
  Then run `python -m unittest tests.test_i18n -v`.
- **Add a language:** copy `locales/en.json` to `locales/<code>.json`
  (ISO 639-1), translate every value, add an `<option>` to `#lang-select`
  in `templates/report_template.html` (native language name), add the
  `toLocaleString` tag to `NUM_LOCALES`, and — for RTL languages — mirror
  rules next to the existing `[dir="rtl"]` CSS. `test_ten_locales_present`
  lists the supported set: extend it.
- **Rules enforced by tests** (`tests/test_i18n.py`): identical ordered key
  sets in all locales, identical `{placeholder}` sets per key, no
  `</script` breakout, every template-used key defined.

## Bug reports

Open a GitHub issue with: what you ran, `python launcher.py --diagnose`
output, and the relevant log lines. Never paste API keys, tokens, database
contents or conversation text — describe the schema, not the data.
