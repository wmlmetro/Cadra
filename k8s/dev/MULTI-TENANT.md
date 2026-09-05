# Multi-tenant routing (subdomain → database)

One Odoo deployment serves every client. The database is chosen **per request**
from the host's first label via Odoo's `dbfilter = ^%d$`:

| URL | `%d` | Database |
|-----|------|----------|
| `staging.app.cadra.ng` | `staging` | `staging` |
| `nrs.cadra.ng` | `nrs` | `nrs` |
| `jizzy.cadra.ng` | `jizzy` | `jizzy` |

**Invariant: the database name MUST equal the subdomain's first label.**

Config lives in:
- [`10-configmap-odoo.yaml`](10-configmap-odoo.yaml) — `dbfilter = ^%d$`, `list_db = False`, no `db_name`.
- [`41-odoo-deployment.yaml`](41-odoo-deployment.yaml) — server writes **no** `db_name`; probes carry a `Host` header for a real tenant.
- [`60-ingress.yaml`](60-ingress.yaml) — one host rule per tenant (shared `*odoo-paths` anchor) + a SAN TLS cert.

---

## One-time migration: rename the staging DB `odoo` → `staging`

The pre-existing staging database is named `odoo`, but `staging.app.cadra.ng`
resolves to `%d = staging`. Reconcile once:

```sh
NS=cadra-dev
# 1. Stop the server so nothing holds a connection to the source DB.
kubectl -n $NS scale deploy/odoo --replicas=0
kubectl -n $NS wait --for=delete pod -l app=odoo --timeout=120s

# 2. Rename the database (run inside the postgres pod, as the odoo superuser).
kubectl -n $NS exec statefulset/db -- \
  psql -U odoo -d postgres -c 'ALTER DATABASE odoo RENAME TO staging;'

# 3. REQUIRED — move the filestore to match (Odoo keys the filestore by DB
#    name: it reads filestore/<db>/). SKIPPING THIS = every attachment and
#    compiled asset bundle 404s, leaving /web blank with
#    "odoo.define is not a function" (web.assets_common 404). The DB rename
#    alone is NOT enough.
kubectl -n $NS exec deploy/odoo -- \
  sh -c 'mv /var/lib/odoo/filestore/odoo /var/lib/odoo/filestore/staging'
#    If `staging/` already exists (e.g. a module was installed before this
#    step ran), merge instead of move:
#      kubectl -n $NS exec deploy/odoo -- \
#        sh -c 'cd /var/lib/odoo/filestore && cp -rn odoo/. staging/'
#
#    NO CLUSTER ACCESS? Do it through CI instead (the Actions runner has
#    kubectl) — this merges old -> new on the live pod:
#      gh workflow run deploy-dev.yml --ref dev \
#        -f filestore_from=odoo -f filestore_to=staging

# 4. Point the bootstrap/upgrade Jobs at the new name: set the POSTGRES_DB
#    repo variable (used by .github/workflows/deploy-dev.yml) to "staging",
#    OR patch the secret directly:
kubectl -n $NS create secret generic cadra-db \
  --from-literal=POSTGRES_DB=staging \
  --from-literal=POSTGRES_USER=odoo \
  --from-literal=POSTGRES_PASSWORD=<pw> \
  --dry-run=client -o yaml | kubectl apply -f -

# 5. Apply the updated config + bring the server back.
kubectl -n $NS apply -f 10-configmap-odoo.yaml -f 41-odoo-deployment.yaml -f 60-ingress.yaml
kubectl -n $NS scale deploy/odoo --replicas=1
```

---

## Onboard a new client (e.g. `jizzy`)

1. **DNS** — point `jizzy.cadra.ng` at the ingress LoadBalancer.
2. **Ingress** — in [`60-ingress.yaml`](60-ingress.yaml): add `jizzy.cadra.ng`
   to the `tls.hosts` list and add a rule `- host: jizzy.cadra.ng` with
   `http: *odoo-paths`. Apply it (cert-manager re-issues the SAN cert).
3. **Brand** — copy `cadra_brand_nrs` → `cadra_brand_jizzy`; change the 3
   `--brand-primary*` hexes (in `static/src/css/brand.css`) and the params in
   `data/brand_params.xml` (`cadra.brand_short_name`, `cadra.brand_primary`,
   `cadra.brand_primary_dark`, optional `cadra.brand_logo` data URI).
   ⚠️ **REQUIRED: add a COPY line for it in [`Dockerfile.odoo.k8s`](../../Dockerfile.odoo.k8s)**
   (each module needs its own line — a glob would flatten them). Without this
   the module isn't on the image addons path and `-i`/`-u` silently ignore it
   ("invalid module names, ignored: …") so the brand never loads. Do NOT add
   brand modules to the shared `CADRA_BOOTSTRAP_MODULES` (that would brand every
   tenant) — install per-client via `bootstrap_extra_modules` / `install_modules`.
4. **Database** — create the DB named exactly `jizzy` and install the brand
   module alongside the shared list. **Run the bootstrap Job** — it installs
   the modules *and* provisions the tenant:
   ```sh
   # deploy-19 workflow, run_bootstrap=true, bootstrap_db=jizzy
   # (or the Job directly with POSTGRES_DB=jizzy)
   ```
   > **Installing modules is not provisioning a tenant.** The bare
   > `odoo -d jizzy -i <CADRA_BOOTSTRAP_MODULES> --stop-after-init` spelling
   > creates the database and installs the code, and stops there — it never
   > runs `scripts/bootstrap.py`, so the tenant ends up with **no
   > `myservice_api.jwt_secret`** and no API client. Nothing complains: the
   > login page renders, `/auth/token` returns a clean 401 for bad
   > credentials, and only a caller who supplies the *right* password gets a
   > `server_misconfigured` 500. Upgrading the tenant later does not fix it —
   > `-u` never runs bootstrap either. This is how `nrs19` and `test19` ended
   > up unable to authenticate; see `docs/handoffs/03-REPORT.md`.
   >
   > To repair a database already in that state, without re-seeding:
   > ```sh
   > odoo shell -c /etc/odoo/odoo.conf -d jizzy --no-http \
   >   <<< "exec(open('/mnt/extra-addons/scripts/bootstrap.py').read())"
   > ```
   > with `CADRA_SEED_PROFILE=` empty. `bootstrap.py` is idempotent — it
   > preserves an existing meaningful secret rather than rotating it.
5. **Seed** — run that client's seed script against DB `jizzy`.

`https://jizzy.cadra.ng` now serves the Jizzy tenant. No new pods.

---

## Test the routing locally (without disturbing your running dev stack)

Local dev keeps `db_name = odoo` and **no** dbfilter, so `localhost` works as
usual. To verify host→DB routing, launch a throwaway server with dbfilter on a
spare port and curl it with `Host:` headers (this is exactly how the mechanism
was validated):

```sh
docker run --rm -d --name dbfilter-test \
  --network myservicenrs_default -p 8099:8069 \
  -v "$PWD":/mnt/extra-addons:ro cadra-odoo:15.0-dev \
  odoo --db_host=db --db_user=odoo --db_password=odoo \
       --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/extra-addons/dist \
       --db-filter='^%d$' --workers=0 --max-cron-threads=0

curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: odoo.cadra.ng'  localhost:8099/web/login  # 200 (DB odoo)
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: jizzy.cadra.ng' localhost:8099/web/login  # 303 (no DB)
docker rm -f dbfilter-test
```
