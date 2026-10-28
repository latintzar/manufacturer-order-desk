# Native sample hosting

The hosted sample runs the same public source and SQLite writers as the local first result. The native visitor membership supplies read-only capabilities. All catalogue, customer, request, conversation and saved-version reads reach the actual server.

## Start locally

```sh
.venv/bin/python tools/dev.py --guest \
  --base-path /apps/manufacturer-order-desk/ \
  --workspace-port 18780 --orders-port 18781 \
  --state /absolute/owned/sample-state
```

Open `http://127.0.0.1:18780/apps/manufacturer-order-desk/`. Native `GET /api/session` admits a visitor automatically. The session cookie is `manufacturer_session`, HttpOnly and SameSite Strict, with Path `/apps/manufacturer-order-desk/`. The HTTPS public-origin setting also makes it Secure.

The public HTTP listener is loopback 18780. Its actual API lives under `/apps/manufacturer-order-desk/api/`; assets use `/apps/manufacturer-order-desk/static/`. `/apps/manufacturer-order-desk/orders/` proxies only the selected local Orders listener 18781. Keep 18781 private. Quotation POSTs run the original local pricing code; the public read-only mode holds order, file, configuration, messaging, session-login and observer mutations at the server.

Run without `--guest` to use the original owner sign-in and editable local workflow. A configured base path works in that mode too. The mount normalizes deployed URLs back to canonical resource paths before native JSON write handlers.

`web_mount.MountedApp` is a server deployment adapter. It prefixes actual HTML/JS/CSS/API resource URLs and cookie paths; the browser retains its native `fetch`. Shared SSE streams pass through. The product's saved-version inspector retains its existing pinned renderer and snapshot adapter, served from the real saved document. It is the same version inspector in the cloned product.

## Single-server systemd installation

`atelier-manufacturer-order-desk.service` targets the personal Atelier host, peter-projects. Vitrina is build/proof infrastructure. Installation is an operator step; source preparation does not change existing Vitrina or Atelier services.

1. Create dedicated system user/group `atelier-manufacturer`, shell `/usr/sbin/nologin`, home `/var/lib/atelier-manufacturer-order-desk`.
2. Check out the selected public commit into `/opt/atelier/manufacturer-order-desk/releases/COMMIT`. Keep source and dependencies owned by the operator and readable by the service user. Create its Python 3.12 `.venv` and install `requirements.lock` there.
3. Verify Node 22 at `/usr/bin/node`, as used by this unit. On a host with an isolated Node installation, set the unit PATH to that existing binary prefix.
4. Point `/opt/atelier/manufacturer-order-desk/current` at that release. Install this unit as `/etc/systemd/system/atelier-manufacturer-order-desk.service`; run `systemd-analyze verify`, daemon-reload and start the dedicated unit.
5. Reverse proxy the exact `/apps/manufacturer-order-desk/` prefix to loopback 18780, preserving the prefix and Host. The unit declares the public HTTPS origin. The application scopes its own cookie; the proxy supplies no session or API data.

The unit creates its mode 0700 state directory and uses umask 0077. The launcher gives its processes an owned empty HOME/config/cache namespace, strips ambient provider and state environment settings, and installs its loopback-only socket boundary. The systemd unit adds a dedicated unprivileged identity, read-only source, private temporary directory and loopback-only IP access. Keep model, scraping, SMTP, Chatwoot and managed identity credentials unconfigured in this sample.

Fresh state seeds six articles and two requests. Its `workspace/`, `orders/companies/sample-hardware/company.db`, public renderer, private transport token and owner code all belong to that state. Only the application HTTP paths are public. The owner code and transport JSON remain private mode 0600 files. Restarts preserve state and issue a fresh local owner code.

## Verification

```sh
.venv/bin/python tools/check_browser.py --guest \
  --workspace http://127.0.0.1:18780/apps/manufacturer-order-desk \
  --orders http://127.0.0.1:18780/apps/manufacturer-order-desk/orders
```

Check native reads, denied writes, observer escape, scoped cookies and the real quote endpoint. Review network counters when the own launcher stops. The global `ROCOTO_READ_ONLY=true` server option and the mount's `read_only=True` guard also protect an explicitly commissioned native observer; clearing observation stays held. Shared applications must retain their own membership and source-ownership contract.

[made by atelier neyra](https://atelierneyra.com)
