# Manufacturer communication service

This optional customer-hostable package runs Chatwoot Community Edition behind the existing Rocoto manufacturer UI. Each customer receives one Compose project, Chatwoot account, application token, signing secret, Postgres database, Redis and attachment volume. Chatwoot owns new human and email history; Rocoto owns orders, proposals, review capabilities and fulfillment. The [adapter](../../verticals/manufacturer/manufacturer_chatwoot.py) stores bindings, operation hashes and bounded event receipts. The [routes](../../verticals/manufacturer/manufacturer_chatwoot_routes.py) keep tokens on the server and verify event signatures before opening a workspace.

The first target is a private loopback service beside the owned Rocoto demo on `rocoto-staging`. A customer installation uses a **separate supported Linux VM** with Docker Engine and Compose v2. The client's existing Windows Server 2012 R2, MACS desktop clients and reported IRIS database remain its existing system. IRIS vendor/version and the MACS import format are still to be verified. This package supplies communication services; it makes no claim of a MACS connector or direct IRIS writes.

## Package and license

The pinned application is `chatwoot/chatwoot:v4.18.0-ce`, the latest stable upstream release verified on 19 October 2026. Images are pinned to registry manifest digests in [compose.yaml](compose.yaml); the package fetches prebuilt images instead of building Rails/Node on the development host. The official [CE publication workflow](https://github.com/chatwoot/chatwoot/blob/v4.18.0/.github/workflows/publish_foss_docker.yml) strips `enterprise/` before producing the `-ce` image. Community code carries the [MIT license](CHATWOOT-LICENSE); bundled third-party components retain their own licenses. Enterprise features and licensing are outside this package.

The application uses the pinned release's `api_access_token` header. Current upstream documentation also describes Bearer authentication for v4.19 and later; the implementation follows the v4.18 source. Its native webhook signature is `X-Chatwoot-Signature: sha256=HMAC(secret, timestamp + '.' + raw_body)`, accompanied by `X-Chatwoot-Timestamp`. The delivery ID header is outside the signed bytes, so receipts dedupe by signed payload hash.

Upstream evidence: [stable release](https://github.com/chatwoot/chatwoot/releases/tag/v4.18.0), [Application API authentication](https://github.com/chatwoot/chatwoot/blob/v4.18.0/app/controllers/concerns/access_token_auth_helper.rb), [webhook signing](https://github.com/chatwoot/chatwoot/blob/v4.18.0/lib/webhooks/trigger.rb), [email channel fields](https://github.com/chatwoot/chatwoot/blob/v4.18.0/app/models/channel/email.rb), [message creation](https://github.com/chatwoot/chatwoot/blob/v4.18.0/app/builders/messages/message_builder.rb), [official Docker guide](https://developers.chatwoot.com/self-hosted/deployment/docker).

## Host resources and network

Rails and Sidekiq each have a 1,280 MiB memory cap; Postgres has 768 MiB and Redis 256 MiB, totaling 3.5 GiB. These are small-trial limits, with two Rails threads and two Sidekiq workers. Measure memory, queue latency and disk after commissioning; a larger customer deployment needs its own capacity review. Reserve space for images, attachments and database backups.

Only Rails binds a host socket: `127.0.0.1:3110`. Postgres and Redis use the internal project network. The app and worker have an egress network for signed callbacks and, after commissioning, the owned mailbox. The initial `--headless-local` mode uses HTTP on loopback for the server API and the existing manufacturer HTTPS origin for callbacks; its `FRONTEND_URL` is app metadata. It sets `FORCE_SSL=false` inside the private service. The default public mode uses `FORCE_SSL=true` and Caddy HTTPS; [chatwoot.caddy.example](chatwoot.caddy.example) names the proxy structure. A distinct public communication hostname is used for the server API and operator setup; customer-facing navigation remains in Rocoto.

The `.env` provides `REDIS_PASSWORD` to both app services. The pinned release's [Redis configuration](https://github.com/chatwoot/chatwoot/blob/v4.18.0/lib/redis/config.rb) and ActionCable read it separately from `REDIS_URL`. Database, Redis, Rails signing and Active Record encryption secrets are unique per instance. The three Active Record encryption keys protect supported mailbox and webhook secrets in the database and must accompany encrypted backups.

## Prepare and commission

[prepare_instance.py](prepare_instance.py) creates a private instance directory and starts zero services. Run it on the selected Linux host, with the native workspace's exact company scope:

```sh
python3 prepare_instance.py \
  --out ~/.local/state/manufacturer-order-desk/chatwoot \
  --project rocoto-sample-hardware-chatwoot \
  --company-id '<native-company-scope>' \
  --environment demo \
  --public-origin https://communications-demo.example.com \
  --callback-url https://manufacturer-demo.example.com/hooks/manufacturer-chatwoot/demo \
  --operator-email '<owned-operator-email>'
```

For the initial headless demo, add `--headless-local`, use the existing manufacturer demo as `--public-origin`, and keep the callback on that same public HTTPS origin. This requires neither a public Chatwoot dashboard nor a separate DNS record.

An optional `--email '<owned-company-mailbox>'` creates a disabled Email inbox during bootstrap. Provider passwords are supplied separately through the server-only `configure_email_inbox()` operator method. The generated operator input and `.env` are mode 0600. Keep them outside Git and terminal output.

From that private directory, after the host and its domain have been commissioned:

```sh
docker compose config --quiet
docker compose pull
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose run --rm rails bundle exec rails runner /operator/bootstrap.rb
docker compose up -d
```

[bootstrap.rb](bootstrap.rb) requires a fresh customer database. It creates a confirmed operator, its account, a private API inbox and a signed account webhook, then writes `operator/bootstrap-result.json` as mode 0600. If the database was initialized but the result file was lost, inspect that account and recover the exact credentials through its private admin path; the script refuses to create a duplicate installation.

In public mode, install the selected Caddy origin and prove its TLS/API connection. In headless mode, prove the loopback API and the signed callback at the existing manufacturer HTTPS origin. Transfer the resulting account, inbox IDs, token and webhook secret into the native workspace configuration described below. Rotate or remove the bootstrap operator password after commissioning if another owned admin authentication method is selected. Bootstrap and API failures remain operational evidence, rather than successful connection claims.

## Native workspace configuration

The selected workspace receives `manufacturer-chatwoot.json`, mode 0600. All fields are required; `credentials_path` names an absolute private file. `company_id` must match the existing `.workspace-identity.json` company scope, and `environment_id` must match the selected native environment.

```json
{
  "schema_version": 1,
  "company_id": "<native-company-scope>",
  "environment_id": "demo",
  "origin": "https://communications-demo.example.com",
  "account_id": 1,
  "service_inbox_id": 1,
  "email_inbox_id": 0,
  "commissioned_until": 0,
  "evidence_id": "",
  "email_enabled": false,
  "email_evidence_id": "",
  "sender_email": "",
  "daily_send_limit": 20,
  "credentials_path": "/absolute/private/chatwoot-credentials.json"
}
```

The separate credentials file contains exactly `schema_version`, `company_id`, `environment_id`, `account_id`, `api_token` and `webhook_secret`. The four identity fields must match. Credentials are reread before each operation, so expiry, credential rotation and email withdrawal take effect immediately.

After a real API-inbox round trip, record its evidence ID and a bounded `commissioned_until` Unix timestamp. `GET /api/manufacturer/communication/status` reports missing configuration and configured channel readiness without contacting a provider. Its `connected: false` explicitly distinguishes configuration from a fresh live probe. A concrete API/history/webhook round trip supplies deployment proof.

The host mounts `register_conversations(..., host=host)`, which mounts status and the signed callback. The existing service/customer URLs switch to Chatwoot when that company configuration selects it. Service messages retain their native actor in the operation receipt; API-inbox `incoming` messages represent client members and `outgoing` represents the owner. Business order/proposal events continue to come from the native review store. Pre-cutover correspondence is available through the separate `/archive` routes. A selected but expired/broken configuration holds communication instead of creating a second new history.

Customer email history reads up to ten existing Chatwoot threads for the exact source-validated contact, with explicit coverage, and uses the newest thread for replies. New inbound threads associate signed evidence through the already bound contact ID. Unbound contacts stay available for review; webhooks cannot select another account or confirm a commercial proposal.

## Email activation and effects

The initial package sets global SMTP to a closed loopback endpoint (`127.0.0.1:1`). This is deliberate: upstream interprets an empty SMTP address as sendmail. Email inboxes start with both IMAP and SMTP disabled. Initial setup therefore admits zero external email sends.

Activate only the owning company's mailbox: verified IMAP SSL, verified SMTP TLS, exact sender identity and the native signing callback. `configure_email_inbox()` sends those settings through the Application API, keeps credentials server-side and returns a redacted receipt. Establish one approved owned-address round trip; only then record `email_evidence_id`, `sender_email`, a current expiry and `email_enabled: true`. The adapter rechecks live inbox flags, exact sender and recipient, current workspace membership, immutable demo origin and daily allowance before an explicit send. Demonstration customers remain fenced from external email.

Human sends and fixed `request_received`, `review_ready` and `request_confirmed` templates use the same transport boundary. A host caller derives template events from committed business state and produces the exact private review URL. The adapter exposes zero model tools. Email interpretation can consume provider evidence separately; message text grants zero business authority.

Chatwoot v4.18 supplies neither a persistent `echo_id` nor an API message idempotency contract. The adapter commits an uncertain operation hash before its one POST. A retry reconciles the operation marker against canonical Chatwoot history and never repeats the POST. A crash or missing receipt therefore remains visibly uncertain. Its `sent` default means queued/accepted, so Rocoto reports `accepted` until stronger provider evidence appears. Receipts retain only IDs/hashes/actor metadata; message bodies remain in Chatwoot.

## Backups, handoff and readiness

Implementation status on 19 October 2026: the adapter, existing-URL cutover and transferable package pass offline tests. Docker was installed on the Rocoto staging host by the parent implementation task; Chatwoot services have not been started or connected. API-chat, signed-webhook and mailbox round trips remain unproved. The Windows-native delivery architecture remains under discussion. Existing native conversations remain selected when this optional configuration is absent, and manual order capture has no Chatwoot dependency. Automatic business-notification scheduling is a separate unfinished integration; the adapter's deterministic template method is available to a future exact-version notification caller.

Back up Postgres, the attachment volume, private `.env`, encrypted credential files and the native adapter's binding/receipt database as one customer-owned set. Test restoration into a separate project and origin. Stop the Compose project to suspend processing; retain volumes for rollback. Keep the prior image digest and a pre-migration database backup when upgrading. Record the customer account, source commit, exact image digest, domains, approved operation scope and round-trip evidence in the owning company's operations record.

Offline tests prove account/company isolation, signature freshness, bounded receipts, duplicate suppression, uncertain-send reconciliation, setup holds, route cutover, native business-event preservation, source demo fencing and secret-free status/history. Test transports trap external calls. This package's creation itself supplies neither installed-host nor mailbox-round-trip evidence; commissioning records supply those facts.
