# Validation

The release was checked on 28 October 2026 with an isolated, newly authored Sample Hardware company. The source pins and extraction boundaries are in [provenance](../provenance/README.md).

## Runtime and source

A fresh Python 3.12 virtual environment installed the locked CPU dependencies; `pip check` passed. The actual Node 22.21.1 executable was checksum-verified. The two original services started from a fresh owned directory, generated their SQLite databases, rendered the original widget and communicated through their authenticated company-scoped HTTP bridge.

The final proof runs the source files verified against the release candidate. It uses six authored catalogue articles, two initial requests and generated hardware images. The launcher clears inherited provider configuration and installs a Python socket boundary that permits loopback. Browser requests are independently restricted to loopback. The retained pure JavaScript pricing engine runs locally.

## Tests

- **279 manufacturer and recipient-configuration checks** cover company scope, capabilities, roles, files, correspondence, immutable snapshots, renderer pinning, publication, restore, staff command retry and private credential/origin handling.
- **402 Orders checks and 11 subtests** cover the retained generic producer, stores, pricing, specifications, contracts and native request flows. Eleven optional acceptance checks are skipped in the CPU environment.
- Python source parses, native JavaScript syntax, the agent skill format and local guide/source links pass their gates.

Client catalogue, client research fixtures and owner-bound operations scripts are identified in `provenance/omitted-client-material.json`. Their original source remains with its owner. Generic engine tests and required shared SDK dependencies are included.

## Browser and persisted workflows

The actual Orders, Customers, Products and Configurator screens were checked at 1600, 390 and 320 pixels. All twelve views rendered without JavaScript errors, failed requests, external requests, broken images or horizontal page overflow. The public configurator also rendered its three authored product illustrations.

The running source saved a lever price of €26, published it to the public catalogue, then restored the original immutable version and its €24 price. Previously saved order snapshots retained their exact values. A staff command submitted twice created one order. The original text specification remained attached to that order.

To repeat the browser check after starting a fresh sample:

```sh
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python tools/check_browser.py \
  --code-file .local/first-result/owner-code.txt
```

The check consumes a local one-use code. Its screenshots and report stay in `.local/browser-proof/`; it writes no session-cookie export.

## Preview and integration boundary

The distributable native presentation uses authored GET snapshots and the original native components. Its fixture adapter exposes read-only actor permissions, holds mutation requests and uses no authentication cookie or provider key. The runnable source first result supports actual local writes and persistence.

Recipient-hosted OpenAI, managed authentication, funding, SMTP, Chatwoot, catalogue scraping and production deployment need their own provider configuration and acceptance. Their source and admission mechanisms are retained; the release proof covers local CPU workflows. The optional PostgreSQL journal is included as source and migrations; this result exercises SQLite.

The secret scan has one known finding in the byte-pinned upstream Mermaid bundle. Its exact rule, path, line and file hash are recorded in `provenance/secret-scan-disposition.json`; all other findings require review. The source archive excludes private state, cookies, credentials, databases, uploads and dependency environments.

[made by atelier neyra](https://atelierneyra.com)
