# Setup

## Local first result

Python 3.12, Node 22 and the packages in `requirements.lock` run both services. `tools/dev.py` creates a private `.local/first-result/` directory and prints the two local URLs and the path to a one-use sign-in code. The key itself stays in that file.

The printed editor URL includes `operator=1`, which selects the owner editing presentation. Native role checks authorize every read and write. The ordinary URL opens the browsing presentation.

The sample uses the original SQLite writers, shared widget/pricing engine, source bridge and native workspace. Reopening the same directory preserves your work. Choose another empty directory to start again:

```sh
.venv/bin/python tools/dev.py --state /absolute/path/new-sample
```

`--workspace-port` and `--orders-port` select two different local ports. The sample clears inherited provider and state environment settings and uses its loopback-only network boundary. Its randomly generated bridge secret stays in the private sample directory.

## Databases and files

| State | Location in the first result | Authority |
| --- | --- | --- |
| Company catalogue and orders | `orders/companies/sample-hardware/company.db` | `CompanyStore`, including immutable price, estimate and order events |
| Published configurations | `orders/companies/sample-hardware/configurator-versions.sqlite` | Hash/revision-bound Orders receiver |
| Workspace state | `workspace/` | Native membership, files, conversations, capabilities and full configuration snapshots |
| Public widget | `public/sample-hardware/rocoto/` | Bundled original renderer and public catalogue |
| Credentials | `local-credentials.json` | Owner-only transport credential for these two sample processes |

SQLite schemas are created by their owning classes. `CompanyStore.SCHEMA` and `ManufacturerStore.__init__` are the source of truth. The optional PostgreSQL journal source and migrations remain in `backend/realtime/`; this local result uses its SQLite path. This project uses native membership and SQLite rather than a Supabase project.

## Your company

Start with the configuration in `tools/sample_build.py`. Replace the catalogue, company configuration, questions, checkout settings and public artwork with your own inputs. `CompanyStore.ingest_catalog` admits source-backed articles. The public widget and server share `quote.mjs`; existing order quotes keep their saved amounts when the catalogue changes.

The original pipeline in `app/src/prototypes/orders/pipeline/` also retains source mirroring, catalogue extraction and reviewed publication tools. Their selected source, credentials and output cache belong to the company being configured. The default cache in this release is `~/.local/state/manufacturer-order-desk/orders-cache`; `ROCOTO_ORDERS_CACHE` selects an explicit alternate directory.

Each service keeps its own absolute state directory. The workspace reads Orders through a company-scoped authenticated HTTP binding. A direct database binding remains a read-only option in `manufacturer_source_http.source_for`.

## Private credentials

Use hidden terminal input for a recipient OpenAI key:

```sh
.venv/bin/python tools/configure.py --directory /absolute/private/config --openai
```

Create the private transport token shared by your two services:

```sh
.venv/bin/python tools/configure.py --directory /absolute/private/config --generate-orders-token
```

The directory has mode `0700`; `credentials.json` has mode `0600`. The helper checks its schema, owner, regular-file type and link count. It prints the saved path. Agents should use this helper or the recipient’s secret manager and keep values out of messages, source and command arguments.

Bind a workspace to the company slug used by its Orders database:

```sh
.venv/bin/python tools/bind.py --workspace-state /absolute/workspace \
  --company sample-hardware --keys-directory /absolute/private/config
```

The command writes the three-field `manufacturer-source.json` binding and returns the non-secret company scope. Use that scope when starting the Orders receiver.

## Serve recipient-owned services

Run each command in its own process:

```sh
.venv/bin/python tools/serve.py --role orders --port 18581 \
  --state /absolute/orders --public-directory /absolute/public \
  --company sample-hardware --company-scope YOUR_SCOPE \
  --orders-origin https://orders.example.test \
  --keys-directory /absolute/private/config
```

```sh
.venv/bin/python tools/serve.py --role workspace --port 18580 \
  --state /absolute/workspace --orders-origin https://orders.example.test \
  --public-origin https://workspace.example.test \
  --keys-directory /absolute/private/config
```

Both processes bind to 127.0.0.1 for a recipient-owned HTTPS reverse proxy. `MANUFACTURER_ORDERS_ORIGIN` is the exact Orders origin. The wrapper passes that explicit value; plain HTTP is accepted for loopback development. Source URLs remain fixed to that configured origin, and redirects remain blocked.

The Orders public directory contains `COMPANY/rocoto/site.json`, its widget, configuration and catalogue. Its state contains `companies/COMPANY/company.db`. The public prefix is the company slug. The sample builder demonstrates those exact contracts using authored data.

The workspace’s public origin supplies its allowed host and hosted authentication context. Native one-use codes remain available through `AccessStore`; hosted identity uses the retained provider contract when commissioned. Keys alone retain the existing model, funding and outbound-effect admission checks. See [integrations](INTEGRATIONS.md).


## Hosting and sessions

Use a separate origin for the editable workspace, with its API on the same origin. The original native session cookie is `rocoto_session`, scoped to `/`. When several projects share one preview origin, the reverse proxy must rewrite that cookie path to the workspace mount, for example `/apps/manufacturer-order-desk/`, and keep its API prefix within that mount. The static native sample is session-free and serves fixed read-only data; it can share the Atelier preview host.

## Hosted native sample

`tools/dev.py --guest --base-path /apps/manufacturer-order-desk/` runs the same native services with automatic browse membership, scoped cookies and server-enforced read-only access. Its pricing endpoint remains the original local calculator. Use the [deployment guide](../deploy/README.md) for the single-server unit, exact API/asset prefixes, private state and HTTPS origin. Running without `--guest` keeps the owner editing workflow.

[made by atelier neyra](https://atelierneyra.com)
