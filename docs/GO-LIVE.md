# Cadra — go-live ordering

The deployment steps whose **order** matters, and what breaks if they are taken
in the wrong one. This is the Cadra half of the ordering; the Vendra repository
carries its own copy, because a deployment order that breaks another system's
write path is not a Cadra-only fact.

This file is about the **DOKS `cadra-dev` cluster** (staging.app.cadra.ng and
the tenant hostnames). For the Docker Compose profiles see
[DEPLOYMENT.md](DEPLOYMENT.md).

---

## 1 · Every tenant is upgraded at or before the image roll

**Never roll the `odoo-19` image before `upgrade-19` has run for every tenant
database carrying the modules that changed.**

One Odoo process serves every database from one registry. The moment a new
stored field lands in the Python, a tenant that has not been upgraded is broken:
reading the column raises `UndefinedColumn`, and any serialiser that touches it
turns the endpoint into a 500.

This is not hypothetical. Handoff 09 added
`nrs.asset.category.verification_interval_days`, which `_compute_verified` reads
on **every `nrs.asset` create and write** — which is **Vendra's INT-03 write
path**. During that handoff the field landed before the fan-out finished and
`POST /api/v1/assets` 500'd for every call until it did.

```
Actions ▸ upgrade-19          # for every tenant DB, before anything rolls
Actions ▸ deploy-dev (roll_odoo = true)   # or deploy-19
```

`upgrade-19` scales `odoo-19` to 0 for the duration and restores it, and rolls
the image forward itself when every tenant succeeded — or back to the previously
deployed image when one failed, so the pods that come back match the schema they
will read.

---

## 2 · A ConfigMap change does not take effect until `odoo-19` is rolled

`odoo-config-19` reaches the container through a **`subPath` mount**, which
Kubernetes excludes from ConfigMap update propagation — the file inside a
running pod never changes — and the container copies it to `/tmp/odoo.conf` at
startup anyway. `odoo-bootstrap-19` arrives through **`envFrom`**, and a
process's environment is fixed when the process is created.

So `kubectl apply` on either one changes the cluster and changes **nothing that
is running**. `deploy-dev` applies both on every push to `dev` and deliberately
does **not** roll `odoo-19`, because it is `strategy: Recreate` on an RWO
filestore and a roll briefly interrupts every live tenant.

**Since handoff 10 this is loud rather than silent.** `deploy-dev` and
`deploy-19` both end by comparing the running pod against the ConfigMaps they
just applied and **failing the job** when they differ. To clear it:

* re-run **deploy-dev** with `roll_odoo = true`, or
* run **deploy-19** with `run_bootstrap = false`.

Both roll `odoo-19` and both briefly interrupt every live tenant. That
interruption is why it is a deliberate button and not something a push does on
its own.

**Settled 2026-09-08.** Handoff 09 set `publisher_warranty_url` in
`k8s/dev/10-configmap-odoo-19.yaml` to stop Odoo's `Publisher: Update
Notification` cron POSTing each tenant's company name, email and phone to
`services.odoo.com` weekly. Both halves are now live in the cluster, done by an
`upgrade-19` run at 06:54 UTC (run `34196778181`):

1. **`publisher_warranty_url`** — `upgrade-19` rolls the image forward at the
   end of its run, so the pod restarted onto the current ConfigMap. Confirmed
   independently by the guard in §2: it read `/etc/odoo/odoo.conf.template` out
   of the running pod and found it identical to the repo's.
2. **The per-tenant cron rows** — `myservice_nrs_base`'s `19.0.1.1.0`
   post-migrate ran on **staging, gtb, jaizbankplc and lasg**, each logging
   *"2 third-party scheduled action(s) deactivated"*.

**`nrs` did not run that migration, and does not need to.** Only 14 modules
load on that database against 77 on the others — our modules are not installed
there — so there is no `myservice_nrs_base` to deactivate anything. It is
covered by layer 1, which is a server-wide config setting and therefore applies
to every database the worker serves, installed modules or not. That is the
division of labour the module's own docstring describes: the config is the
durable half, the cron deactivation is the second layer.

---

## 3 · Turnstile's two halves go together

The sitekey is a **build arg** baked into the frontend bundle
(`VITE_TURNSTILE_SITEKEY`); the secret reaches Odoo through bootstrap
(`CADRA_TURNSTILE_SECRET`). A secret with no sitekey locks everyone out of the
login form. Set both, or neither.

---

## 4 · Provisioning a tenant is not installing modules

`-i` / `-u` never run `scripts/bootstrap.py`, so a database created the
documented way has **no `jwt_secret` and no API client** — `/auth/login` 500s
and no integration can authenticate. Use `deploy-19` with `run_bootstrap = true`
and a `bootstrap_db`, or run the bootstrap explicitly. See
`k8s/dev/MULTI-TENANT.md`.
