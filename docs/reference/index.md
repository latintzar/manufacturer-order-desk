# Source reference

The [architecture](../ARCHITECTURE.md) explains the connected services; the [UX guide](../UX.md) explains their interactions. [source-index.json](source-index.json) contains every indexed definition, source line and route handler. Anonymous callbacks remain beside their call sites.

## Manufacturer workspace

| Module | Named definitions | Responsibility |
| --- | ---: | --- |
| [harness/verticals/manufacturer/manufacturer_agent_edits.py](../../harness/verticals/manufacturer/manufacturer_agent_edits.py) | 8 | Bounded agent views and server-side edits of the existing complete snapshot. |
| [harness/verticals/manufacturer/manufacturer_chatwoot.py](../../harness/verticals/manufacturer/manufacturer_chatwoot.py) | 35 | Company-bound headless Chatwoot CE application API (v4.18.0). |
| [harness/verticals/manufacturer/manufacturer_chatwoot_routes.py](../../harness/verticals/manufacturer/manufacturer_chatwoot_routes.py) | 9 | Private configuration, native admission and signature-first Chatwoot ingress. |
| [harness/verticals/manufacturer/manufacturer_conversation_routes.py](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py) | 19 | Authenticated human service/customer conversations for a manufacturer workspace. |
| [harness/verticals/manufacturer/manufacturer_conversations.py](../../harness/verticals/manufacturer/manufacturer_conversations.py) | 43 | Company-bound human correspondence and immutable customer request reviews. |
| [harness/verticals/manufacturer/manufacturer_customer_portal.py](../../harness/verticals/manufacturer/manufacturer_customer_portal.py) | 38 | Narrow customer review and phone capabilities, separate from workspace access. |
| [harness/verticals/manufacturer/manufacturer_email_analysis.py](../../harness/verticals/manufacturer/manufacturer_email_analysis.py) | 9 | Funded, bounded reply analysis and narrow exact-version assent admission. |
| [harness/verticals/manufacturer/manufacturer_fulfillment.py](../../harness/verticals/manufacturer/manufacturer_fulfillment.py) | 12 | Human-reported fulfillment, independent of the read-only source's reservations. |
| [harness/verticals/manufacturer/manufacturer_host.py](../../harness/verticals/manufacturer/manufacturer_host.py) | 61 | Manufacturer vertical installation, native admission and company-scoped HTTP routes. |
| [harness/verticals/manufacturer/manufacturer_mail.py](../../harness/verticals/manufacturer/manufacturer_mail.py) | 41 | Owned-domain customer email, isolated from workspace membership and agent authority. |
| [harness/verticals/manufacturer/manufacturer_mail_routes.py](../../harness/verticals/manufacturer/manufacturer_mail_routes.py) | 26 | Private per-workspace email commissioning, signed ingress and bounded delivery worker. |
| [harness/verticals/manufacturer/manufacturer_manual_orders.py](../../harness/verticals/manufacturer/manufacturer_manual_orders.py) | 2 | Admitted staff orders: deterministic validation and the company's Orders command. |
| [harness/verticals/manufacturer/manufacturer_order.py](../../harness/verticals/manufacturer/manufacturer_order.py) | 4 | Read-only order presentation shared by the two independently packaged consumers. |
| [harness/verticals/manufacturer/manufacturer_order_files.py](../../harness/verticals/manufacturer/manufacturer_order_files.py) | 6 | Read original order attachments through the workspace's exact company binding. |
| [harness/verticals/manufacturer/manufacturer_preview.py](../../harness/verticals/manufacturer/manufacturer_preview.py) | 9 | Isolated previews of saved configurator documents using a pinned real widget renderer. |
| [harness/verticals/manufacturer/manufacturer_publish.py](../../harness/verticals/manufacturer/manufacturer_publish.py) | 5 | Deliver a saved company version to its commissioned Orders receiver and retain its receipt. |
| [harness/verticals/manufacturer/manufacturer_seed.py](../../harness/verticals/manufacturer/manufacturer_seed.py) | 1 | Explicit synthetic QA source for a fresh, isolated manufacturer workspace. |
| [harness/verticals/manufacturer/manufacturer_source.py](../../harness/verticals/manufacturer/manufacturer_source.py) | 11 | Deterministic manufacturer request briefs and company-scoped customer records. |
| [harness/verticals/manufacturer/manufacturer_source_files.py](../../harness/verticals/manufacturer/manufacturer_source_files.py) | 7 | Company source documents, stored in native ChatFiles and read with native file tools. |
| [harness/verticals/manufacturer/manufacturer_source_http.py](../../harness/verticals/manufacturer/manufacturer_source_http.py) | 13 | Company-bound read transport to the owning Orders service, without database file access. |
| [harness/verticals/manufacturer/manufacturer_source_reader.py](../../harness/verticals/manufacturer/manufacturer_source_reader.py) | 1 | Bounded subprocess for inert source-document extraction; never imports the app. |
| [harness/verticals/manufacturer/manufacturer_store.py](../../harness/verticals/manufacturer/manufacturer_store.py) | 33 | Owned manufacturer drafts and a read-only adapter for the public CompanyStore schema. |
| [harness/verticals/manufacturer/manufacturer_tools.py](../../harness/verticals/manufacturer/manufacturer_tools.py) | 5 | Native manufacturer tools use the same admitted document store as manual editing. |
| [harness/verticals/manufacturer/origin_config.py](../../harness/verticals/manufacturer/origin_config.py) | 1 | The recipient's exact Orders origin; plain HTTP is limited to loopback development. |
| [harness/verticals/manufacturer/research_queue.py](../../harness/verticals/manufacturer/research_queue.py) | 38 | Order evidence in the native agent ledger, consumed by the native scheduler. |
| [harness/verticals/manufacturer/research_tools.py](../../harness/verticals/manufacturer/research_tools.py) | 5 | Admitted company research tools for the Organization and its saved agents. |
| [harness/verticals/manufacturer/web/manufacturer-conversations.js](../../harness/verticals/manufacturer/web/manufacturer-conversations.js) | 17 |  |
| [harness/verticals/manufacturer/web/manufacturer-customer-portal.js](../../harness/verticals/manufacturer/web/manufacturer-customer-portal.js) | 17 |  |
| [harness/verticals/manufacturer/web/manufacturer-customers.js](../../harness/verticals/manufacturer/web/manufacturer-customers.js) | 30 |  |
| [harness/verticals/manufacturer/web/manufacturer-files.js](../../harness/verticals/manufacturer/web/manufacturer-files.js) | 13 |  |
| [harness/verticals/manufacturer/web/manufacturer-new-order.js](../../harness/verticals/manufacturer/web/manufacturer-new-order.js) | 22 |  |
| [harness/verticals/manufacturer/web/manufacturer-order-files.js](../../harness/verticals/manufacturer/web/manufacturer-order-files.js) | 8 |  |
| [harness/verticals/manufacturer/web/manufacturer-order-review.js](../../harness/verticals/manufacturer/web/manufacturer-order-review.js) | 10 |  |
| [harness/verticals/manufacturer/web/manufacturer-preview.js](../../harness/verticals/manufacturer/web/manufacturer-preview.js) | 2 |  |
| [harness/verticals/manufacturer/web/manufacturer-products.js](../../harness/verticals/manufacturer/web/manufacturer-products.js) | 32 |  |
| [harness/verticals/manufacturer/web/manufacturer-shell.js](../../harness/verticals/manufacturer/web/manufacturer-shell.js) | 15 |  |
| [harness/verticals/manufacturer/web/manufacturer-tabs.js](../../harness/verticals/manufacturer/web/manufacturer-tabs.js) | 98 |  |

## Orders and public widget

