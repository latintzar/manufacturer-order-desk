# Catalogues, quotes and orders for hardware manufacturers

Manufacturer order desk is a sales app for hardware manufacturers. It connects product catalogues, configurable offers and incoming orders, with an agent harness and vertical SDK for continuing the sales workflow.

A customer request needs to become a clear product specification and quote, while catalogues and prices keep changing. Sales needs to keep the original request, chosen parts and quoted values together.

| Feature | What it does |
| --- | --- |
| Order desk | Review requests with customer, pricing, products and source context. |
| Product catalogue | Edit articles and prices through versioned configuration. |
| Public configurator | Choose parts and submit specifications through the saved renderer. |
| Quotes and history | Retain quoted values and inspect or restore configuration history. |
| Agent tools | Use the original vertical SDK and harness integration for the manufacturer domain. |

## Workflow

Customer specification → Product selection → Saved quotation → Order desk → Agent-assisted follow-up

## Design decisions

- Saved quotes keep their quoted values as the catalogue evolves.
- The public configurator and internal desk use the same saved configuration and order store.

## Status and next steps

The native app runs the original services with an authored six-article catalogue and sample requests. Client-owned catalogues, photographs and account data retain their original custody. Connected models and providers use your own setup. Load an owned manufacturer catalogue, configure its specification flow and commission the domain tools.

Source: [docs/architecture.md](../docs/architecture.md), [docs/workflows.md](../docs/workflows.md), [docs/setup.md](../docs/setup.md).
