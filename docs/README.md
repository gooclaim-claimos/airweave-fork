# airweave-fork — documentation

Gooclaim-specific documentation for the Data Sources fork of Airweave. Anything not
covered here behaves as upstream Airweave: see <https://docs.airweave.ai> (source in
`fern/`, which this set does not touch).

| Doc | What it covers |
|---|---|
| [00-overview](00-overview.md) | What Data Sources is in Gooclaim OS, what it does and does not do |
| [01-architecture](01-architecture.md) | Components, request and sync flows, tenancy model, gateway wiring |
| [03-apis](03-apis.md) | The API surface Gooclaim services and the UI use, and what Gooclaim added |
| [05-configuration](05-configuration.md) | Environment variables Gooclaim sets or must leave unset |
| [06-deployment](06-deployment.md) | Running on the dev EC2 instance with `docker compose` |
| [07-operations](07-operations.md) | Health, logs, metrics, common failures and their causes |
| [08-testing](08-testing.md) | The two backend test trees, lint, the Gooclaim tests |
| [09-development](09-development.md) | Branches, conventions, adding Gooclaim changes safely |
| [11-security](11-security.md) | Trust boundary, trusted headers, master key, tenant isolation |
| [12-integrations](12-integrations.md) | gooclaim-auth, datasources MCP, LiteLLM, gooclaim-audit, Portal |
| [gooclaim-fork-rebase](gooclaim-fork-rebase.md) | Bringing in a newer upstream |

Not written, because nothing Gooclaim-specific and true would go in them: components
(see the README's "How It Differs From Upstream" table), data model and database docs
(the four Gooclaim migrations are described in the README and 01-architecture), ADRs.
