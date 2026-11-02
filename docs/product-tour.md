# Product tour

Manufacturer Order Desk is an AI-native order desk for construction materials manufacturers working across web and email. Customers configure products and request quotes online; the sales team keeps incoming orders, product options and email requests in the same workflow.

A customer request needs to become a clear product specification and quote, while catalogues and prices keep changing. Sales needs to keep the original request, chosen parts and quoted values together.

## A specification becomes a reviewed quote

1. **Specify the products.** A customer opens the company-branded public configurator, chooses catalogue items or completes the questionnaire, and supplies the specification. Staff can enter the same kind of request from the order desk.
2. **Keep the original request.** The order service saves customer details, product choices, quantities and an original attachment. Receiving locations and the supplier’s dispatch warehouse retain their separate meanings.
3. **Review the quote.** In Orders, inspect the request, its original document and the priced lines. Articles marked “on request” remain visibly awaiting quotation; the priced subtotal remains separate.
4. **Discuss a specific proposal.** Prepare quantities, prices, delivery and a customer note as one proposal. Its customer-review link identifies that version, so confirmation or a requested change stays attached to the terms.
5. **Maintain the selling surface.** Update a product price or configurator question, preview the saved full snapshot, then publish that exact revision to the public application. History can restore an earlier snapshot as a new revision.

The local first result runs the real public configurator, order service and staff workspace using an authored six-article Sample Hardware catalogue. Email delivery and agent-assisted editing use separately configured accounts and capabilities.

## Product areas

| Area | What you do | Result |
| --- | --- | --- |
| Orders | Review requests, enter staff orders and inspect their documents. | The original customer request and commercial record stay together. |
| Customers | Follow a customer’s orders and proposal conversation. | A team can recover the context behind a quote. |
| Products | Edit articles, prices and quotation flags. | The catalogue and configurator share a versioned full document. |
| Configurator | Edit appearance, questions and choices; inspect history. | A preview shows the selected saved version, and publication acknowledges that exact snapshot. |
| Customer review | Share and discuss a specific proposal. | Acceptance and requested changes refer to identifiable terms. |
| Agent tools and correspondence | Let admitted tools work with the manufacturer’s records. | Managed execution, email and helpdesk adapters use explicit company scope and setup. |

## Design decisions

- **Quotes keep their commercial meaning.** Unknown prices retain an awaiting-quote state. A numeric zero remains a real price, and a partial subtotal stays distinguishable from the complete total.
- **Restore means the whole snapshot.** Questions, translations, products and prices travel together. Restoring a version preserves the intervening history.
- **Retries keep one request identity.** The staff form retains its draft and immutable pending command. An unchanged retry resolves the saved command rather than creating another request.
- **The original specification remains inspectable.** Source files and spreadsheet-cell references give the team evidence for resolving an ambiguous product, quantity or destination.

## Reached stage

The native local app persists manual catalogue, order, quote and configuration workflows through its actual services. The hosted visitor uses authored sample records. Client-owned catalogues, photographs and account data retain their original custody. Load your own catalogue and configure managed editing, email, customer research or Chatwoot against the retained integration contracts.

## Local walkthrough

1. Open **Orders**, then a request. Compare its products, customer, pricing and original context.
2. Open **Products** and change a unit price. The shared configuration saves an immutable version.
3. Open **Configurator**. Edit appearance or questions, inspect the actual saved renderer, open history and restore a version.
4. Use **New order** to enter a customer, catalogue articles, warehouse and original specification. A saved command retains its identity through interrupted retries.
5. Use the public configurator to select parts or send a specification. Requests arrive in the same company order store.

Quoted amounts retain their saved values. A request needing a price keeps `total: null`; a priced zero remains zero. Receiving allocations remain distinct from the dispatch warehouse.

## Modules

| Source | Responsibility |
| --- | --- |
| [Public configurator](../app/src/prototypes/orders/widget/) | Present product selection and specification entry. |
| [Order authority](../app/src/prototypes/orders/store.py) | Persist customer requests, audit events and idempotent commands. |
| [Pricing](../app/src/prototypes/orders/quote.py) | Calculate catalogue-backed quotes with the shared pricing implementation. |
| [Company bridge](../harness/verticals/manufacturer/manufacturer_source_http.py) | Bind the workspace to one configured order service and company. |
| [Order projection](../harness/verticals/manufacturer/manufacturer_order.py) | Present pricing, fulfilment and original request context. |
| [Configuration versions](../harness/verticals/manufacturer/manufacturer_store.py) | Save and restore immutable full snapshots. |
| [Saved preview](../harness/verticals/manufacturer/manufacturer_preview.py) | Render the chosen snapshot with its verified picker bundle. |
| [Domain tools](../harness/verticals/manufacturer/manufacturer_tools.py) | Expose admitted manufacturer actions through the vertical SDK. |

## Setup and implementation

[Setup](SETUP.md) · [Architecture](ARCHITECTURE.md) · [UX decisions](UX.md) · [Integrations](INTEGRATIONS.md) · [Function reference](reference/index.md) · [Validation](VALIDATION.md) · [Agent skill](../skills/manufacturer-order-desk/SKILL.md)

[made by atelier neyra](https://atelierneyra.com)
