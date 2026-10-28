---
name: manufacturer-order-desk
description: Run, inspect or extend the native manufacturer catalogue, order and shared-configurator project. Use its isolated first result, source contracts and recipient-owned credential tools.
---

# Manufacturer order desk

Read `README.md`, `docs/SETUP.md` and the relevant flow in `docs/ARCHITECTURE.md` first. `docs/UX.md` records the actual interaction decisions. The function reference maps implementation entry points.

## First result

Use Python 3.12 and Node 22. Install `requirements.lock` in a fresh virtual environment and run `tools/dev.py`. It creates an authored sample in an empty owned directory, prints the workspace/configurator URLs and saves a one-use code in its private code file. Read that file directly for local browser sign-in; keep its value out of tool output and messages.

The first result clears inherited provider/state settings and restricts server networking to loopback. It uses the real `CompanyStore`, pricing code, private source bridge and native workspace components. Sample images and requests are authored fixtures. Preserve the public widget, internal editor and versioned source relationship.

## Credentials

Select the recipient company and state before selecting credentials. Use `tools/configure.py` with hidden terminal input or the recipient’s secret manager. `--openai` stores the recipient key. `--generate-orders-token` creates the private bridge secret. Values stay outside source, command arguments, screenshots, logs and chat.

`tools/bind.py` writes one company’s source binding. `tools/serve.py` loads only the explicitly selected private directory and role. It keeps funding, membership, current-authority and outbound-effect checks. `docs/INTEGRATIONS.md` distinguishes local workflows from commissioned provider interfaces.

## Work by module

- Public selection and checkout: `app/src/prototypes/orders/widget/` and `serve.py`.
- Trusted prices and orders: `quote.mjs`, `quote.py`, `store.py`, `platform_orders.py`.
- Source bridge and exact publication: `manufacturer_source_http.py`, `manufacturer_publish.py`, `configurator_versions.py`.
- Full editor snapshots and restore: `manufacturer_store.py`, `manufacturer_preview.py` and manufacturer native browser modules.
- Staff retry identity: `manufacturer-new-order.js`, `manufacturer_manual_orders.py`.
- Original files: `manufacturer_source_files.py`, `manufacturer_order_files.py`, `order_files.py`.
- Shared admission and runtime: `harness/mechanics/`, `runtime/`, `sdk/`.

## Preserve the contracts

A quotation needing a price keeps `total: null`; priced zero stays zero. Existing orders retain their saved prices. Publish only a complete saved version with its matching revision/hash receipt. Restore creates another immutable revision. Staff retries reuse the same saved command and idempotency key. Recheck membership inside mutations; resolve files through exact company ownership. Receiving allocations and dispatch warehouses are different fields.

English reads/edits preserve other languages. Keep actual components and functional copy. Use authored fixtures when demonstrating changes and retain provenance. The original source authority, other companies’ accounts/state and existing Vitrina services remain outside this extracted project.

Run the relevant local tests and browser flow. Keep provider, GPU, sending, payment and deployment effects behind their own explicit recipient authority. Record concrete evidence and remaining integration limits in the owning repository.

[made by atelier neyra](https://atelierneyra.com)