| Module | Named definitions | Responsibility |
| --- | ---: | --- |
| [app/src/prototypes/orders/agent_host.py](../../app/src/prototypes/orders/agent_host.py) | 17 | Private local manufacturer agent host. Optional dependency: requirements-agent.txt. |
| [app/src/prototypes/orders/build_preview.py](../../app/src/prototypes/orders/build_preview.py) | 7 | Build the orders preview: each company's homepage with its order page on top. |
| [app/src/prototypes/orders/commission.py](../../app/src/prototypes/orders/commission.py) | 2 | Initialize a company's persistent store from a reviewed built catalogue, once. |
| [app/src/prototypes/orders/configurator_versions.py](../../app/src/prototypes/orders/configurator_versions.py) | 12 | Authenticated, company-bound immutable configuration publication for the native platform. |
| [app/src/prototypes/orders/customer_details.py](../../app/src/prototypes/orders/customer_details.py) | 6 | Validate public checkout context retained with the customer's order. |
| [app/src/prototypes/orders/customer_mail.py](../../app/src/prototypes/orders/customer_mail.py) | 37 | Private customer links and a held, threaded transactional email outbox. |
| [app/src/prototypes/orders/customer_page.py](../../app/src/prototypes/orders/customer_page.py) | 1 | Private capability-backed customer order page; served without customer data. |
| [app/src/prototypes/orders/examples/make_constellation.py](../../app/src/prototypes/orders/examples/make_constellation.py) | 9 | Write the example drawing for laser cutting: the two Dippers in a round steel plate. |
| [app/src/prototypes/orders/harness_launcher.py](../../app/src/prototypes/orders/harness_launcher.py) | 7 | Isolated manufacturer tool host using the native harness's actual pack and registry. |
| [app/src/prototypes/orders/laser.py](../../app/src/prototypes/orders/laser.py) | 71 | Read a drawing a customer uploads for laser cutting and say what a workshop needs to know. |
| [app/src/prototypes/orders/laser_quote.mjs](../../app/src/prototypes/orders/laser_quote.mjs) | 4 |  |
| [app/src/prototypes/orders/laser_quote.py](../../app/src/prototypes/orders/laser_quote.py) | 5 | The laser-cutting estimate: one formula, written here and in laser_quote.mjs. |
| [app/src/prototypes/orders/mail_relay.py](../../app/src/prototypes/orders/mail_relay.py) | 8 | Private HTTPS-to-Gmail relay; OAuth remains with the commissioned local operator. |
| [app/src/prototypes/orders/mail_transport.py](../../app/src/prototypes/orders/mail_transport.py) | 12 | Authenticated HTTPS boundary for the private transactional-mail outbox. |
| [app/src/prototypes/orders/manufacturer.py](../../app/src/prototypes/orders/manufacturer.py) | 8 | The executable manufacturer stage contract and its generated readable playbook. |
| [app/src/prototypes/orders/manufacturer_host.py](../../app/src/prototypes/orders/manufacturer_host.py) | 22 | Native harness composition for one bound manufacturer company database. |
| [app/src/prototypes/orders/order_assistant.py](../../app/src/prototypes/orders/order_assistant.py) | 6 | Bounded Responses requests for customer specification and proposal text. |
| [app/src/prototypes/orders/order_files.py](../../app/src/prototypes/orders/order_files.py) | 22 | Private design-file staging and order attachment access. |
| [app/src/prototypes/orders/orders_tools.py](../../app/src/prototypes/orders/orders_tools.py) | 6 | Manufacturer family in the native harness's specs/read/call contract. |
| [app/src/prototypes/orders/origin_config.py](../../app/src/prototypes/orders/origin_config.py) | 1 | The recipient's exact Orders origin; plain HTTP is limited to loopback development. |
| [app/src/prototypes/orders/packs/manufacturer/web/manufacturer_orders.js](../../app/src/prototypes/orders/packs/manufacturer/web/manufacturer_orders.js) | 10 |  |
| [app/src/prototypes/orders/pipeline/ask.py](../../app/src/prototypes/orders/pipeline/ask.py) | 22 | Check a company's questionnaire against its catalogue, at build time. |
| [app/src/prototypes/orders/pipeline/bundle.py](../../app/src/prototypes/orders/pipeline/bundle.py) | 7 | Bundle the shared widget with one company's config into a single script. |
| [app/src/prototypes/orders/pipeline/catalog.py](../../app/src/prototypes/orders/pipeline/catalog.py) | 12 | Read a company's published price list into the catalogue the order page ships with. |
| [app/src/prototypes/orders/pipeline/check.py](../../app/src/prototypes/orders/pipeline/check.py) | 10 | Open the built preview in a browser and order something, at desktop and at phone width. |
| [app/src/prototypes/orders/pipeline/check_business_flow.py](../../app/src/prototypes/orders/pipeline/check_business_flow.py) | 4 | Prove literal specification quantities and deliberate proposal choices in disposable local state. |
| [app/src/prototypes/orders/pipeline/check_capture.py](../../app/src/prototypes/orders/pipeline/check_capture.py) | 5 | Prove questionnaire needs survive a real checkout in a disposable local store. |
| [app/src/prototypes/orders/pipeline/check_embed.py](../../app/src/prototypes/orders/pipeline/check_embed.py) | 4 | Copy the public script onto a separate origin; inspect the real chooser without order writes. |
| [app/src/prototypes/orders/pipeline/check_pick.py](../../app/src/prototypes/orders/pipeline/check_pick.py) | 5 | Walk a real specification-first widget and its company API at desktop and phone widths. |
| [app/src/prototypes/orders/pipeline/clean.py](../../app/src/prototypes/orders/pipeline/clean.py) | 6 | Clean a mirrored page for a private preview. |
| [app/src/prototypes/orders/pipeline/common.py](../../app/src/prototypes/orders/pipeline/common.py) | 9 | Shared paths and company loading for the orders pipeline. |
| [app/src/prototypes/orders/pipeline/freeze.py](../../app/src/prototypes/orders/pipeline/freeze.py) | 6 | Freeze a client-rendered homepage into static markup. |
| [app/src/prototypes/orders/pipeline/homepage.py](../../app/src/prototypes/orders/pipeline/homepage.py) | 8 | Choose what the preview publishes for one company: its homepage and that page's requisites. |
| [app/src/prototypes/orders/pipeline/imagery.py](../../app/src/prototypes/orders/pipeline/imagery.py) | 6 | Validate anonymous image observations before admitting catalogue material inputs. |
| [app/src/prototypes/orders/pipeline/media.py](../../app/src/prototypes/orders/pipeline/media.py) | 4 | Make small renditions of the heavy media a homepage shows. |
| [app/src/prototypes/orders/pipeline/mirror.py](../../app/src/prototypes/orders/pipeline/mirror.py) | 20 | Mirror a company's public website into the cache, politely. |
| [app/src/prototypes/orders/pipeline/new_company.py](../../app/src/prototypes/orders/pipeline/new_company.py) | 1 | Start a company folder from its website address. |
| [app/src/prototypes/orders/pipeline/pick.py](../../app/src/prototypes/orders/pipeline/pick.py) | 11 | Validate company-owned picker data, source coverage and self-contained drawings. |
| [app/src/prototypes/orders/pipeline/posters.py](../../app/src/prototypes/orders/pipeline/posters.py) | 2 | Draw one poster per catalogue category, so the menu shows every product before three.js loads. |
| [app/src/prototypes/orders/pipeline/prefix.py](../../app/src/prototypes/orders/pipeline/prefix.py) | 13 | Move a mirrored page under its company prefix. |
| [app/src/prototypes/orders/pipeline/questionnaire_conditions.py](../../app/src/prototypes/orders/pipeline/questionnaire_conditions.py) | 4 | Prepare a condition-only update for an existing versioned configurator configuration. |
| [app/src/prototypes/orders/pipeline/studio/__main__.py](../../app/src/prototypes/orders/pipeline/studio/__main__.py) | 1 | Company-scoped CLI for immutable plans, stage gates and native transport receipts. |
| [app/src/prototypes/orders/pipeline/studio/delivery.py](../../app/src/prototypes/orders/pipeline/studio/delivery.py) | 4 | Validate reviewed angled product images before installing a private company cache. |
| [app/src/prototypes/orders/pipeline/studio/frames.py](../../app/src/prototypes/orders/pipeline/studio/frames.py) | 3 | Describe-derived frames and explicit geometry/material composition roles. |
| [app/src/prototypes/orders/pipeline/studio/geometry/catalogue.py](../../app/src/prototypes/orders/pipeline/studio/geometry/catalogue.py) | 5 | Pure catalogue validation and render planning; safe to import outside Blender. |
| [app/src/prototypes/orders/pipeline/studio/geometry/cli.py](../../app/src/prototypes/orders/pipeline/studio/geometry/cli.py) | 2 | CLI for dry runs and one-family technical-reference renders. |
| [app/src/prototypes/orders/pipeline/studio/geometry/scene.py](../../app/src/prototypes/orders/pipeline/studio/geometry/scene.py) | 52 | Studio renders of metal stock with Cycles (offline path tracing), built parametrically. |
| [app/src/prototypes/orders/pipeline/studio/materials.py](../../app/src/prototypes/orders/pipeline/studio/materials.py) | 3 | Evidence-backed surface-zone contract shared by all three product views. |
| [app/src/prototypes/orders/pipeline/studio/planning.py](../../app/src/prototypes/orders/pipeline/studio/planning.py) | 2 | Adapter-independent ownership reconciliation and three-shot coverage planning. |
| [app/src/prototypes/orders/pipeline/studio/queue.py](../../app/src/prototypes/orders/pipeline/studio/queue.py) | 11 | Two-lane, receipt-first queue; unknown submissions are held, never auto-retried. |
| [app/src/prototypes/orders/pipeline/studio/schema.py](../../app/src/prototypes/orders/pipeline/studio/schema.py) | 9 | Versioned studio ledger. Company data and provider credentials remain outside Git. |
| [app/src/prototypes/orders/pipeline/studio/transport.py](../../app/src/prototypes/orders/pipeline/studio/transport.py) | 1 | Provider adapter execution boundary; persist receipt before fetching output bytes. |
| [app/src/prototypes/orders/places.py](../../app/src/prototypes/orders/places.py) | 23 | Address search for the order page's delivery step, with hard ceilings on what it may cost. |
| [app/src/prototypes/orders/platform_orders.py](../../app/src/prototypes/orders/platform_orders.py) | 1 | Authenticated staff intake into the same authoritative company order store. |
| [app/src/prototypes/orders/platform_source.py](../../app/src/prototypes/orders/platform_source.py) | 8 | Read-only order presentation shared by the two independently packaged consumers. |
| [app/src/prototypes/orders/prepare_native_harness.py](../../app/src/prototypes/orders/prepare_native_harness.py) | 8 | Prepare one private native manufacturer harness artifact without starting a model turn. |
| [app/src/prototypes/orders/propose.py](../../app/src/prototypes/orders/propose.py) | 8 | Choose catalogue-backed, compatible articles before requesting narrative text. |
| [app/src/prototypes/orders/public_catalogue.py](../../app/src/prototypes/orders/public_catalogue.py) | 3 | Select the reviewed sales collection while preserving the full company catalogue. |
| [app/src/prototypes/orders/quote.py](../../app/src/prototypes/orders/quote.py) | 1 | Compute trusted server totals with the browser's shared pricing engine. |
| [app/src/prototypes/orders/refresh.py](../../app/src/prototypes/orders/refresh.py) | 12 | Bounded source refresh and deterministic ready-time maintenance for one company. |
| [app/src/prototypes/orders/release_catalogue.py](../../app/src/prototypes/orders/release_catalogue.py) | 3 | Apply one reviewed built catalogue while retaining the existing company's order store. |
| [app/src/prototypes/orders/reviewed_orders.py](../../app/src/prototypes/orders/reviewed_orders.py) | 19 | Atomic operator review and exact customer assent for held order requests. |
| [app/src/prototypes/orders/serve.py](../../app/src/prototypes/orders/serve.py) | 29 | The orders preview's server: the built pages, and the capped address search beside them. |
| [app/src/prototypes/orders/spec.py](../../app/src/prototypes/orders/spec.py) | 20 | Source-backed specification parsing, with bounded private-document extraction. |
| [app/src/prototypes/orders/spec_receipts.py](../../app/src/prototypes/orders/spec_receipts.py) | 2 | Server-retained allocation readings bind confirmation to the submitted original. |
| [app/src/prototypes/orders/spec_workbook.py](../../app/src/prototypes/orders/spec_workbook.py) | 9 | Bounded XLSX cell extraction and arithmetic for customer allocation matrices. |
| [app/src/prototypes/orders/store.py](../../app/src/prototypes/orders/store.py) | 50 | Private per-company SQLite record. Current projections and immutable evidence coexist. |
| [app/src/prototypes/orders/supply.py](../../app/src/prototypes/orders/supply.py) | 7 | One deterministic, timezone-aware ready-window engine for tools and HTTP callers. |
| [app/src/prototypes/orders/tool_cli.py](../../app/src/prototypes/orders/tool_cli.py) | 1 | Local operator CLI. Filesystem access to the private DB is the trust boundary. |
| [app/src/prototypes/orders/tools/seed_praktiker_demo.py](../../app/src/prototypes/orders/tools/seed_praktiker_demo.py) | 2 | Create the commissioned synthetic Praktiker order, once, with a real file attachment. |
| [app/src/prototypes/orders/tools.py](../../app/src/prototypes/orders/tools.py) | 8 | Shared harness/API/CLI tool registry; caller assigns an authenticated role. |
| [app/src/prototypes/orders/widget/ask.js](../../app/src/prototypes/orders/widget/ask.js) | 46 |  |
| [app/src/prototypes/orders/widget/core.js](../../app/src/prototypes/orders/widget/core.js) | 21 |  |
| [app/src/prototypes/orders/widget/embed.js](../../app/src/prototypes/orders/widget/embed.js) | 2 |  |
| [app/src/prototypes/orders/widget/engine3d.js](../../app/src/prototypes/orders/widget/engine3d.js) | 27 |  |
| [app/src/prototypes/orders/widget/geom.js](../../app/src/prototypes/orders/widget/geom.js) | 1 |  |
| [app/src/prototypes/orders/widget/laser.js](../../app/src/prototypes/orders/widget/laser.js) | 34 |  |
| [app/src/prototypes/orders/widget/pick.js](../../app/src/prototypes/orders/widget/pick.js) | 75 |  |
| [app/src/prototypes/orders/widget/pricing.js](../../app/src/prototypes/orders/widget/pricing.js) | 26 |  |
| [app/src/prototypes/orders/widget/shop.js](../../app/src/prototypes/orders/widget/shop.js) | 208 |  |

