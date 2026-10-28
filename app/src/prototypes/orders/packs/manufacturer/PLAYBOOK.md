# Manufacturer run

Generated from `stages.json` by `manufacturer.py generate`.

One company URL starts the run. Each stage produces evidence and passes its gate before the next begins.

## Models

- reader: gpt-5.6-luna. bounded extraction and deterministic coverage.
- judge: inherited GPT-6. pricing, engineering and ambiguity judgement.
- vision: gpt-6-astra. one-image blind source observation and contextual material judgement, followed by script validation.
- image_review: gpt-5.6-terra. efficient generated-image quality review against saved source evidence, geometry and lighting references.

The pinned b512 pack reads these profiles as planning metadata. The current 23d managed harness binds only the declared catalogue_reader and readiness_judge roles to their managed_model values; every other stage remains planning metadata until a reviewed role and adapter exist. Record selected and actual model independently.

## Orchestration

Own the end-to-end company outcome, dependencies, gates and publication plan. Delegate bounded work using file references and compact return records.

Scripts extract and reconcile. Cheap reader models receive the actual extracted text and record which pages they read; script-produced records alone never count as semantic model reads.

Dedicated Terra workers call native GPT Image and inspect generated outputs against material-zone briefs, geometry and lighting references. Source-photo description remains one anonymous asset per Astra call with echoed ID, immutable observation and subsequent script comparison. Parent receives compact IDs, verdicts, measured usage and one review sheet.

Use one GPT Image production model. Improve per-item physical material-zone prompts under the same saved reference lighting; preserve source, finish, coating and cut-face distinctions.

Record actual model/calls when exposed; unknown billing stays null. Keep source hashes, compact prompts, retries and rejected outputs. Preserve inherited records.

Extract source text deterministically, then give it to cheap readers in bounded visible batches; record extraction counts separately from semantic reads. Keep image outputs and individual visual reviews inside image workers. Hardlink originals; return compact receipts and one sheet. Use one angled view; preserve separately evidenced exterior, interior and cut-face material. Compressed source texture is evidence of finish class, not permission to magnify compression into pits or deep grain. One rejected view holds its angled image. Use explicit material routing and dimension drawings while imagery is held. Use up to four metered API generation workers and serialize heavy geometry renders; preserve disk headroom and avoid duplicating native images. Reuse a angled image across dimension, thickness and length variants when their section/material/finish look the same; catalogue row count never determines generation count. User-approved Terra reviews generated outputs; Astra retains source-photo truth checks.

## Stages

### 1. discover

Discover every public page, price source and downloadable file. Honour robots and crawl bounds. Record source dates and hashes.

Model profile: reader. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"discover-check.json","path":"passed","operator":"eq","expected":true}`.

### 2. catalogue

Read every product, price basis, MOQ, quantity step, selling rule and worked example. A source-specific parser is company state; every row has an outcome and evidence. Resolve conflicts by dated canonical source.

Model profile: judge. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"catalogue-check.json","path":"passed","operator":"eq","expected":true}`.

### 3. page

Build the complete delivery-menu flow. Reproduce source arithmetic; quote ambiguous rows on confirmation. Walk all item shapes, English and source language, at 1600,390,320 px; inspect screenshots.

Model profile: judge. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"page-check.json","path":"passed","operator":"eq","expected":true}`.

### 4. picture-pilot

Execute imagery.json: reconcile all image links first; exclude parent/family samples and cross-material reuse, including reframed copies. Send one anonymous asset per fresh Astra call, require exact echoed ID, save blind description then script-check against catalogue. Contextual review may use catalogue evidence while preserving blind outputs. Generate six macros with the configured GPT Image production model from verified own-type crops and exact structural renders under the actual owner lighting. Compare providers only when explicitly requested. Show one sheet and obtain operator approval.

Model profile: vision. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"picture-approval.json","path":"approved","operator":"eq","expected":true}`.

### 5. pictures

