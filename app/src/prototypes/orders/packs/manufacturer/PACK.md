# Manufacturer harness integration

This pack loads through the current harness's `layout.py` and `sdk/pack.py`, imports its native host
hooks and passes its actual tool registry. The host extension translates a current harness membership
into an orders-owned `CompanyContext`, bound to one private company database. Every store operation
opens and closes SQLite in the worker thread that performs it.

## Local launch

From the orders checkout root, validate the Metal-M database and start the read-only tool bridge:

```bash
python3 app/src/prototypes/orders/harness_launcher.py \
  --harness-source /home/peter/wt/rocoto-vcr-fix/harness \
  --database /home/peter/.local/state/rocoto/orders-demo/runtime/companies/metal-m/company.db \
  --company metal-m \
  --workspace /home/peter/.local/state/rocoto/orders-demo/harness/metal-m \
  --actor peter-local --role operator check
```

Replace `check` with `stdio` to keep the bridge open. Each input line is a tool call:

```json
{"name":"catalog_read","arguments":{"item_id":"01-00061"}}
```

The response is one JSON line with `ok` and `result`, or `ok: false` and `error`. `call --request
'<JSON>'` runs one call. `specs` prints the native dynamic-tool definitions (`inputSchema`),
and `prompt` prints the pack system instruction, common instruction and generated onboarding
skill. These commands make no model or provider calls.

The shell user selects `--role`; its default is `public`. `operator` is the existing trusted-local
operator path, rather than a claim of company ownership. The fixed company id must match the
already ingested database, and the private workspace binds company, canonical database path and template. Reads
open SQLite with `mode=ro` and `query_only`. JSON tool calls cannot change the company, database,
principal, role or write capability. A network host must derive these from its own authenticated
membership; the installed host extension now performs that translation. Harness `browse` maps to
the public order capability, `operator` to operator and `owner` to owner. Current admission and the
workspace-scope company id are checked before every tool invocation; arbitrary native contexts are refused.

For explicitly authorised local maintenance, add `--write --evidence '<source or operator receipt>'`
at startup. Each write still needs its declared idempotency key and role. The adapter keeps
`orders_submit` and `claim_grant` host-only: the order API computes prices, and verified ownership
uses its separate operator workflow. Public claim requests remain pending. Message tools create
held drafts; this bridge has no send or publish tool.

## Current boundary

| Working integration | Remaining harness work |
|---|---|
| Actual layered `layout.install`, `sdk/pack.load`, `import_host`, `import_tool_families`, registry, recipe and skill checks | Repeat packaging validation against the selected tracked harness revision before updating the pinned build |
| Native `BareWorkspace` extension maps current `owner`, `operator` and `browse` membership to a database-bound `CompanyContext` | Issue a fresh one-use code when a new browser session needs access |
| Per-operation same-thread SQLite connections, with company identity checked at install and open | Keep the company database and workspace marker under the runtime account at mode `0600` |
| `orders_list` supplies cursor pagination with current status, recorded price and the latest date projection, without customer details | Add richer order detail actions when those workflows have reviewed projections |
| Authenticated `/api/manufacturer/orders` and `/manufacturer/orders` render real paginated orders, held/quoted amounts, fulfilment and readiness | Add the declared surface to the generic shell navigation when it gains a vertical surface hook |
| A commissioned native API turn used the existing Codex transport and authenticated membership to read a real catalogue item and the empty order database with read-only authority | Add reviewed write authority only for operator workflows that require it |
| `run_stage_plan` reads a compact stage index or one stage's instructions, intended model profile and evidence gate on demand; `run_read(stage_runs)` supplies recorded progress | Native stage execution still depends on the available reviewed host adapters |

The development pack now keeps two manifests. The published b512 harness reads the unchanged
`pack.json`; the current 23d managed harness selects `vertical.json`, which declares the bounded
`catalogue_readiness` recipe. Its Luna catalogue reader and Astra readiness judge have read-only
company tools and separate finite role allowances. The durable recipe record is a review record:
it does not replace the original stage dependencies, perform ingestion or booking, or complete the
full onboarding run. `run_stage_plan` remains a planning read in both runtimes; the current harness
uses `delegate_job` to apply the two model declarations when the parent explicitly launches them.