## Shared SDK and runtime

| Module | Named definitions | Responsibility |
| --- | ---: | --- |
| [harness/deploy/build_preview.py](../../harness/deploy/build_preview.py) | 9 | Copy tracked Rocoto runtime and shared UI assets into an explicit ignored artifact. |
| [harness/deploy/chatwoot/prepare_instance.py](../../harness/deploy/chatwoot/prepare_instance.py) | 2 | Generate a private customer instance package. Creates files; starts no services. |
| [harness/layout.py](../../harness/layout.py) | 8 | Source and asset paths for one Rocoto harness process, using only the standard library. |
| [harness/mechanics/access.py](../../harness/mechanics/access.py) | 13 | One-use environment codes and 24-hour private browser sessions. |
| [harness/mechanics/agent_bridge.py](../../harness/mechanics/agent_bridge.py) | 65 | Workspace chat bridge with managed OpenAI turns and admitted harness tools. |
| [harness/mechanics/agent_catalogue.py](../../harness/mechanics/agent_catalogue.py) | 5 | Ready-made agents of the vertical this process serves (pack.py). |
| [harness/mechanics/agent_invocation.py](../../harness/mechanics/agent_invocation.py) | 1 | One foreground chat can invoke one owned agent run with current host authority. |
| [harness/mechanics/agent_kind_policy.py](../../harness/mechanics/agent_kind_policy.py) | 4 | Declared class authority follows saved conversations and native descendants. |
| [harness/mechanics/agent_wakes.py](../../harness/mechanics/agent_wakes.py) | 20 | Durable wake requests from authenticated host adapters. |
| [harness/mechanics/attachments.py](../../harness/mechanics/attachments.py) | 2 | Validated private image attachments for every workspace. |
| [harness/mechanics/background_agents.py](../../harness/mechanics/background_agents.py) | 47 | Durable, explicitly activated agents with declared workspace inputs. |
| [harness/mechanics/builtin_capabilities.py](../../harness/mechanics/builtin_capabilities.py) | 6 | Workspace-owned optional communication services, without startup provider effects. |
| [harness/mechanics/business_context.py](../../harness/mechanics/business_context.py) | 17 | Workspace business profiles, authorship and immutable revision history. |
| [harness/mechanics/business_maps.py](../../harness/mechanics/business_maps.py) | 19 | Owned, immutable map data published from generated JSON, with no network IO. |
| [harness/mechanics/business_scope.py](../../harness/mechanics/business_scope.py) | 7 | Current workspace membership and actor authority shared by every vertical. |
| [harness/mechanics/capability_providers.py](../../harness/mechanics/capability_providers.py) | 44 | Optional company-owned Viber, email and bounded voice transports. |
| [harness/mechanics/capability_spend.py](../../harness/mechanics/capability_spend.py) | 7 | Explicit account-bound email/voice allowances in the existing message ledger. |
| [harness/mechanics/catalogue_providers.py](../../harness/mechanics/catalogue_providers.py) | 12 | Host-reviewed authentication for original, pinned remote MCP packages. |
| [harness/mechanics/chat_files.py](../../harness/mechanics/chat_files.py) | 20 | Private generated documents, bound by the host to a company, owner and chat. |
| [harness/mechanics/chat_permissions.py](../../harness/mechanics/chat_permissions.py) | 20 | Explicit per-person chat ownership and durable pin/archive preferences. |
| [harness/mechanics/chat_stream.py](../../harness/mechanics/chat_stream.py) | 4 | Bounded live subscriber for a host-owned, persistently recorded native turn. |
| [harness/mechanics/company_usage.py](../../harness/mechanics/company_usage.py) | 41 | Immutable company money events, distinct from provider credit admission. |
| [harness/mechanics/conversation_tools.py](../../harness/mechanics/conversation_tools.py) | 6 | Common conversation tools supplied by the workspace host. |
| [harness/mechanics/custom_connectors.py](../../harness/mechanics/custom_connectors.py) | 31 | Owner-scoped connector source packages and encrypted, write-only credentials. |
| [harness/mechanics/custom_coordinator.py](../../harness/mechanics/custom_coordinator.py) | 44 | Host lifecycle for fixed custom adapters, observed HTTPS and durable cleanup. |
| [harness/mechanics/custom_execution.py](../../harness/mechanics/custom_execution.py) | 53 | Host-only custom adapter authority and test receipts; executes no source. |
| [harness/mechanics/custom_http.py](../../harness/mechanics/custom_http.py) | 32 | Scoped read-only HTTPS for isolated custom adapters; secrets stay on the host. |
| [harness/mechanics/custom_routes.py](../../harness/mechanics/custom_routes.py) | 9 | Owner controls over exact proposed targets and host-tested connector versions. |
| [harness/mechanics/custom_runtime.py](../../harness/mechanics/custom_runtime.py) | 9 | Host-commissioned custom runtime, verified against the installed broker. |
| [harness/mechanics/custom_setup.py](../../harness/mechanics/custom_setup.py) | 4 | Public target proposals; only the authenticated owner's action grants access. |
| [harness/mechanics/custom_tool_contracts.py](../../harness/mechanics/custom_tool_contracts.py) | 4 | Original-source adapter manifests and proposals exposed to the native harness. |
| [harness/mechanics/custom_worker.py](../../harness/mechanics/custom_worker.py) | 8 | Fixed stdlib entrypoint for the network-isolated custom read adapter profile. |
| [harness/mechanics/delegated_jobs.py](../../harness/mechanics/delegated_jobs.py) | 14 | Named, funded read jobs that run in separate OpenAI-managed sessions. |
| [harness/mechanics/document_preview_contract.py](../../harness/mechanics/document_preview_contract.py) | 4 | Host-only fixed profile and output claims; never parses Office or PDF data. |
| [harness/mechanics/document_preview_readiness.py](../../harness/mechanics/document_preview_readiness.py) | 3 | Fresh root-receipt checks for the separately commissioned document renderer. |
| [harness/mechanics/document_preview_routes.py](../../harness/mechanics/document_preview_routes.py) | 9 | Authenticated local page-preview routes. Host registration enables no decoder. |
| [harness/mechanics/document_preview_worker.py](../../harness/mechanics/document_preview_worker.py) | 8 | Fixed Office/PDF conversion. Execute only in the isolated document profile. |
| [harness/mechanics/document_previews.py](../../harness/mechanics/document_previews.py) | 17 | Private derived pages over exact ChatFiles originals; decoding stays in gVisor. |
| [harness/mechanics/document_rendering.py](../../harness/mechanics/document_rendering.py) | 10 | Bounded document creation from text, using standard document libraries. |
| [harness/mechanics/harness_routes.py](../../harness/mechanics/harness_routes.py) | 3 | The page asks the harness what it serves: GET /api/harness. |
| [harness/mechanics/harness_tools.py](../../harness/mechanics/harness_tools.py) | 30 | The harness describes itself: one read tool, `get_harness`, on every tool surface. |
| [harness/mechanics/intake_instructions.py](../../harness/mechanics/intake_instructions.py) | 2 | Host-selected standing instructions for canonical company conversations. |
| [harness/mechanics/local_workspace.py](../../harness/mechanics/local_workspace.py) | 3 | Company-only tools for a host operator using the local MCP entrypoint. |
| [harness/mechanics/managed_connections.py](../../harness/mechanics/managed_connections.py) | 8 | Managed function calls reuse workspace connection approvals and effect receipts. |
| [harness/mechanics/managed_mcp.py](../../harness/mechanics/managed_mcp.py) | 30 | Revocable, session-bound MCP reads for OpenAI's managed agent harness. |
| [harness/mechanics/managed_sessions.py](../../harness/mechanics/managed_sessions.py) | 35 | Durable managed-session identity, submissions and local effect receipts. |
| [harness/mechanics/managed_usage.py](../../harness/mechanics/managed_usage.py) | 16 | Agents API allowances inside the workspace's existing immutable money ledger. |
| [harness/mechanics/mcp_access.py](../../harness/mechanics/mcp_access.py) | 11 | Durable host-issued MCP read grants. Tokens are returned once and stored hashed. |
| [harness/mechanics/mcp_connections.py](../../harness/mechanics/mcp_connections.py) | 79 | Host-owned, principal-scoped remote MCP reads and OAuth consent. |
| [harness/mechanics/mcp_host.py](../../harness/mechanics/mcp_host.py) | 9 | Authenticated browser grants and host-only company resolution for public MCP. |
| [harness/mechanics/mcp_server.py](../../harness/mechanics/mcp_server.py) | 6 | Local MCP reads from the same selected workspace registry as hosted chat. |
| [harness/mechanics/messaging.py](../../harness/mechanics/messaging.py) | 62 | Scoped phone-channel enrollment, one-attempt delivery and verified reply admission. |
| [harness/mechanics/messaging_composition.py](../../harness/mechanics/messaging_composition.py) | 2 | Compose optional channels into one message outbox and ordinary reply ingress. |
| [harness/mechanics/messaging_config.py](../../harness/mechanics/messaging_config.py) | 8 | Private host commissioning for one explicit workspace and company. |
| [harness/mechanics/messaging_provider.py](../../harness/mechanics/messaging_provider.py) | 34 | Channel adapters for participant phone chat. Credentials never enter public records. |
| [harness/mechanics/messaging_signals.py](../../harness/mechanics/messaging_signals.py) | 7 | Verified provider messages enter the workspace's existing signal ledger. |
| [harness/mechanics/native_custom_broker.py](../../harness/mechanics/native_custom_broker.py) | 32 | Fixed custom-read jobs inside the privileged native broker. |
| [harness/mechanics/native_custom_client.py](../../harness/mechanics/native_custom_client.py) | 14 | Private host client for immutable, credential-free custom adapter jobs. |
| [harness/mechanics/organization_chats.py](../../harness/mechanics/organization_chats.py) | 11 | Canonical company conversations, without adopting any person's history. |
| [harness/mechanics/phone_chat.py](../../harness/mechanics/phone_chat.py) | 31 | Participant phone chat of a participant-reach agent: who it reaches and on which channel. |
| [harness/mechanics/phone_delivery.py](../../harness/mechanics/phone_delivery.py) | 41 | Host alert delivery of participant phone chat (CHANNELS.md, "Host alert delivery"). |
| [harness/mechanics/phone_routes.py](../../harness/mechanics/phone_routes.py) | 12 | The phone block of one Tracking Agent over HTTP (CHANNELS.md, "HTTP interface"). |
| [harness/mechanics/phone_spend.py](../../harness/mechanics/phone_spend.py) | 9 | The spend bound of participant phone chat: daily caps, Stop and fail-closed reads. |
| [harness/mechanics/private_records.py](../../harness/mechanics/private_records.py) | 1 | Bounded owner-only operator records, shared by funding and provider adapters. |
| [harness/mechanics/profile_activity.py](../../harness/mechanics/profile_activity.py) | 12 | Read-only activity from owned chats, durable runs and measured API receipts. |
| [harness/mechanics/profile_cover_generation.py](../../harness/mechanics/profile_cover_generation.py) | 16 | Bounded, company-funded generation of decorative profile artwork. |
| [harness/mechanics/profile_cover_host.py](../../harness/mechanics/profile_cover_host.py) | 11 | Narrow host integration for profile artwork and its parent-chat tools. |
| [harness/mechanics/profile_cover_routes.py](../../harness/mechanics/profile_cover_routes.py) | 2 | Authenticated, uncached profile cover reads; all identities come from the host. |
| [harness/mechanics/profile_covers.py](../../harness/mechanics/profile_covers.py) | 9 | Private profile artwork published from an owned, immutable chat artifact. |
| [harness/mechanics/profile_image_usage.py](../../harness/mechanics/profile_image_usage.py) | 4 | Images API receipts settled into the existing company OpenAI funding pool. |
| [harness/mechanics/provider_configuration.py](../../harness/mechanics/provider_configuration.py) | 4 | Host configuration for a company's OAuth applications and remote MCP policies. |
| [harness/mechanics/provider_credentials.py](../../harness/mechanics/provider_credentials.py) | 14 | Encrypted provider credentials and explicit quiescent legacy migration. |
| [harness/mechanics/provider_outputs.py](../../harness/mechanics/provider_outputs.py) | 9 | Standard provider resources become scoped output metadata, never URL fetches. |
| [harness/mechanics/provider_policy.py](../../harness/mechanics/provider_policy.py) | 7 | Host-commissioned MCP authority; upstream packages remain unchanged. |
| [harness/mechanics/public_mcp.py](../../harness/mechanics/public_mcp.py) | 29 | Own-domain, read-only MCP transport over existing company retrieval services. |
| [harness/mechanics/public_urls.py](../../harness/mechanics/public_urls.py) | 2 | Strict public HTTPS URL syntax; DNS admission remains at connection time. |
| [harness/mechanics/recipe_runs.py](../../harness/mechanics/recipe_runs.py) | 12 | Durable, conversation-scoped progress through a vertical's job recipe. |
| [harness/mechanics/registered_oauth.py](../../harness/mechanics/registered_oauth.py) | 11 | Private host registrations for reviewed providers, never customer token import. |
| [harness/mechanics/scope_host.py](../../harness/mechanics/scope_host.py) | 15 | Common workspace membership, conversation authority and resource-policy admission. |
| [harness/mechanics/signal_chain.py](../../harness/mechanics/signal_chain.py) | 26 | One workspace signal ledger: bounded chains, daily budgets and effect receipts. |
| [harness/mechanics/signal_dispatcher.py](../../harness/mechanics/signal_dispatcher.py) | 6 | One dispatcher routes saved signals to an agent job or an ordinary conversation. |
| [harness/mechanics/signal_endpoints.py](../../harness/mechanics/signal_endpoints.py) | 16 | Owner-registered signed HTTPS effects in the workspace's signal ledger. |
| [harness/mechanics/signal_screening.py](../../harness/mechanics/signal_screening.py) | 8 | A single funded Responses classification inside the existing signal chain. |
| [harness/mechanics/signal_sources.py](../../harness/mechanics/signal_sources.py) | 15 | Reviewed timers and signed webhooks feeding the workspace's one signal ledger. |
| [harness/mechanics/skills.py](../../harness/mechanics/skills.py) | 23 | Company-scoped instruction skills with immutable revisions and explicit installation. |
| [harness/mechanics/source_icons.py](../../harness/mechanics/source_icons.py) | 5 | Bounded public favicon reads with DNS pinning and a small process cache. |
| [harness/mechanics/source_media.py](../../harness/mechanics/source_media.py) | 84 | Fixed, isolated media preparation broker. This module never decodes media. |
| [harness/mechanics/stored_media.py](../../harness/mechanics/stored_media.py) | 2 | Signature classification and range playback for bounded, owned output bytes. |
| [harness/mechanics/title_stream.py](../../harness/mechanics/title_stream.py) | 3 | Project a streamed display title from the first assistant commentary. |
| [harness/mechanics/transfer_budget.py](../../harness/mechanics/transfer_budget.py) | 17 | Durable demo egress budget and fail-closed HTTP response middleware. |
| [harness/mechanics/wake_tools.py](../../harness/mechanics/wake_tools.py) | 6 | Conversation-bound tools for signed webhooks and finite self-set wakes. |
| [harness/mechanics/web_mount.py](../../harness/mechanics/web_mount.py) | 14 | Mount the real workspace and Orders HTTP service below one deployment path. |
| [harness/mechanics/workspace_auth.py](../../harness/mechanics/workspace_auth.py) | 25 | Hosted WorkOS identity admission into the harness's existing workspace sessions. |
| [harness/mechanics/workspace_auth_routes.py](../../harness/mechanics/workspace_auth_routes.py) | 11 | Small hosted-login routes; the caller retains the native session middleware. |
| [harness/mechanics/workspace_billing.py](../../harness/mechanics/workspace_billing.py) | 35 | Workspace subscriptions and settled credit receipts, separate from agent spending. |
| [harness/mechanics/workspace_billing_routes.py](../../harness/mechanics/workspace_billing_routes.py) | 15 | Shared workspace billing HTTP boundary and private per-workspace commissioning. |
| [harness/mechanics/workspace_capabilities.py](../../harness/mechanics/workspace_capabilities.py) | 4 | Host-owned connection and execution readiness shared by all verticals. |
| [harness/mechanics/workspace_identity.py](../../harness/mechanics/workspace_identity.py) | 8 | Private, portable company identity shared by stores and provider pools. |
| [harness/run.py](../../harness/run.py) | 1 | Run a harness command through the active vertical's source layout. |
| [harness/runtime/agent_auth.py](../../harness/runtime/agent_auth.py) | 8 | Host-selected native authentication and company-bound metered API leases. |
| [harness/runtime/api_smoke.py](../../harness/runtime/api_smoke.py) | 2 | One explicit, tiny commissioning request through the actual company gateway. |
| [harness/runtime/hosted_capabilities.py](../../harness/runtime/hosted_capabilities.py) | 17 | Exact installed capabilities packaged for OpenAI's managed environment. |
| [harness/runtime/hosted_install.py](../../harness/runtime/hosted_install.py) | 2 | Acquire unchanged public plugin archives for OpenAI-hosted execution. |
| [harness/runtime/managed_children.py](../../harness/runtime/managed_children.py) | 7 | Project provider-attested managed subagents into scoped Rocoto conversations. |
| [harness/runtime/managed_codex.py](../../harness/runtime/managed_codex.py) | 47 | Agents API v1 transport, verified against official documentation on 2026-10-11. |
| [harness/runtime/managed_diagnostics.py](../../harness/runtime/managed_diagnostics.py) | 2 | Bounded operator diagnostics beside state, separate from conversation history. |
| [harness/runtime/managed_files.py](../../harness/runtime/managed_files.py) | 6 | Retain stock hosted artifacts in the owning conversation's existing Files store. |
| [harness/runtime/managed_policy.py](../../harness/runtime/managed_policy.py) | 15 | Workspace funding and revocable tool authority around OpenAI-managed execution. |
| [harness/runtime/managed_runtime.py](../../harness/runtime/managed_runtime.py) | 31 | Funded managed turns, session recovery and controls for the shared harness. |
| [harness/runtime/managed_spend.py](../../harness/runtime/managed_spend.py) | 7 | Opt-in token estimates and a persisted wall deadline for managed execution. |
| [harness/runtime/managed_turn.py](../../harness/runtime/managed_turn.py) | 10 | Managed Agents protocol projected through Rocoto's admitted workspace tools. |
| [harness/runtime/native_approvals.py](../../harness/runtime/native_approvals.py) | 40 | Host-bound native MCP approval intents; this module performs no provider I/O. |
| [harness/runtime/native_events.py](../../harness/runtime/native_events.py) | 10 | Project public Codex items; authentication and thread admission belong to the host. |
| [harness/runtime/native_executor.py](../../harness/runtime/native_executor.py) | 70 | Host-owned native Codex worker broker and its narrow Unix-socket client. |
| [harness/runtime/native_install_broker.py](../../harness/runtime/native_install_broker.py) | 28 | Fixed offline installer operations inside the existing privileged broker. |
| [harness/runtime/native_install_client.py](../../harness/runtime/native_install_client.py) | 12 | Scoped native package materializer using the fixed privileged installer. |
| [harness/runtime/native_install_readiness.py](../../harness/runtime/native_install_readiness.py) | 2 | Fresh, allocation-free native installer readiness for authenticated hosts. |
| [harness/runtime/native_install_source.py](../../harness/runtime/native_install_source.py) | 5 | Pinned public source acquisition for the offline native installer. |
| [harness/runtime/native_install_worker.py](../../harness/runtime/native_install_worker.py) | 9 | Fixed offline native CLI materializer. Run only inside its quota sandbox. |
| [harness/runtime/native_mcp.py](../../harness/runtime/native_mcp.py) | 25 | Inherited native Codex tools through the standard MCP Streamable HTTP protocol. |
| [harness/runtime/native_package_mount.py](../../harness/runtime/native_package_mount.py) | 11 | Root-side validation of bounded original plugin trees; no account credentials. |
| [harness/runtime/native_packages.py](../../harness/runtime/native_packages.py) | 39 | Original Codex packages, private selections, and verified worker-mount inputs. |
| [harness/runtime/native_plugins.py](../../harness/runtime/native_plugins.py) | 14 | Host-only native Codex plugin management, isolated per company and person. |
| [harness/runtime/native_provider_relay.py](../../harness/runtime/native_provider_relay.py) | 25 | Original provider tools under host authority and a consenting owner. |
| [harness/runtime/native_provider_write.py](../../harness/runtime/native_provider_write.py) | 18 | One approved native MCP mutation, fixed credentials and durable outcome. |
| [harness/runtime/native_questions.py](../../harness/runtime/native_questions.py) | 21 | Durable ordinary Codex questions, scoped to a host-admitted worker generation. |
| [harness/runtime/native_skills.py](../../harness/runtime/native_skills.py) | 12 | Pinned original skill references resolved into actual native skill inputs. |
| [harness/runtime/openai_gateway.py](../../harness/runtime/openai_gateway.py) | 25 | Company-bound, loopback Responses transport with prepaid request admission. |
| [harness/runtime/plugin_catalogue.py](../../harness/runtime/plugin_catalogue.py) | 19 | Pinned upstream plugin reference data, independent from account connections. |
| [harness/runtime/plugin_routes.py](../../harness/runtime/plugin_routes.py) | 26 | Private, host-commissioned native package selection and durable removal. |
| [harness/runtime/provider_tool_policy.py](../../harness/runtime/provider_tool_policy.py) | 1 | Host-reviewed approval hints for original provider tool schemas. |
| [harness/sdk/agent_inputs.py](../../harness/sdk/agent_inputs.py) | 25 | Input provider contract for the shared saved-agent store and scheduler. |
| [harness/sdk/capability_contract.py](../../harness/sdk/capability_contract.py) | 1 | The optional communication capabilities a vertical selects from the harness. |
| [harness/sdk/display_presentation.py](../../harness/sdk/display_presentation.py) | 33 | Shared display kit: bounded presentations, output bindings and safe page projections. |
| [harness/sdk/display_runs.py](../../harness/sdk/display_runs.py) | 27 | Durable display cadence, leases and run history shared by every vertical. |
| [harness/sdk/display_scripts.py](../../harness/sdk/display_scripts.py) | 24 | Bounded script execution supplied by Rocoto's SDK. |
| [harness/sdk/host.py](../../harness/sdk/host.py) | 35 | Composition and admission contracts for one selected vertical on the harness. |
| [harness/sdk/job_recipes.py](../../harness/sdk/job_recipes.py) | 6 | Vertical job instructions and bounded role declarations for managed delegation. |
| [harness/sdk/layers.py](../../harness/sdk/layers.py) | 9 | Rocoto source ownership and the remaining imports into the active vertical. |
| [harness/sdk/pack.py](../../harness/sdk/pack.py) | 87 | The vertical this harness process serves: one validated manifest and the files it names. |
| [harness/sdk/tool_families.py](../../harness/sdk/tool_families.py) | 17 | Validated workspace tools and host-owned authority shared by every transport. |
| [harness/server.py](../../harness/server.py) | 148 | One workspace host for the Rocoto harness and its selected vertical. |
| [harness/web/app.js](../../harness/web/app.js) | 396 |  |
| [harness/web/business-map.js](../../harness/web/business-map.js) | 24 |  |
| [harness/web/business-summary.js](../../harness/web/business-summary.js) | 5 |  |
| [harness/web/display-canvas.js](../../harness/web/display-canvas.js) | 104 |  |
| [harness/web/display-charts.js](../../harness/web/display-charts.js) | 67 |  |
| [harness/web/harness-shell.js](../../harness/web/harness-shell.js) | 6 |  |
| [harness/web/messaging-settings.js](../../harness/web/messaging-settings.js) | 62 |  |
| [harness/web/plugin-settings.js](../../harness/web/plugin-settings.js) | 4 |  |
| [harness/web/profile-settings.js](../../harness/web/profile-settings.js) | 9 |  |
| [harness/web/question-box.js](../../harness/web/question-box.js) | 12 |  |
| [harness/web/rich-content.js](../../harness/web/rich-content.js) | 19 |  |
| [harness/web/rich-diagram.js](../../harness/web/rich-diagram.js) | 1 |  |
| [harness/web/settings-shell.js](../../harness/web/settings-shell.js) | 3 |  |
| [harness/web/tool-trail.js](../../harness/web/tool-trail.js) | 15 |  |
| [harness/web/wake-controls.js](../../harness/web/wake-controls.js) | 5 |  |
| [harness/web/workspace-account.js](../../harness/web/workspace-account.js) | 13 |  |
| [harness/web/workspace-extensions.js](../../harness/web/workspace-extensions.js) | 2 |  |
| [harness/web/workspace-home.js](../../harness/web/workspace-home.js) | 1 |  |
| [harness/web/workspace-settings.js](../../harness/web/workspace-settings.js) | 12 |  |
| [harness/web/workspace-tabs.js](../../harness/web/workspace-tabs.js) | 7 |  |

