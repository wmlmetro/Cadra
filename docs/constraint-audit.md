# Constraint audit — `_sql_constraints` on Odoo 19

**Date:** 2026-09-05 · **Handoff:** 02 · **Stack audited:** Odoo 19.0
(`cadra-odoo:19.0-dev`), all local databases.

Odoo 19 removed the `_sql_constraints` model attribute. `orm/model_classes.py:162`
logs a warning and **creates nothing**, so every uniqueness and check constraint
declared that way silently ceased to exist. Nothing failed; no test went red. It
surfaced because someone read a log line.

This audit enumerates every declaration site in the repo, says which ones the
Odoo 19 process can actually see, and records what existed in each database
before and after the fix. **The audit is the deliverable even where a fix
waits** — an unenforced constraint you know about is manageable; one you do not
is not.

---

## Summary

| | Before | After |
|---|---|---|
| Declaration sites reachable by Odoo 19 | 8 | 0 |
| Constraints missing from each serving database | 8 | 0 |
| Missing constraint instances across 7 tenants | 56 | 0 |
| `_sql_constraints` warnings per registry load | 8 | 0 |
| Databases holding data that would violate a restored constraint | 0 | — |

All eight are now enforced in all seven serving databases. No deduplication was
needed anywhere: every constraint was clean on every tenant.

---

## What Odoo 19 can and cannot see

This is the finding that determines the scope of everything else. The two
vendored trees are **mutually exclusive by Odoo version**:

| Tree | Loaded by | `addons_path` entry |
|---|---|---|
| `dist/` (Odoo 15 vendor bundle) | Odoo **15** only | `config/odoo.dev.conf:17`, `config/odoo.prod.conf:26` |
| `crnd-19/`, `oca-19/` | Odoo **19** only | `config/odoo.19.conf:21` |

`config/odoo.19.conf` says so in its own comment — *"the legacy 15.0 vendor tree
(dist) is intentionally NOT on the path here"* — and the running process
confirms it. An addons-path entry's *immediate* children must be modules;
`dist/` is a child of `/mnt/extra-addons` (the repo root) and has no
`__manifest__.py`, so its 114 module directories sit one level too deep to be
seen. Resolving module paths inside the container:

```
generic_request          path=None
generic_system_event     path=None
crnd_wsd                 path=None
generic_location         path=/mnt/extra-addons/crnd-19/generic_location
generic_resource         path=/mnt/extra-addons/crnd-19/generic_resource
generic_team             path=/mnt/extra-addons/crnd-19/generic_team
```

Corroborated in the logs: `module generic_request: not installable, skipped`.

**Consequence:** the 61 constraints in `dist/` are **correct as they stand**.
They run on Odoo 15, where `_sql_constraints` is still honoured. Porting them
would be work with no effect on the 19 stack and a regression risk for the 15
stack that is still production. `_upgrade/` is likewise unreachable (not on the
path, three levels deep, and gitignored).

---

## Every declaration site in the repo

Counted by AST parse, so docstring and comment mentions are excluded and
multiple declarations in one file are counted separately.

| Tree | Files | Sites | Constraints | Reachable by Odoo 19 | Action |
|---|---:|---:|---:|---|---|
| first-party (repo root) | 3 | 3 | 3 | **yes** | **fixed** (1 in handoff 01, 2 here) |
| `crnd-19/` | 6 | 6 | 6 | **yes** | **fixed** here |
| `oca-19/` | 0 | 0 | 0 | yes | none present |
| `dist/` | 43 | 44 | 61 | **no** | **none — correct for Odoo 15** |
| `_upgrade/` | 13 | 17 | 20 | **no** | none — gitignored scratch |
| **Total** | **65** | **70** | **90** | **8 reachable** | |

Odoo core contributes nothing: only `lunch` and `test_orm` mention the
attribute, and neither is installed in any database.

### Corrections to the counts in handoff 02

- **"44 files in `dist/`"** — 43 files, 44 sites, 61 constraints. The 44th
  `grep` hit is a class *docstring* in `generic_mixin/models/generic_mixin_uuid.py`
  showing users how to declare a UUID constraint.
- **"8 in `crnd-19/`"** — 6 sites. Two of the 8 `grep` hits are the same
  docstring at `generic_mixin/models/generic_mixin_uuid.py:27` and `:61`.
