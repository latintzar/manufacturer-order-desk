# Manufacturer Order Desk

An AI-native order desk for construction materials manufacturers working across web and email

Manufacturer Order Desk is an AI-native order desk for construction materials manufacturers working across web and email. Customers configure products and request quotes online; the sales team keeps incoming orders, product options and email requests in the same workflow.

[Website](https://atelierneyra.com/manufacturer-order-desk) · [Open demo](https://preview.atelierneyra.com/apps/manufacturer-order-desk/) · [Product tour](docs/product-tour.md) · [Documentation](https://docs.atelierneyra.com/manufacturer-order-desk/overview/)

[![Construction-materials configurator showing steel-tube options and a priced basket beside the mobile order list](https://atelierneyra.com/assets/product-motion-v4/manufacturer-order-desk.jpg)](https://preview.atelierneyra.com/apps/manufacturer-order-desk/)

## A specification becomes a quote

1. **Choose products or send a specification.** The company-branded configurator accepts catalogue selections, questionnaire answers and original documents.
2. **Review the request in Orders.** Keep the customer, chosen parts, quantities, prices and original specification together.
3. **Discuss a saved proposal.** A customer-review link identifies the terms being confirmed or changed. Email delivery uses your configured sender.
4. **Keep the catalogue current.** Edit products or configurator questions, preview the saved snapshot and publish that exact revision. History can restore a previous snapshot as a new version.

## Product areas

| Area | What it does |
| --- | --- |
| Orders | Review requests, create staff orders and inspect original specifications. |
| Customers | Follow order history and the conversation behind a proposal. |
| Products | Maintain articles, prices and items awaiting quotation. |
| Configurator | Edit appearance, questions and choices; preview, publish and restore full versions. |
| Customer review | Keep confirmation and requested changes attached to a particular proposal. |
| Agent tools and correspondence | Continue the same workflow through scoped tools, email and helpdesk adapters. |

The native first result runs the real services with an authored six-article catalogue and sample requests. Connected agents and email use your own accounts, with their configuration and acceptance checks.

[Product tour](docs/product-tour.md) follows the complete customer-to-desk journey and links every area to its implementation.

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

## Guides

- [Product tour and modules](docs/product-tour.md)
- [Setup and your service credentials](docs/SETUP.md)
- [Architecture and workflows](docs/ARCHITECTURE.md)
- [UX decisions](docs/UX.md)
- [Function and route reference](docs/reference/index.md)
- [Agent guide](skills/manufacturer-order-desk/SKILL.md)
- [Source provenance and changes](provenance/README.md)
- [Dependency licences](THIRD-PARTY.md)

## Licence

[MIT](LICENSE) covers Peter Neyra’s original code. Upstream components retain their own notices and terms, including the PDF worker’s PyMuPDF dependency. See [THIRD-PARTY.md](THIRD-PARTY.md).

[made by atelier neyra](https://atelierneyra.com)