Live managed execution remains held. OpenAI support case **17021543** is escalated because the
provider returns `Session budget configuration is not enabled`; the existing 11 October managed
allowances are expired with zero available balance, and managed Agents-session access for the
selected Rocoto project still needs a successful read proof. Do not request another funding record
until the provider enables session budgets. Then verify Luna and Astra project access, commission a
fresh bounded company allowance, and run this pack in a separate current-harness state/build before
changing the published b512 service.

The native service selects `verticals/<ROCOTO_VERTICAL>` inside its own source tree and rejects a
symlinked vertical. `prepare_native_harness.py` uses the harness's existing preview-packaging
selection to copy the tracked shared runtime and assets from the read-only harness checkout. It adds
only the manufacturer's declared files, Python modules, JSON configuration and `web/` assets, then
validates the copied native host and writes the mode-`0600` template/company/database bindings:

```bash
python3 app/src/prototypes/orders/prepare_native_harness.py
```

Issue an access code from that isolated harness build with its ordinary `access` command, using the
same state directory and an `owner` or `operator` membership. The prepared `start-native.sh` selects
the manufacturer vertical, existing founder-local Codex transport and loopback port. Starting and
signing in make no model request; the first chat message is the explicit inference boundary.

The commissioned local proof uses a private sparse checkout of harness commit `b512067f` and one
isolated state directory. It first proved the authenticated Orders surface without inference, then a
commissioned native API turn used the real Codex transport to read a catalogue item and the empty
order database. The read-only company grant remained enforced. This isolated packaged harness is the
proof boundary; a concurrently edited harness checkout is neither its runtime source nor a checkout
blocker.

The generic page returns the declared Orders surface in `/api/harness`, while its JavaScript currently
implements navigation only for the special `cameras` surface. The manufacturer host therefore serves
an interim standalone page at `/manufacturer/orders`, with the exact shared theme, self-hosted
Fraunces wordmark and a link into the native Office chat. Its API derives the principal from the
authenticated session and current workspace, then invokes `orders_list` through the same admitted
native registry. The smallest remaining generic-shell change is a vertical surface link/asset hook;
the order projection and authorization stay in this host module.

## Checks

```bash
ORDERS_HARNESS_SOURCE=/home/peter/wt/rocoto-vcr-fix/harness \
  python3 -m pytest -q app/src/prototypes/orders/tests/test_harness_launcher.py
```

Eleven tests cover the native schema contract, layered bootstrap, legacy flat-pack compatibility, fixed principal/company, SQLite read-only access,
write authority, payload escalation refusal, actual pack/registry reads, company/template binding
and continued JSONL service after an invalid call. The HTTP test proves session authentication,
membership rejection, admitted operator data and protected page assets against the real FastAPI app.
The isolated native proof imports the actual host,
registry and `VerticalFamily`, maps a live operator membership, invokes catalogue and paginated order
reads concurrently, and proves SQLite opens in worker threads. It then revokes membership and proves
the same context is refused. The former HTTP-style adapter is shown to fail the actual native registry
before the adapted family passes. With the environment variable unset, six local checks run and the
four cross-checkout integration tests report skipped explicitly.

The measured stage record is retained with the company run. The stage playbook is generated from
[stages.json](stages.json); see [PLAYBOOK.md](PLAYBOOK.md) and the exact
[imagery contract](imagery.json).

The current Metal-M customer release publishes six finished families, 70 exact catalogue SKUs and
one angled image per family. The full 150-type, 2,751-row catalogue remains in the private company
database for subsequent onboarding. The authenticated HTTPS mail relay delivered in PR 198 is active;
OAuth remains on the operator host and relay authority is scoped to the company outbox operations.
These commissioned pieces do not make the complete manufacturer template self-service.

## Historical optional Agents SDK alternative

`agent_host.py` predates the completed native-host integration. It remains an optional historical
alternative for its local spend-ledger experiments; it is not the manufacturer pack's primary run
path. It uses OpenAI Agents SDK `Agent`, `Runner`, `FunctionTool` and the Responses model adapter.
Trusted startup fixes company, role,
actor and write authority. Each conversation binds that exact capability. History, turns, tool
results, guard/error notes, provider usage and schedules live in `agent-host.sqlite3` in the private
company workspace. SDK tracing and automatic provider retries are disabled. An interrupted turn
keeps its notes and requires operator review before a fresh thread; uncertain provider usage holds
its reservation and blocks further calls until reconciliation.

