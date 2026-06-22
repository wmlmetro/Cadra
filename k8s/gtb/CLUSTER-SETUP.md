# GTB dev — parallel instance setup

The GTB instance runs in the **`gtb-dev`** namespace on the **same DOKS cluster**
as `cadra-dev`. It reuses the cluster-scoped pieces already installed for
cadra-dev (ingress-nginx, cert-manager, the `letsencrypt-prod` ClusterIssuer)
and the same DigitalOcean Container Registry and GitHub Actions secrets.

Only the per-namespace objects, the brand layer (`gtb_theme`), the hostname and
the image tag prefix (`gtb-`) differ. See `k8s/dev/CLUSTER-SETUP.md` for the
full cluster-scoped setup (ingress-nginx proxy-protocol fix, cert-manager, etc.)
— **do not** re-run those; they are shared.

---

## 0. Things you must fill in first

These are placeholders in this overlay — replace before the first deploy:

| What | Where | Placeholder |
|------|-------|-------------|
| GTB hostname | `k8s/gtb/60-ingress.yaml` (3 spots: tls host, rule host) | `staging.app.gtb.ng` |
| GTB logo | `gtb_theme/static/src/img/logo.png` | solid-orange 280×80 PNG |
| GTB brand colours | `gtb_theme/static/src/css/brand.css` (`:root` block) | GTBank orange `#E35205` |
| Company display name | `gtb_theme/hooks.py` (`GTB_COMPANY_NAME`) | `"GTB"` |

---

## 1. DNS

Point the GTB host at the **same** ingress-nginx LoadBalancer IP that
`staging.app.cadra.ng` already uses (find it once via
`kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}'`):

```bash
# Example with doctl — adjust zone/record to the real GTB domain:
doctl compute domain records create gtb.ng \
  --record-type A --record-name staging.app --record-data <LB_IP> --record-ttl 300
```

cert-manager will then issue the `gtb-tls` cert for the GTB host automatically
(HTTP-01 challenge), driven by the `cert-manager.io/cluster-issuer` annotation
already on the GTB Ingress.

---

## 2. GitHub Actions config

`deploy-gtb.yml` reuses the **same** repo secrets and variables as `deploy-dev`
(`DIGITALOCEAN_ACCESS_TOKEN`, `POSTGRES_PASSWORD`, `ODOO_MASTER_PASSWORD`,
`CADRA_JWT_SECRET`, `CADRA_TEST_CLIENT_SECRET`, `DO_REGISTRY_NAME`,
`DO_CLUSTER_NAME`, …). Nothing new to add unless you want GTB to use a separate
DB password/JWT — in which case scope new values via a dedicated GitHub
Environment and point the `deploy` job's `environment:` at it.

> Note: the `deploy` job currently uses `environment: name: dev`. If that
> environment has required reviewers or is branch-restricted to `dev`, either
> relax it or create a `gtb` environment and switch the job to it.

The workflow triggers on push to the **`gtb`** branch, or via
**Run workflow** (workflow_dispatch).

---

## 3. First deploy (initialises the GTB database)

The very first deploy must run the bootstrap Job (creates the schema, installs
modules incl. `gtb_theme`; seed profile is empty, so no data is loaded):

```bash
gh workflow run deploy-gtb.yml --ref gtb -f run_bootstrap=true
```

After this, ordinary pushes to `gtb` roll the image without re-bootstrapping
(the schema persists on the `gtb-dev` Postgres PVC). Re-run with
`run_bootstrap=true` only to reinstall modules.

To pick up a `gtb_theme` change (new asset, version bump) without a full
re-bootstrap, dispatch with the upgrade input:

```bash
gh workflow run deploy-gtb.yml --ref gtb -f upgrade_modules=gtb_theme
```

---

## 4. Quick health check

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://<GTB_HOST>/web/login   # expect 200
kubectl -n gtb-dev get pods,svc,ingress,certificate
```
