# Security policy

AgentLedger is a local-first tool: it reads your agent databases and builds
a local HTML report. It makes no network calls by design
(`--external` mode excepted, which only fetches a local `dataset.json`).

## Reporting a vulnerability

Open a GitHub issue with the `security` label and **do not** include:

- API keys, tokens, or credentials of any kind;
- database contents, conversation text, or file bodies;
- full local paths (redact usernames).

Describe the schema and the steps to reproduce. We aim to acknowledge
within 7 days.

## Scope notes

- Connectors must stay read-only (`mode=ro`); a connector that writes to a
  source folder is treated as a bug.
- Diagnostics (`launcher --diagnose`) intentionally print paths — check them
  before pasting into a public issue.