Install the optional dependency in a dedicated environment:

```bash
python3 -m venv /home/peter/.local/state/rocoto/orders-demo/agent-venv
/home/peter/.local/state/rocoto/orders-demo/agent-venv/bin/pip install \
  -r app/src/prototypes/orders/requirements-agent.txt
```

Copy `model-grant.example.json` to
`/home/peter/.local/state/rocoto/orders-demo/harness/metal-m-model-grant.json`, keep mode `0600`,
and commission these exact fields: Rocoto OpenAI project and ownership evidence; API model IDs for
reader/judge/vision; dated standard input/output prices and conservative input-token bounds;
approved USD total/per-turn limits, request/output limits, grant ID, receipt and Unix expiry.
Session model labels in `stages.json` are never silently treated as API model IDs. Supply the
project's credential as `ROCOTO_ORDERS_OPENAI_API_KEY` through the private process environment.
The existing video credential file is not read by this host. Its location is evidence of that
runtime's configuration, not authorisation to reuse its account.

After that explicit commissioning, this exact command opens a durable local office chat:

```bash
/home/peter/.local/state/rocoto/orders-demo/agent-venv/bin/python \
  -m app.src.prototypes.orders.agent_host \
  --harness-source /home/peter/wt/rocoto-vcr-fix/harness \
  --database /home/peter/.local/state/rocoto/orders-demo/runtime/companies/metal-m/company.db \
  --company metal-m \
  --workspace /home/peter/.local/state/rocoto/orders-demo/harness/metal-m \
  --config /home/peter/.local/state/rocoto/orders-demo/harness/metal-m-model-grant.json \
  --actor peter-local --role operator chat --thread office
```

Use `turn --thread office --message 'Read the current company questions'` for one turn;
`--stage catalogue` selects that stage's model profile and adds its goal/gate as reference text.
It never executes commands from stage JSON or declares a stage gate passed from prose.
Use `schedule --template ready-time --profile judge --runs 4` to activate four due checks;
`tick` runs due work once; `worker` polls every five seconds until the grant expires. Each schedule
keeps its activating principal and grant, waits its template interval after completion, and pauses
on error. A process killed while a schedule runs leaves that schedule held in `running` for review;
startup does not replay it. `status` reads the local journal, including after grant expiry. Money
is reserved before each provider request from commissioned token/rate bounds and settled using
reported usage; changed grants need a new ID. One turn runs per company workspace. Use one
commissioned workspace per company; the journal is the spend ledger for that workspace.

The host exposes the existing company database tools. It provides the latest 100 order IDs/states
to privileged turns so maintenance templates can read individual requests. External page crawling,
code edits, image generation/vision input, sending, publication, larger-order pagination, subagent
delegation and network/UI membership are separate adapters still to connect. Templates requiring
those capabilities must record that limitation. Text/function requests alone are supported;
`vision` profile selection does not add an image input transport. The configured API model and
reported usage are recorded; the SDK response does not independently expose a served model ID.

The published b512 native service still uses `delegate_investigations`, whose children inherit the
parent runtime configuration. Its stage profiles remain planning metadata. The current 23d managed
harness adds declared `delegate_job` roles and binds the two recipe roles to their Luna and Astra
models. Other manufacturer stage profiles remain planning metadata until each has a reviewed role,
read adapter and bounded authority.

Offline proof uses the real SDK loop with a fake `Model` response, native pack loading and real
company tool dispatch. It makes zero inference/provider calls:

```bash
ORDERS_HARNESS_SOURCE=/home/peter/wt/rocoto-vcr-fix/harness \
  PYTHONPATH=app/src/prototypes/orders \
  /tmp/orders-agent-sdk-venv/bin/python -m pytest -q \
  app/src/prototypes/orders/tests/test_agent_host.py \
  app/src/prototypes/orders/tests/test_harness_launcher.py
```

The current managed recipe has an additional offline proof, with no provider request:

```bash
ORDERS_MANAGED_HARNESS_SOURCE=/home/peter/wt/rocoto-vcr-fix/harness \
ORDERS_LEGACY_HARNESS_SOURCE=/tmp/rocoto-harness-b512067f/harness \
python3 -m pytest -q \
  app/src/prototypes/orders/tests/test_manufacturer_recipes.py
```

SDK contract reference: [OpenAI Agents SDK quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python).