Execute imagery.json with dedicated image workers: one GPT Image model, one angled product image for each verified visual material variant. Compile compact evidence-backed outside, inside, cut-face and coating instructions under the same owner-reference lighting. Route SKU photos by verified variant. Terra inspects every generated output; source-image blind description remains Astra; record hashes, model, prompt, receipt, verdict and bounded retries. Preserve unresolved source gaps. Before production, record the operator-selected delivery scope: full onboarding or a named sales checkpoint. Enumerate included visual families, exact SKU reuse, held source inputs and the remaining onboarding backlog. A checkpoint passes only its explicitly approved scope; never report it as whole-catalogue studio coverage. Use representative catalogue dimensions, close long-stock framing and a single shared studio reference across all products.

Model profile: image_review. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"picture-coverage.json","path":"approved_scope_complete","operator":"eq","expected":true}`.

### 6. store

Ingest facts with sources, prices with history, unknown stock as listed, capacity as assumed, MOQ and steps. Export the exact catalogue projection. Estimate from stock, calendar and capacity; acceptance reserves and books atomically.

Model profile: judge. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"store-check.json","path":"passed","operator":"eq","expected":true}`.

### 7. orders-claim

Wire order submission, pending company claims, branded bilingual email receipts and private order-management capabilities. Recompute prices server-side and preserve idempotency. Use the commissioned company sender, stable order subject and reply thread. Hold outbox until sending is authorized; reconcile uncertain sends before retry. Keep owner operations privileged, customer projections private and changes recorded.

Model profile: judge. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"orders-check.json","path":"passed","operator":"eq","expected":true}`.

### 8. refresh

Re-read price sources nightly with bounded retrieval. Compare source hashes, parse into a candidate, run coverage/price gates, then atomically ingest. Preserve known operational stock, overrides and order reservations. Escalate material ambiguities to the office.

Model profile: reader. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"refresh-check.json","path":"passed","operator":"eq","expected":true}`.

### 9. verify

Prove every source row, every catalogue type, every required image and both phone and desktop flows. Run repository gates. Record differences honestly and resolve before publication.

Model profile: judge. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"release-check.json","path":"passed","operator":"eq","expected":true}`.

### 10. publish

Prepare a reviewed package and exact publish plan. Publish only after explicit owner approval, verify served bytes, record release and rollback.

Model profile: judge. Record: actor, actual_model, started_at, finished_at, tool_calls, provider_calls, cost, retries, evidence, gate_result.

Gate: `{"artifact":"publish-check.json","path":"served_hashes_verified","operator":"eq","expected":true}`.

## Picture geometry and framing

Generated from `imagery.json`. Produce one consistent part across these views: angled_product.
Choose a common purchasable stock length from the catalogue. Record millimetres and the selection reason. Short source samples establish finish, not stock length.
Close product view. Long stock continues beyond the frame; one near end may establish section. Product scale comes from consistent proportions, not fitting its full length in frame.
Shared studio: #E4E2DE neutral-grey seamless sweep.
One reviewed image shared across every generated view and family; record its hash.
Hard directional key from upper left, consistent exposure and white balance, controlled specular reflections, common shadow direction and softness.
Compare the complete single-view delivery sheet across families. Material appearance may vary; the photographic studio stays fixed.
Record master geometry: sku, section_dimensions_mm, represented_length_mm, dimension_basis, source_row, structural_mesh_sha256, finish_feature_evidence, camera_position, camera_target, focal_length_mm, sensor_width_mm, focus_distance, aperture, edge_radius_or_bevel_evidence, texture_scale_basis.
Keep the same mesh across views; change cameras only. Check section ratio, length-to-width ratio, object count, end shape, consistent finish features, same cut-face metal zone.
Inspect the neutral angled structure and its dimensions. Resolve variant bindings before generation.
Compare the generated angled image against its structural reference and the complete delivery against one studio anchor. Record specific gate verdicts and evidence.
Stop on failed structure before spending. Generate one angled image per approved visual family. Retry only after a concrete correction within the batch budget.

## Execution

Run `python manufacturer.py next --state <evidence-dir> --database <company.db>`.
Carry out that stage using the declared tools and company-specific adapters. Record actor, actual model, calls, cost, retries and evidence in stage_runs. Use null for measurements the runtime does not expose.
Run `python manufacturer.py check <stage> --state <evidence-dir> --database <company.db>` before marking a stage complete.
Source facts, image references, company adapters and decisions live with that company's store. The template remains reusable.
