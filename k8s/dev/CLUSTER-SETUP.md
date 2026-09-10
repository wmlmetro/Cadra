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

**Cluster-only secret key** (not a GitHub secret — set directly on the
`cadra-odoo` K8s secret):

- `ODOO_ADMIN_PASSWORD` — the Odoo **admin user** password, used for XML-RPC by
  the one-off `cadra-nrs-import` Job (`k8s/dev/71-nrs-import-job.yaml`). Not the
  same thing as `ODOO_MASTER_PASSWORD`, which is the database manager's master
  password. It used to be baked into the import image as `admin`; a credential
  in an image layer is pulled by every host that runs the image and printed by
  `docker history`, so it has no default any more and the Job's entrypoint
  refuses without it.

  ```bash
  kubectl -n cadra-dev patch secret cadra-odoo --type merge \
    -p '{"stringData":{"ODOO_ADMIN_PASSWORD":"<password>"}}'
  ```

  `nrs-import.yml` pre-checks this key and fails naming it, because a missing
  `secretKeyRef` otherwise leaves the pod in `CreateContainerConfigError` with
  no logs at all.

**Variables** (same screen → Variables):
- `DO_REGISTRY_NAME` (e.g. `vendra-registry`)
- `DO_CLUSTER_NAME`
- `POSTGRES_DB`, `POSTGRES_USER` — optional, default `odoo`/`odoo`
- `VITE_TURNSTILE_SITEKEY` — optional; Cloudflare Turnstile sitekey

### Turnstile (optional, per tenant)

Login-form bot protection has two halves, and they must come from the **same**
Cloudflare Turnstile widget:

- `VITE_TURNSTILE_SITEKEY` is a *variable*, not a secret — it ships to every
  browser inside the frontend bundle. It is a **build arg**, so changing it
  needs a frontend rebuild (any push to `dev`), not just a pod restart. One
  bundle serves every tenant, so the widget must list **every** tenant
  hostname in its Cloudflare domain list.
- `CADRA_TURNSTILE_SECRET` reaches Odoo through the `cadra-odoo` K8s secret and
  is written to the `myservice_api.turnstile_secret` config parameter by
  bootstrap.

**Which tenants enforce it is decided by that parameter, not by the build.**
`GET /api/v1/brand` reports whether the tenant on that host has a secret set,
and the frontend renders the challenge only where it does. So the sitekey can
be rolled out to every tenant safely — the widget appears only on tenants you
have deliberately switched on.

#### Enabling tenants

1. Set both GitHub settings and push to `dev`. Nothing enforces yet.
2. Write the parameter for every tenant you intend to protect, in **one** run:

```bash
gh workflow run set-turnstile.yml --ref dev \
  -f dbs=staging,gtb,jaizbankplc,lasg -f action=enable
```

   The secret is not an input — the workflow reads `CADRA_TURNSTILE_SECRET`, the
   same value `deploy-dev` syncs into the `cadra-odoo` K8s secret, so the two
   can't drift. Prefer this over a bootstrap run: bootstrap also installs
   modules, touches admin groups, the API test client and the mail server, and
   can take well over an hour against a live tenant.

3. **Roll odoo-19.** Running HTTP workers cache `ir.config_parameter`, and a
   write from another process is *not* reliably picked up — observed
   propagating in one run and not the next on an identical setup. Until the
   roll, `/api/v1/brand` and `/auth/login` both keep reporting the old state.

```bash
gh workflow run deploy-19.yml --ref dev -f run_bootstrap=false
```

   odoo-19 uses Recreate on an RWO filestore, so the roll briefly interrupts
   **every** tenant. That is why step 2 does all the DBs at once — batch the
   changes and roll once.

4. Confirm per host:

```bash
curl -s https://staging.app.cadra.ng/api/v1/brand | jq .data.turnstile
```

#### Disabling a tenant

Bootstrap only ever *writes* the parameter — clearing the GitHub secret will
not turn Turnstile back off, so that a Job which loses the variable can't
silently strip protection off a live tenant. Clear it explicitly, then roll:

```bash
gh workflow run set-turnstile.yml --ref dev -f dbs=<db> -f action=disable
gh workflow run deploy-19.yml --ref dev -f run_bootstrap=false
```

A tenant that is switched on but whose hostname is missing from the Cloudflare
widget shows a "security check could not load" note and falls back to letting
the API decide — users are not locked out, but that tenant gets no protection
until the hostname is added.

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
