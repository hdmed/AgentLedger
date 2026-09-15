---
name: New connector
about: Propose or track support for another local AI agent
title: "[connector] "
labels: enhancement
---

## Agent and local data

- Agent name and where it stores usage locally (path):
- Format (SQLite / JSONL / other) and stable session id:
- Token fields available (input / output / cache / reasoning):
- Cost field available (USD? credits? none?):

## Acceptance sketch

- [ ] Non-destructive schema inventory documented
- [ ] Read-only access, dummy fixtures (nominal / empty / corrupt / unknown schema)
- [ ] `(source, source_session_id)` dedup + independent watermark
- [ ] `README.md` connector row + documented fallbacks