## Recipient tools and journal

| Module | Named definitions | Responsibility |
| --- | ---: | --- |
| [backend/realtime/configuration.py](../../backend/realtime/configuration.py) | 25 | Typed Rocoto Real-time configuration; activation requires actual source evidence. |
| [backend/realtime/continuity.py](../../backend/realtime/continuity.py) | 30 | Host-receipted continuity of stock tracker state across camera file rotations. |
| [backend/realtime/contracts.py](../../backend/realtime/contracts.py) | 18 | Small, versioned contracts shared by realtime workers and the host. |
| [backend/realtime/identity.py](../../backend/realtime/identity.py) | 9 | Explicit binding of a verified supplier identity to an imported operator. |
| [backend/realtime/import_stream.py](../../backend/realtime/import_stream.py) | 16 | Host-reviewed migration of admitted stream history through the maintained SDK. |
| [backend/realtime/import_tracker_run.py](../../backend/realtime/import_tracker_run.py) | 38 | Host import of retained complete tracker runs as historical tracker reports. |
| [backend/realtime/locations.py](../../backend/realtime/locations.py) | 49 | A retail location's trackers, records, outputs, schedule and runs behind the company wall. |
| [backend/realtime/media.py](../../backend/realtime/media.py) | 2 | Resolve host-published media against current maintained camera authority. |
| [backend/realtime/module_store.py](../../backend/realtime/module_store.py) | 27 | Durable source-scoped snapshots for maintained core processing modules. |
| [backend/realtime/modules.py](../../backend/realtime/modules.py) | 11 | Maintained retail projections over admitted, explicitly bound observations. |
| [backend/realtime/provision.py](../../backend/realtime/provision.py) | 6 | Explicit host migration of saved video identity into the existing tenant registry. |
| [backend/realtime/provision_host.py](../../backend/realtime/provision_host.py) | 14 | Host command: import one saved video company identity through the owner migration role. |
| [backend/realtime/read_contract.py](../../backend/realtime/read_contract.py) | 2 | Bounded public projection wire shared by authenticated Rocoto hosts. |
| [backend/realtime/replay.py](../../backend/realtime/replay.py) | 18 | Pure, bounded replay compiler for previously admitted observation records. |
| [backend/realtime/replay_store.py](../../backend/realtime/replay_store.py) | 17 | Durable observation replay through the ordinary scoped admission service. |
| [backend/realtime/replay_worker.py](../../backend/realtime/replay_worker.py) | 5 | Bounded replay admission plus core projection orchestration. |
| [backend/realtime/routes.py](../../backend/realtime/routes.py) | 7 | Maintained, tenant-authenticated reads for realtime projections. |
| [backend/realtime/store.py](../../backend/realtime/store.py) | 20 | Tenant-scoped admission and durable work. The host authenticates every context. |
| [backend/realtime/subjects.py](../../backend/realtime/subjects.py) | 22 | Source-backed, non-biometric identities and exact event-subject associations. |
| [deploy/development/contract.py](../../deploy/development/contract.py) | 4 | Shared validation for development-preview target manifests. |
| [tools/bind.py](../../tools/bind.py) | 1 | Bind one recipient workspace to its own Orders service. |
| [tools/check_browser.py](../../tools/check_browser.py) | 2 | Check the owned local first result with Playwright, without calling external services. |
| [tools/configure.py](../../tools/configure.py) | 1 | Save recipient keys through hidden terminal input. |
| [tools/dev.py](../../tools/dev.py) | 5 | Run the actual order service and native workspace with an isolated authored sample. |
| [tools/offline.py](../../tools/offline.py) | 6 | Offline first-result boundary; recipient-connected service deployment is separate. |
| [tools/private.py](../../tools/private.py) | 3 | Recipient-owned private settings; credential values stay outside source and stdout. |
| [tools/sample_build.py](../../tools/sample_build.py) | 1 | Create an owned sample manufacturer using the real Orders store and widget bundle. |
| [tools/serve.py](../../tools/serve.py) | 1 | Serve one recipient-owned process with explicit state and private credentials. |