- **"10 declaration sites affected"** (CLAUDE.md) — 8, and only 8 were ever
  reachable.
- **"305 warnings in the container log"** is not a measure of blast radius. The
  warning fires once per declaration site **per registry build**, and a registry
  is built per database per process. Clusters in the log are exact multiples of
  9, then of 8 after handoff 01 fixed `api_idempotency.py`. `305 = 33×9 + 8` —
  it measures **34 registry loads over 11 days**, not 305 broken objects.

---

## The eight live holes, before and after

No class in this set sets `_table`, so the table is the model name with dots
replaced by underscores.

| # | Site | Module | Model | Table | Constraint | Guarantee | Risk |
|---:|---|---|---|---|---|---|---|
| 1 | `myservice_asset_register/models/asset.py` | `myservice_asset_register` | `nrs.asset` | `nrs_asset` | `UNIQUE (asset_code)` | one asset per code | **identity — highest** |
| 2 | `myservice_staff_bus/models/bus_route.py` | `myservice_staff_bus` | `bus.route` | `bus_route` | `UNIQUE (code)` | one route per code | identity, low use |
| 3 | `crnd-19/generic_resource/models/generic_resource.py` | `generic_resource` | `generic.resource` | `generic_resource` | `UNIQUE (res_model, res_id)` | one resource row per Odoo record | **identity** |
| 4 | `crnd-19/generic_resource/models/generic_resource_mixin.py` | `generic_resource` | `generic.resource.mixin` (**abstract**) | inheritors' tables | `UNIQUE (resource_id)` | one inheritor row per resource | **identity** |
| 5 | `crnd-19/generic_resource/models/generic_resource_type.py` | `generic_resource` | `generic.resource.type` | `generic_resource_type` | `UNIQUE (model_id)` | one resource type per model | **identity** |
| 6 | `crnd-19/generic_resource/models/generic_resource_simple_category.py` | `generic_resource` | `generic.resource.simple.category` | `generic_resource_simple_category` | `UNIQUE (parent_id, name)` | no sibling categories alike | moderate |
| 7 | `crnd-19/generic_team/models/generic_team_member.py` | `generic_team` | `generic.team.member` | `generic_team_member` | `UNIQUE (user_id, team_id)` | no duplicate memberships | moderate |
| 8 | `crnd-19/generic_location/models/generic_location.py` | `generic_location` | `generic.location` | `generic_location` | `CHECK (name != description)` | title is not the description | **cosmetic** |

**#1 is the urgent one.** The September Integration Flow makes dual-code
reconciliation a named control point — *"an asset is complete only when both the
Cadra Asset Code and the SAP asset code are linked on the register"* — and
INT-06/07 matches a SAP asset code to exactly one Cadra asset. Without the
constraint two assets can share a code and the reconciliation silently matches
the wrong one.

**#4 is the subtle one.** It is declared on an `AbstractModel`, and
`crnd-19/generic_resource/models/ir_model.py:113` injects that mixin into models
**at runtime** from `generic.resource.type` rows, so the set of tables carrying
it is data-driven rather than code-driven. Today exactly one resource type is
configured (`generic.resource.simple`). Verified empirically that
`models.Constraint` on an abstract model does propagate to concrete inheritors
on Odoo 19:

```
generic_resource_simple_unique_resource_id on generic_resource_simple -> UNIQUE (resource_id)
```

---

## Per-database state

Nine databases exist. Two are out of scope:

- **`odoo`** — the `db_name` in `odoo.conf`, not a tenant. Its `ir_module_module`
  rows are stale Odoo 15 state referencing `generic_request` and
  `generic_system_event`, which live only in `dist/` and no longer resolve, so
  its registry load skips every affected module and it emits **zero** warnings.
  It does not serve the API.
- **`test19`** — module set identical to the tenants and carried all 8 holes, but
  has no `jwt_secret`, so `/auth/login` 500s. In scope for the fix, not usable
  for API tests. (`nrs19` has the same missing secret — pre-existing, unrelated
  to this work, flagged in report 02.)

### Before — constraints present / violating rows

Every serving database was missing all 8. Violating-row counts, which decide
whether a constraint can be applied at all:

