# Cadra dev — one-time cluster setup

The `deploy-dev` GitHub Actions workflow assumes the cluster already has a few
pieces in place. These are **one-time, cluster-scoped** installs that the
workflow does NOT manage (it only owns the `cadra-dev` namespace objects).
Run these once per DOKS cluster, before the first deploy.

> ⚠️ Two settings here are **load-bearing and easy to lose on a reinstall**.
> They are called out with ⚠️ below. If the site ever returns "empty reply
> from server" or an untrusted cert again, re-check those two.

---

## 1. ingress-nginx

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/do/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod \
  -l app.kubernetes.io/component=controller --timeout=300s
```

DigitalOcean provisions a LoadBalancer for the controller Service. Find its IP:

```bash
kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{"\n"}'
```

### ⚠️ Proxy-protocol mismatch (the "empty reply from server" bug)

The DO `do/deploy.yaml` sets `do-loadbalancer-enable-proxy-protocol: "true"`
on the Service **and** `use-proxy-protocol: "true"` in the controller
ConfigMap. But our LoadBalancer is type `REGIONAL_NETWORK` (DO's L4 network
LB), which **ignores** that annotation — the real LB forwards raw TCP without
the PROXY header. nginx then waits for a PROXY header that never arrives and
closes every connection → `curl` reports "empty reply from server".

Fix: tell nginx NOT to expect proxy protocol (the network LB already
preserves the client source IP, so nothing is lost):

```bash
kubectl -n ingress-nginx patch configmap ingress-nginx-controller \
  --type merge -p '{"data":{"use-proxy-protocol":"false"}}'
```

The controller reloads automatically within a few seconds. **Re-apply this any
time ingress-nginx is reinstalled from the upstream manifest.**

Verify (should be 308, not "empty reply"):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Host: staging.app.cadra.ng" http://<LB_IP>/web/login
```

---

## 2. cert-manager + ClusterIssuer

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl -n cert-manager wait --for=condition=available deployment --all --timeout=180s

# ClusterIssuer (Let's Encrypt prod). Edit the email in the file first — a
# malformed address makes ACME registration fail.
kubectl apply -f k8s/dev/61-cluster-issuer.yaml
```

cert-manager watches the `cert-manager.io/cluster-issuer` annotation on the
`cadra` Ingress and auto-issues the cert into the `cadra-tls` secret via an
HTTP-01 challenge. Watch it reach Ready (note: `-w` takes one kind at a time):

```bash
kubectl get clusterissuer letsencrypt-prod
kubectl -n cadra-dev get certificate cadra-tls -w
```

The HTTP-01 challenge needs port 80 reachable through the LB — which depends
on the proxy-protocol fix in step 1 being in place.

---

## 3. DNS

Point the ingress host at the LoadBalancer IP from step 1:

```bash
# Example with doctl (zone = cadra.ng):
doctl compute domain records create cadra.ng \
  --record-type A --record-name staging.app --record-data <LB_IP> --record-ttl 300
```

cert-manager's HTTP-01 challenge will not validate until this resolves.

---

## 4. GitHub Actions config (for the deploy-dev workflow)

**Secrets** (Settings → Secrets and variables → Actions → Secrets):
- `DIGITALOCEAN_ACCESS_TOKEN` — PAT with registry + k8s scopes
- `POSTGRES_PASSWORD`
- `ODOO_MASTER_PASSWORD`
- `CADRA_JWT_SECRET` — ≥48 chars (`openssl rand -hex 32`)
- `CADRA_TEST_CLIENT_SECRET`
- `CADRA_TURNSTILE_SECRET` — optional; Cloudflare Turnstile secret key

**Variables** (same screen → Variables):
- `DO_REGISTRY_NAME` (e.g. `vendra-registry`)
- `DO_CLUSTER_NAME`
- `POSTGRES_DB`, `POSTGRES_USER` — optional, default `odoo`/`odoo`
- `VITE_TURNSTILE_SITEKEY` — optional; Cloudflare Turnstile sitekey

### Turnstile (optional, both halves or neither)

Login-form bot protection is off until both settings are present, and they
must come from the **same** Cloudflare Turnstile widget:

- `VITE_TURNSTILE_SITEKEY` is a *variable*, not a secret — it ships to every
  browser inside the frontend bundle. It is a **build arg**, so changing it
  needs a frontend rebuild (any push to `dev`), not just a pod restart.
- `CADRA_TURNSTILE_SECRET` reaches Odoo through the `cadra-odoo` K8s secret and
  is written to the `myservice_api.turnstile_secret` config parameter by
  bootstrap — so it only takes effect **after a bootstrap run**
  (`gh workflow run deploy-dev.yml --ref dev -f run_bootstrap=true`), and it
  applies to whichever tenant DB that run targets.

Setting the secret without the sitekey locks every user out of the login form:
the backend then demands a `turnstile_token` the frontend has no widget to
produce. Set the variable first, deploy, then add the secret and bootstrap.

Bootstrap only ever *writes* the parameter — clearing the GitHub secret will
not turn Turnstile back off, so that a Job which loses the variable can't
silently strip protection off a live tenant. To disable it, clear the
parameter on that tenant:

```bash
kubectl -n cadra-dev exec deploy/odoo-19 -- \
  sh -c 'echo "env[\"ir.config_parameter\"].sudo().set_param(\"myservice_api.turnstile_secret\", False); env.cr.commit()" | odoo shell -d <db> --no-http'
```

---

## 5. First deploy (initialises the database)

A normal push to `dev` skips the bootstrap Job. The very first deploy — which
must create the Odoo schema and install the modules — has to run it:

```bash
gh workflow run deploy-dev.yml --ref dev -f run_bootstrap=true
```

After this, ordinary pushes to `dev` work because the schema persists on the
Postgres PVC. Re-run with `run_bootstrap=true` only if you need to reinstall
modules or re-seed.

---

## Quick health check

```bash
# App, with a browser-trusted cert (no -k):
curl -sS -o /dev/null -w "%{http_code}\n" https://staging.app.cadra.ng/web/login   # expect 200

# In-cluster state:
kubectl -n cadra-dev get pods,svc,ingress,certificate
```
