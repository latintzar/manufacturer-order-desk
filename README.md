# Manufacturer order desk

Manufacturer order desk is a workspace for manufacturer sales orders, product selection and catalogue editing.

![The native catalogue workspace with authored sample products](docs/images/workspace.png)

## Run it

Use Python 3.12 and Node 22:

```sh
git clone https://github.com/latintzar/manufacturer-order-desk.git
cd manufacturer-order-desk
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python tools/dev.py
```

Open the workspace at **http://127.0.0.1:18580/?operator=1**. Its one-use sign-in code is saved in `.local/first-result/owner-code.txt`. Open the public configurator at **http://127.0.0.1:18581/sample-hardware/#order**.

The first result contains an authored Sample Hardware catalogue, six articles and two requests. It runs the actual services, persists changes in your local directory and restricts network access to loopback. Product artwork is generated sample content; the original client catalogue, photographs, documents and account state stay with their owner.

## Try the workflows

1. Open **Orders**, then a request. Compare its products, customer, pricing and original context.
2. Open **Products** and change a unit price. The shared configuration saves an immutable version.
3. Open **Configurator**. Edit appearance or questions, inspect the actual saved renderer, open history and restore a version.
4. Use **New order** to enter a customer, catalogue articles, warehouse and original specification. A saved command retains its identity through interrupted retries.
5. Use the public configurator to select parts or send a specification. Requests arrive in the same company order store.

Quoted amounts retain their saved values. A request needing a price keeps `total: null`; a priced zero remains zero. Receiving allocations remain distinct from the dispatch warehouse.

## Guides

- [Setup and recipient credentials](docs/SETUP.md)
- [Architecture and workflows](docs/ARCHITECTURE.md)
- [UX decisions](docs/UX.md)
- [Function and route reference](docs/reference/index.md)
- [Agent guide](skills/manufacturer-order-desk/SKILL.md)
- [Source provenance and changes](provenance/README.md)
- [Dependency licences](THIRD-PARTY.md)

## Source layout

| Path | Responsibility |
| --- | --- |
| `app/src/prototypes/orders/` | Public widget, pricing, specification processing and authoritative `CompanyStore` |
| `harness/verticals/manufacturer/` | Orders, customers, products, configurator, correspondence and company-scoped source bridge |
| `harness/runtime/`, `mechanics/`, `sdk/` | Complete pinned shared workspace runtime, policy, files, tools and admission mechanisms |
| `harness/web/` | Native browser shell and shared components |
| `backend/realtime/` | Retained PostgreSQL journal support; the first result uses SQLite |
| `tools/` | Isolated first result, hidden key input and recipient-owned service entry points |
| `fixtures/sample-hardware/` | Newly authored sample artwork and provenance |

## Deployment and integrations

The two services can run independently against recipient-owned state. [Setup](docs/SETUP.md) explains their source binding, private transport token, public origins, databases and files.

Manual catalogue and order workflows run locally. The retained managed-agent, hosted identity, billing, email and Chatwoot interfaces have their own credentials, admission and commissioning contracts. The [integration guide](docs/INTEGRATIONS.md) maps those boundaries to source. The sample keeps its manual workspace capabilities and performs zero model or outbound-mail calls.

## Checks

```sh
ROCOTO_VERTICAL=manufacturer .venv/bin/python -m pytest -q harness/tests/test_manufacturer_*.py tests
.venv/bin/python -m pytest -q app/src/prototypes/orders/tests
```

[Validation](docs/VALIDATION.md) records the precise tested subset, browser proof and optional acceptance limits. Original client-specific research presentation fixtures remain private; generic store, role, retry, pricing, file and revision contracts are retained.

## Licence

[MIT](LICENSE) covers Peter Neyra’s original code. Upstream components retain their own notices and terms, including the PDF worker’s PyMuPDF dependency. See [THIRD-PARTY.md](THIRD-PARTY.md).

[made by atelier neyra](https://atelierneyra.com)
