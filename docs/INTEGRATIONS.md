# Integrations

The local first result uses native membership, SQLite, the shared pricing engine and a private company bridge between two loopback services.

| Interface | Source | Recipient setup and acceptance |
| --- | --- | --- |
| Public widget and Orders | `app/src/prototypes/orders/serve.py`, `store.py`, `pipeline/bundle.py` | Build your public directory and ingest your catalogue. `quote.py` runs the same Node pricing code as the browser. |
| Company source bridge | `manufacturer_source_http.py`, `manufacturer_publish.py`, `platform_source.py`, `configurator_versions.py` | Exact Orders origin, company slug, workspace scope and a private shared transport token. Each write checks company identity; publication acknowledges exact ID, revision and SHA256. |
| Original specifications | `manufacturer_source_files.py`, `manufacturer_source_reader.py`, `order_files.py` | Native owned files and the pinned CPU document dependencies. Extraction is bounded; scanned or incomplete input retains review status. |
| Hosted identity | `harness/mechanics/workspace_auth.py` and selected host routes | Recipient identity-provider configuration and verified organization membership. One-use local codes use the same native roles. Locate the retained identity provider implementation through the function reference if the host adapter is selected. |
| Managed agents | `harness/runtime/agent_auth.py`, `managed_runtime.py`, `managed_codex.py` | Recipient `ROCOTO_OPENAI_API_KEY`, explicit `openai_api` mode, company funding/admission and access to the pinned managed-core API contract. Provider acceptance is separate from local source checks. |
| Customer research | `research_queue.py`, `research_tools.py` | Company capability, admitted agent runtime, source permission and funded grant. The sample sets `customerResearch: false` and marks illustrative requests as demo data. |
| Customer email | `manufacturer_mail.py`, `manufacturer_mail_routes.py`, `customer_mail.py` | Recipient sender/domain, provider credentials, verified send/receive/webhook evidence, scoped spend grant and daily limits. Save and send remain distinct operations. |
| Chatwoot | `manufacturer_chatwoot.py`, `manufacturer_chatwoot_routes.py`, `harness/deploy/chatwoot/` | Owned Chatwoot CE instance, account/inbox IDs, API and webhook secrets, scope and commissioning evidence. The package generates private instance secrets and defaults its outbound SMTP to a held local endpoint. |
| Billing and subscription | `harness/mechanics/workspace_billing.py`, `workspace_billing_routes.py`, company usage and capability modules | The recipient’s own provider account and authoritative subscription/funding records. Local access codes establish workspace identity; spending keeps its separate admission. |
| PostgreSQL journal | `backend/realtime/`, shared journal adapter | Recipient database, schema and supported driver for that journal path. The first result exercises SQLite. |

## Keys and activation

`tools/configure.py` saves your project key through hidden input. `tools/serve.py` clears inherited provider settings and loads the explicitly selected credential directory. `--enable-managed-agents` selects the retained API auth mode; company funding, capability and current-authority checks remain in the native runtime.

The sample’s manual workspace sets `agentEditing: false`. A recipient enabling agent editing changes its own company configuration and commissions the managed runtime. The source includes the original managed request/usage/recovery mechanisms; this extraction makes no new provider availability, funded execution or email-delivery claim.

Source configuration is the deployment contract. A key supplies authentication; scoped grants, membership, budgets and verified external setup authorize effects. The local first-result scripts keep those external effects held while the deterministic product workflows run.

[made by atelier neyra](https://atelierneyra.com)