## HTTP handlers

These are literal decorated FastAPI paths. The public Orders server also uses explicit dispatch in `serve.py`; its handler methods are indexed above. Authentication and capability checks remain in the implementation.

| Method | Path | Handler |
| --- | --- | --- |
| GET | `/manufacturer/orders` | [register_routes.orders_page](../../app/src/prototypes/orders/manufacturer_host.py#L172) |
| GET | `/manufacturer/orders.css` | [register_routes.orders_style](../../app/src/prototypes/orders/manufacturer_host.py#L181) |
| GET | `/manufacturer/orders.js` | [register_routes.orders_script](../../app/src/prototypes/orders/manufacturer_host.py#L190) |
| GET | `/api/manufacturer/orders` | [register_routes.orders_api](../../app/src/prototypes/orders/manufacturer_host.py#L199) |
| GET | `/api/manufacturer/orders/{order_id}/files/{file_id}` | [register_routes.order_file](../../app/src/prototypes/orders/manufacturer_host.py#L229) |
| GET | `/sources/{source_id}/assets/{asset_id}/snapshot` | [source_snapshot](../../backend/realtime/routes.py#L118) |
| GET | `/sources/{source_id}/epochs/{epoch_id}/snapshot` | [epoch_snapshot](../../backend/realtime/routes.py#L139) |
| GET | `/replays/{run_id}` | [replay_status](../../backend/realtime/routes.py#L170) |
| GET | `/api/connections/custom/{connector_id}/execution` | [register_custom_routes.execution](../../harness/mechanics/custom_routes.py#L41) |
| POST | `/api/connections/custom/{connector_id}/execution/target` | [register_custom_routes.target](../../harness/mechanics/custom_routes.py#L49) |
| POST | `/api/connections/custom/{connector_id}/execution/activate` | [register_custom_routes.activate](../../harness/mechanics/custom_routes.py#L61) |
| POST | `/api/connections/custom/{connector_id}/execution/test` | [register_custom_routes.test](../../harness/mechanics/custom_routes.py#L78) |
| POST | `/api/connections/custom/{connector_id}/execution/revoke` | [register_custom_routes.revoke](../../harness/mechanics/custom_routes.py#L98) |
| POST | `/api/connections/custom/{connector_id}/execution/stop` | [register_custom_routes.stop](../../harness/mechanics/custom_routes.py#L109) |
| GET | `/api/files/{file_id}/page-preview` | [register_document_preview_routes.metadata](../../harness/mechanics/document_preview_routes.py#L65) |
| POST | `/api/files/{file_id}/preview` | [register_document_preview_routes.prepare](../../harness/mechanics/document_preview_routes.py#L71) |
| GET | `/api/files/{file_id}/pages/{page}` | [register_document_preview_routes.page](../../harness/mechanics/document_preview_routes.py#L101) |
| GET | `/api/harness` | [register_harness_routes.harness](../../harness/mechanics/harness_routes.py#L51) |
| GET | `/api/mcp/connections` | [MCPHost.register_routes.connections](../../harness/mechanics/mcp_host.py#L98) |
| POST | `/api/mcp/connections` | [MCPHost.register_routes.create_connection](../../harness/mechanics/mcp_host.py#L106) |
| DELETE | `/api/mcp/connections/{key}` | [MCPHost.register_routes.revoke_connection](../../harness/mechanics/mcp_host.py#L136) |
| GET | `/api/agents/{agent_id}/phone` | [register_phone_routes.phone_block](../../harness/mechanics/phone_routes.py#L95) |
| POST | `/api/agents/{agent_id}/phone/participants` | [register_phone_routes.phone_add](../../harness/mechanics/phone_routes.py#L100) |
| POST | `/api/agents/{agent_id}/phone/participants/{member_id}/remove` | [register_phone_routes.phone_remove](../../harness/mechanics/phone_routes.py#L106) |
| POST | `/api/agents/{agent_id}/phone/participants/{member_id}` | [register_phone_routes.phone_participant](../../harness/mechanics/phone_routes.py#L112) |
| POST | `/api/agents/{agent_id}/phone/delivery` | [register_phone_routes.phone_delivery_state](../../harness/mechanics/phone_routes.py#L119) |
| POST | `/api/agents/{agent_id}/phone/contact-request` | [register_phone_routes.phone_contact_request](../../harness/mechanics/phone_routes.py#L125) |
| GET | `/api/profile-covers/{cover_id}` | [register_profile_cover_routes.cover](../../harness/mechanics/profile_cover_routes.py#L22) |
| GET | `/api/auth/config` | [register_workspace_auth.auth_config](../../harness/mechanics/workspace_auth_routes.py#L23) |
| GET | `/auth/login` | [register_workspace_auth.login](../../harness/mechanics/workspace_auth_routes.py#L27) |
| GET | `/auth/callback` | [register_workspace_auth.callback](../../harness/mechanics/workspace_auth_routes.py#L41) |
| GET | `/api/workspaces` | [register_workspace_auth.workspaces](../../harness/mechanics/workspace_auth_routes.py#L54) |
| GET | `/api/workspaces/access` | [register_workspace_auth.workspace_access](../../harness/mechanics/workspace_auth_routes.py#L64) |
| POST | `/api/workspaces/select` | [register_workspace_auth.select](../../harness/mechanics/workspace_auth_routes.py#L96) |
| POST | `/api/workspaces/invitations` | [register_workspace_auth.invite](../../harness/mechanics/workspace_auth_routes.py#L109) |
| GET | `/api/billing/status` | [register_workspace_billing.status](../../harness/mechanics/workspace_billing_routes.py#L109) |
| POST | `/api/billing/checkout` | [register_workspace_billing.checkout](../../harness/mechanics/workspace_billing_routes.py#L148) |
| POST | `/api/billing/credits` | [register_workspace_billing.credits](../../harness/mechanics/workspace_billing_routes.py#L152) |
| POST | `/api/billing/portal` | [register_workspace_billing.portal](../../harness/mechanics/workspace_billing_routes.py#L156) |
| POST | `/hooks/stripe/{environment}` | [register_workspace_billing.webhook](../../harness/mechanics/workspace_billing_routes.py#L160) |
| GET | `/api/plugins/installed` | [register_plugin_routes.installed](../../harness/runtime/plugin_routes.py#L253) |
| POST | `/api/plugins/{plugin_id}/install` | [register_plugin_routes.install](../../harness/runtime/plugin_routes.py#L265) |
| DELETE | `/api/plugins/{plugin_id}/installation` | [register_plugin_routes.remove](../../harness/runtime/plugin_routes.py#L286) |
| GET | `/api/organization/chats` | [create_app.organization_chats](../../harness/server.py#L918) |
| POST | `/api/organization/chats` | [create_app.organization_chat](../../harness/server.py#L930) |
| GET | `/api/messaging` | [create_app.messaging_status](../../harness/server.py#L944) |
| POST | `/api/messaging/verification` | [create_app.messaging_verification](../../harness/server.py#L948) |
| POST | `/api/messaging/verification/confirm` | [create_app.messaging_confirm](../../harness/server.py#L963) |
| POST | `/api/messaging/hello` | [create_app.messaging_hello](../../harness/server.py#L978) |
| POST | `/hooks/in/{environment}/{hook_id}` | [create_app.incoming_hook](../../harness/server.py#L1057) |
| POST | `/api/hooks/{environment}/{hook_id}` | [create_app.incoming_hook](../../harness/server.py#L1057) |
| GET | `/api/wakes` | [create_app.wake_sources](../../harness/server.py#L1079) |
| POST | `/api/wakes/endpoints/{endpoint_id}/secret` | [create_app.endpoint_secret](../../harness/server.py#L1089) |
| POST | `/api/wakes/hooks/{hook_id}/secret` | [create_app.reveal_wake_secret](../../harness/server.py#L1101) |
| POST | `/hooks/{channel}/{environment}` | [create_app.messaging_webhook](../../harness/server.py#L1116) |
| GET | `/hooks/{channel}/{environment}` | [create_app.messaging_webhook](../../harness/server.py#L1116) |
| POST | `/api/messaging/webhook/{environment}/{channel}` | [create_app.messaging_webhook](../../harness/server.py#L1116) |
| GET | `/api/plugins/catalogue` | [create_app.plugins_catalogue](../../harness/server.py#L1225) |
| GET | `/api/plugins/{plugin_id}` | [create_app.plugin_details](../../harness/server.py#L1229) |
| GET | `/api/connections` | [create_app.connections](../../harness/server.py#L1236) |
| GET | `/api/connections/custom` | [create_app.custom_connections](../../harness/server.py#L1272) |
| POST | `/api/connections/custom` | [create_app.create_custom_connection](../../harness/server.py#L1287) |
| GET | `/api/connections/custom/{connector_id}` | [create_app.custom_connection](../../harness/server.py#L1326) |
| GET | `/api/connections/custom/{connector_id}/package` | [create_app.custom_connection_package](../../harness/server.py#L1344) |
| POST | `/api/connections/custom/{connector_id}/secrets` | [create_app.custom_connection_secret](../../harness/server.py#L1353) |
| DELETE | `/api/connections/custom/{connector_id}/secrets/{name}` | [create_app.custom_connection_secret_remove](../../harness/server.py#L1374) |
| POST | `/api/connections/{provider}/connect` | [create_app.connect_provider](../../harness/server.py#L1380) |
| GET | `/api/connections/flows/{flow_id}` | [create_app.connection_flow](../../harness/server.py#L1423) |
| DELETE | `/api/connections/{provider}` | [create_app.disconnect_provider](../../harness/server.py#L1432) |
| GET | `/api/connections/oauth/callback` | [create_app.oauth_landing](../../harness/server.py#L1443) |
| GET | `/oauth-callback.js` | [create_app.oauth_script](../../harness/server.py#L1449) |
| POST | `/api/connections/oauth/callback` | [create_app.oauth_callback](../../harness/server.py#L1453) |
| GET | `/` | [create_app.home](../../harness/server.py#L1462) |
| GET | `/app.js` | [create_app.script](../../harness/server.py#L1482) |
| GET | `/question-box.js` | [create_app.question_box_script](../../harness/server.py#L1486) |
| GET | `/question-box.css` | [create_app.question_box_style](../../harness/server.py#L1490) |
| GET | `/brand/rocoto-mark.svg` | [create_app.logo](../../harness/server.py#L1494) |
| GET | `/fonts/fraunces/fraunces-latin-500-700.woff2` | [create_app.wordmark_font](../../harness/server.py#L1499) |
| GET | `/connection-brands/{filename}` | [create_app.connection_brand](../../harness/server.py#L1504) |
| GET | `/vendor/{filename:path}` | [create_app.vendor](../../harness/server.py#L1510) |
| GET | `/assets/chat-dreamscape.png` | [create_app.workspace_artwork](../../harness/server.py#L1517) |
| GET | `/assets/search-dreamscape.png` | [create_app.workspace_artwork](../../harness/server.py#L1517) |
| GET | `/assets/monet-water-lilies.jpg` | [create_app.empty_state_artwork](../../harness/server.py#L1522) |
| GET | `/style.css` | [create_app.style](../../harness/server.py#L1527) |
| GET | `/business-summary.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/business-summary.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/settings-shell.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/settings-shell.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/harness-shell.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-tabs.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-extensions.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/wake-controls.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/wake-controls.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-tabs.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-home.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-home.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/display-charts.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/display-charts.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/display-canvas.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/display-canvas.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/tool-trail.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/tool-trail.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/rich-content.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/rich-content.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/rich-diagram.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/profile-settings.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/profile-settings.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/plugin-settings.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/plugin-settings.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/messaging-settings.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/messaging-settings.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-settings.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/workspace-settings.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/business-map.js` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/business-map.css` | [create_app.interface_component](../../harness/server.py#L1561) |
| GET | `/rich-diagram.html` | [create_app.diagram_component](../../harness/server.py#L1567) |
| GET | `/static/vendor/{filename:path}` | [create_app.shared_vendor](../../harness/server.py#L1588) |
| GET | `/api/source-icon` | [create_app.source_icon](../../harness/server.py#L1592) |
| GET | `/theme.css` | [create_app.theme](../../harness/server.py#L1600) |
| GET | `/healthz` | [create_app.health](../../harness/server.py#L1637) |
| GET | `/api/session` | [create_app.session_info](../../harness/server.py#L1652) |
| POST | `/api/session` | [create_app.login](../../harness/server.py#L1667) |
| POST | `/api/session/demo` | [create_app.demo_session](../../harness/server.py#L1677) |
| DELETE | `/api/session` | [create_app.logout](../../harness/server.py#L1686) |
| POST | `/api/session/company` | [create_app.select_environment](../../harness/server.py#L1694) |
| POST | `/api/environment` | [create_app.select_environment](../../harness/server.py#L1694) |
| GET | `/api/observers` | [create_app.observers](../../harness/server.py#L1703) |
| POST | `/api/observer` | [create_app.observe](../../harness/server.py#L1710) |
| DELETE | `/api/observer` | [create_app.end_observation](../../harness/server.py#L1717) |
| GET | `/api/status` | [create_app.status](../../harness/server.py#L1724) |
| GET | `/api/business` | [create_app.business](../../harness/server.py#L1745) |
| GET | `/api/business/map` | [create_app.business_map](../../harness/server.py#L1756) |
| POST | `/api/business/profile` | [create_app.business_profile](../../harness/server.py#L1787) |
| POST | `/api/business/onboarding` | [create_app.onboarding](../../harness/server.py#L1794) |
| GET | `/api/profile/activity` | [create_app.profile_activity](../../harness/server.py#L1812) |
| GET | `/api/usage` | [create_app.usage](../../harness/server.py#L1837) |
| POST | `/api/usage/settings` | [create_app.usage_settings](../../harness/server.py#L1863) |
| GET | `/api/skills/catalogue` | [create_app.skills_catalogue](../../harness/server.py#L1886) |
| GET | `/api/skills` | [create_app.skills_installed](../../harness/server.py#L1891) |
| POST | `/api/skills/install` | [create_app.skills_install](../../harness/server.py#L1896) |
| GET | `/api/ready-agents` | [create_app.agent_catalogue](../../harness/server.py#L1904) |
| GET | `/api/agents/catalogue` | [create_app.agent_catalogue](../../harness/server.py#L1904) |
| GET | `/api/workspace/capabilities` | [create_app.workspace_capabilities](../../harness/server.py#L1957) |
| GET | `/api/agents` | [create_app.agents_list](../../harness/server.py#L1962) |
| POST | `/api/agents` | [create_app.agents_create](../../harness/server.py#L1983) |
| GET | `/api/agents/{agent_id}` | [create_app.agent_details](../../harness/server.py#L1996) |
| POST | `/api/agents/{agent_id}/update` | [create_app.agent_update](../../harness/server.py#L2000) |
| POST | `/api/agents/{agent_id}/activate` | [create_app.agent_activate](../../harness/server.py#L2028) |
| POST | `/api/agents/{agent_id}/run` | [create_app.agent_run](../../harness/server.py#L2032) |
| POST | `/api/agents/{agent_id}/pause` | [create_app.agent_pause](../../harness/server.py#L2036) |
| GET | `/api/agents/{agent_id}/runs/{run_id}/report` | [create_app.agent_report](../../harness/server.py#L2044) |
| POST | `/api/chat` | [create_app.chat](../../harness/server.py#L2067) |
| GET | `/api/chats` | [create_app.chats](../../harness/server.py#L2178) |
| POST | `/api/chats/{chat_id}/metadata` | [create_app.chat_metadata](../../harness/server.py#L2187) |
| GET | `/api/chats/{chat_id}` | [create_app.child_chat](../../harness/server.py#L2198) |
| POST | `/api/chats/{chat_id}/approvals/{request_id}` | [create_app.answer_native_approval](../../harness/server.py#L2237) |
| POST | `/api/chats/{chat_id}/questions/{request_id}` | [create_app.answer_native_question](../../harness/server.py#L2270) |
| POST | `/api/chats/{chat_id}/credential-requests/{request_id}` | [create_app.answer_credential_request](../../harness/server.py#L2305) |
| POST | `/api/chat/{chat_id}/stop` | [create_app.stop_chat](../../harness/server.py#L2350) |
| POST | `/api/chat/{chat_id}/steer` | [create_app.steer_chat](../../harness/server.py#L2367) |
| POST | `/api/attachments` | [create_app.attachment](../../harness/server.py#L2389) |
| GET | `/attachments/{attachment_id}.png` | [create_app.attachment_image](../../harness/server.py#L2408) |
| GET | `/api/files` | [create_app.list_files](../../harness/server.py#L2466) |
| GET | `/api/files/{file_id}` | [create_app.get_file](../../harness/server.py#L2485) |
| GET | `/api/files/{file_id}/content` | [create_app.file_content](../../harness/server.py#L2493) |
| PATCH | `/api/files/{file_id}` | [create_app.rename_file](../../harness/server.py#L2502) |
| POST | `/api/files/{file_id}/opened` | [create_app.mark_file_opened](../../harness/server.py#L2515) |
| GET | `/api/files/{file_id}/download` | [create_app.download_file](../../harness/server.py#L2524) |
| GET | `/api/files/{file_id}/preview` | [create_app.preview_file](../../harness/server.py#L2543) |
| GET | `/api/manufacturer/communication/status` | [register_chatwoot.status](../../harness/verticals/manufacturer/manufacturer_chatwoot_routes.py#L97) |
| GET | `/api/manufacturer/orders/{order_id}/review` | [register_conversations.get_review](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L147) |
| POST | `/api/manufacturer/orders/{order_id}/review` | [register_conversations.prepare_review](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L152) |
| GET | `/api/manufacturer/service-conversation` | [register_conversations.get_service](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L202) |
| POST | `/api/manufacturer/service-conversation/messages` | [register_conversations.send_service](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L207) |
| GET | `/api/manufacturer/conversations/{customer_id}` | [register_conversations.get_customer](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L229) |
| POST | `/api/manufacturer/conversations/{customer_id}/messages` | [register_conversations.send_customer](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L235) |
| GET | `/api/manufacturer/service-conversation/archive` | [register_conversations.service_archive](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L259) |
| GET | `/api/manufacturer/conversations/{customer_id}/archive` | [register_conversations.customer_archive](../../harness/verticals/manufacturer/manufacturer_conversation_routes.py#L268) |
| POST | `/api/manufacturer/customers/{customer_id}/review-links` | [register_customer_portal.mint_review](../../harness/verticals/manufacturer/manufacturer_customer_portal.py#L539) |
| POST | `/api/manufacturer/customers/{customer_id}/phone-links` | [register_customer_portal.mint_phone](../../harness/verticals/manufacturer/manufacturer_customer_portal.py#L567) |
| POST | `/api/manufacturer/customer-links/{capability_id}/revoke` | [register_customer_portal.revoke_link](../../harness/verticals/manufacturer/manufacturer_customer_portal.py#L594) |
| POST | `/api/manufacturer/customer-portal/{environment}/{action}` | [register_customer_portal.operation](../../harness/verticals/manufacturer/manufacturer_customer_portal.py#L608) |
| GET | `/api/manufacturer/orders/{order_id}/fulfillment` | [register_fulfillment.get_progress](../../harness/verticals/manufacturer/manufacturer_fulfillment.py#L225) |
| POST | `/api/manufacturer/orders/{order_id}/fulfillment` | [register_fulfillment.set_progress](../../harness/verticals/manufacturer/manufacturer_fulfillment.py#L237) |
| POST | `/api/manufacturer/files` | [register_routes.upload_source](../../harness/verticals/manufacturer/manufacturer_host.py#L502) |
| GET | `/api/manufacturer/overview` | [register_routes.overview](../../harness/verticals/manufacturer/manufacturer_host.py#L515) |
| GET | `/api/manufacturer/orders` | [register_routes.overview](../../harness/verticals/manufacturer/manufacturer_host.py#L515) |
| POST | `/api/manufacturer/orders` | [register_routes.create_order](../../harness/verticals/manufacturer/manufacturer_host.py#L520) |
| GET | `/api/manufacturer/orders/{order_id}` | [register_routes.order](../../harness/verticals/manufacturer/manufacturer_host.py#L528) |
| GET | `/api/manufacturer/orders/{order_id}/files` | [register_routes.order_files](../../harness/verticals/manufacturer/manufacturer_host.py#L533) |
| GET | `/api/manufacturer/orders/{order_id}/files/{file_id}` | [register_routes.order_file](../../harness/verticals/manufacturer/manufacturer_host.py#L540) |
| GET | `/api/manufacturer/orders/{order_id}/files/{file_id}/page/{page}` | [register_routes.order_file_page](../../harness/verticals/manufacturer/manufacturer_host.py#L547) |
| GET | `/api/manufacturer/customers` | [register_routes.customers](../../harness/verticals/manufacturer/manufacturer_host.py#L561) |
| GET | `/api/manufacturer/customers/{customer_id}` | [register_routes.customer](../../harness/verticals/manufacturer/manufacturer_host.py#L566) |
| GET | `/api/manufacturer/configurator` | [register_routes.configurator](../../harness/verticals/manufacturer/manufacturer_host.py#L571) |
| POST | `/api/manufacturer/configurator` | [register_routes.save_configurator](../../harness/verticals/manufacturer/manufacturer_host.py#L576) |
| GET | `/api/manufacturer/configurator/versions` | [register_routes.versions](../../harness/verticals/manufacturer/manufacturer_host.py#L582) |
| GET | `/api/manufacturer/configurator/versions/{version_id}` | [register_routes.version](../../harness/verticals/manufacturer/manufacturer_host.py#L587) |
| POST | `/api/manufacturer/configurator/versions/{version_id}/restore` | [register_routes.restore_version](../../harness/verticals/manufacturer/manufacturer_host.py#L592) |
| POST | `/api/manufacturer/configurator/restore` | [register_routes.restore](../../harness/verticals/manufacturer/manufacturer_host.py#L600) |
| GET | `/api/manufacturer/preview/{version_id}` | [register_routes.preview](../../harness/verticals/manufacturer/manufacturer_host.py#L608) |
| GET | `/api/manufacturer/team` | [register_routes.team](../../harness/verticals/manufacturer/manufacturer_host.py#L620) |
| POST | `/api/manufacturer/team` | [register_routes.update_team](../../harness/verticals/manufacturer/manufacturer_host.py#L625) |
| GET | `/api/manufacturer/email/status` | [register_mail.status](../../harness/verticals/manufacturer/manufacturer_mail_routes.py#L302) |
| GET | `/api/manufacturer/email/review` | [register_mail.reviews](../../harness/verticals/manufacturer/manufacturer_mail_routes.py#L311) |
| POST | `/api/manufacturer/email/drain` | [register_mail.drain](../../harness/verticals/manufacturer/manufacturer_mail_routes.py#L320) |

[made by atelier neyra](https://atelierneyra.com)