| Database | `asset_code` dups | `bus_route.code` dups | `generic_resource` dups | mixin dups | category dups | resource-type dups | team-member dups | location check |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| jaizbankplc | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| lasg | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nrs | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gtb | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| cadra19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nrs19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gtb19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Also checked on `nrs_asset`, because a `UNIQUE` column with a placeholder value
would collide even with no true duplicates: `asset_code` is NULL in 0 rows,
empty in 0 rows, and `'/'` — the fallback `create()` uses when the sequence is
missing — in 0 rows. The `nrs.asset` sequence exists in all seven.

**So no deduplication was required, and no constraint had to wait behind a data
decision.** `nrs19` holds 11,878 assets and is clean.

### After — all eight enforced everywhere

| Database | constraints present (of 8) | assets |
|---|---:|---:|
| jaizbankplc | 8 | 371 |
| lasg | 8 | 150 |
| nrs | 8 | 1,272 |
| gtb | 8 | 150 |
| cadra19 | 8 | 1,322 |
| nrs19 | 8 | 11,878 |
| gtb19 | 8 | 156 |

Proven to bite, not merely to exist:

```
ERROR:  duplicate key value violates unique constraint "nrs_asset_asset_code_unique"
DETAIL:  Key (asset_code)=(Jaiz-AST-000244) already exists.
```

And reflected in Odoo's own registry, so a later upgrade will not drop them:

```
nrs_asset_asset_code_unique | u | UNIQUE (asset_code)
bus_route_code_unique       | u | UNIQUE (code)
```

---

## How the fix is spelled, and why it differs by tree

`models.Constraint` names a constraint `<table>_<attribute name without its
leading underscore>` (`orm/table_objects.py:55`), which is exactly what the
legacy list produced. The two spellings are therefore interchangeable in the
database, and no 15→19 database ends up with an orphan.

**Our own modules keep both spellings** behind an `_ODOO_MAJOR` check, because
the Odoo 15 stack is still production and still loads them:

```python
if _ODOO_MAJOR >= 19:
    _asset_code_unique = models.Constraint('UNIQUE (asset_code)', 'Asset code must be unique.')
else:
    _sql_constraints = [('asset_code_unique', 'unique(asset_code)', 'Asset code must be unique.')]
```

**`crnd-19/` uses the plain form**, no guard, because that tree is on the Odoo
19 addons path only.

---

## Why patching `crnd-19/` costs nothing

The usual objection to patching vendored code is that the next upstream refresh
clobbers it. That does not apply to the three modules involved.
`scripts/fetch-crnd-19.sh` clones only the **public** generic-addons repo, and
its own closing note lists exactly these as *not* fetched:

```
==> STILL REQUIRED (not fetched — gated / paid):
    LGPL (get from CRND account OR port dist/<mod> 15.0 -> 19.0):
        generic_service  generic_resource  generic_location  generic_team
```

So `generic_resource`, `generic_location` and `generic_team` are **our own
15→19 forward-ports**, hand-placed in `crnd-19/`. Re-running the fetch script
will not overwrite them.

That also explains the pattern. `crnd-19/generic_tag`, `generic_mixin` and
`generic_crypto_utils` came from the public repo and already carry 13
`models.Constraint` declarations — upstream did their 19 port properly. The
three unported modules are precisely the three we ported ourselves from
`dist/`, where `_sql_constraints` was still correct. **These six were our own
porting bug, not vendor debt**, which is why they are fixed here rather than
escalated.

---

## Preventing recurrence

`tests/test_source_guards.py::test_no_unguarded_sql_constraints` fails when
`_sql_constraints` is declared unguarded anywhere in `myservice_*` or
`cadra_brand_*`. It parses the AST rather than grepping, so it accepts the
legitimate `else:` branch of the version guard and rejects a bare class-body
declaration. It needs no running instance:

```
tests/.venv/bin/python -m pytest tests/test_source_guards.py
```

Two companion tests keep the guard honest: one asserts it actually flags a
reintroduced declaration (otherwise a bug in the AST walk would make it pass
forever and silently stop guarding — the same failure mode it exists to
prevent), and one asserts it is scanning the modules we think it is, so a path
typo cannot make it pass vacuously.

The guard deliberately does **not** cover `dist/`, `crnd-19/` or `oca-19/`.
`dist/` must keep the old spelling. For the other two, a future upstream refresh
could reintroduce the pattern; the check to add then is a startup assertion on
the warning, not a source test. Until then, `docker logs myservicenrs-odoo-1 |
grep -c "no longer supported"` returning anything but 0 after a restart is the
signal that something regressed.
