# myservicenrs

**NRS Facilities Service Manager** — Odoo 15 + Bureaucrat ITSM
Running at [myservice.com.ng](https://myservice.com.ng)

---

## What's in this repo

| Path                     | Purpose                                     |
| ------------------------ | ------------------------------------------- |
| `install.sh`             | One-shot server install (Ubuntu 22.04)      |
| `web/index.html`         | Portal homepage with live request search    |
| `data/itsm_structure.py` | ITSM Groups → Services → Categories → Types |
| `data/load_locations.py` | Nigeria zone/state/city skeleton            |
| `data/load_offices.py`   | Load 400+ office sites from CSV             |
| `scripts/load_all.sh`    | Run all data loaders in order               |
| `config/odoo.conf`       | Odoo config template                        |
| `config/nginx.conf`      | Nginx reverse proxy config                  |
| `config/odoo.service`    | Systemd unit file                           |

---

## Fresh server install (Ubuntu 22.04)

```bash
# Clone the repo
git clone https://github.com/sojiabolarin/myservicenrs.git /opt/odoo/myservicenrs
cd /opt/odoo/myservicenrs

# Run the installer (as root)
sudo bash install.sh
```

The installer handles everything end-to-end — system packages, PostgreSQL, Odoo 15,
Bureaucrat ITSM modules, database init, ITSM structure seed, location skeleton, and
Nginx reverse proxy.

**Estimated runtime: 15–25 minutes** on a clean VPS.

After install, credentials are saved to:

- `/etc/odoo/.masterpass` — Odoo master/admin password
- `/etc/odoo/.dbpass` — PostgreSQL database password

### Add SSL (after DNS propagates)

```bash
certbot --nginx -d myservice.com.ng
```

---

## ITSM Structure

```
Service Group (3)
├── Facility Management        4 services · 23 categories · 24 types
├── Security & Safety          4 services · 23 categories · 29 types
└── Fleet Management           6 services · 34 categories · 50 types

Total: 14 services · 80 categories · 103 types
```

Types are **operational action signals** — they tell the system what playbook to follow
without the requester needing to write a description.

**Incident Report** is a cross-cutting Type across all Security & Safety services, with
5 sub-variants (Security, Medical, Fire/Evacuation, Near-Miss, Civil).

**Permit to Work** is a single Type under Safety & Compliance. The PTW work type
(Hot Work, Confined Space, Height, Electrical) is captured via a custom request field.

---

## Location Tree

```
Zone (6)  →  State (36 + FCT)  →  City  →  Office Site  →  Building
```

Access cascades down: a zonal manager sees all states, cities, and offices below
their zone automatically.

### Load office sites

```bash
# Fill in locations/nrs_offices_template.csv (DO NOT commit the CSV)
# Then:
OFFICES_CSV=/path/to/nrs_offices.csv bash scripts/load_all.sh
```

---

## Re-running data loaders

All loaders are idempotent — safe to re-run on any database.

```bash
# Reload everything
bash scripts/load_all.sh

# Skip structure, reload locations only
SKIP_STRUCT=1 bash scripts/load_all.sh

# Skip locations, reload structure only
SKIP_LOCS=1 bash scripts/load_all.sh
```

---

## Portal homepage

`web/index.html` is a static page served by Nginx at `https://myservice.com.ng/`.

Features:

- Live request search via Odoo JSON-RPC (authenticated users only)
- Real-time stats (open, in-progress, closed this month)
- Quick-submit buttons per service group
- Redirects unauthenticated users to sign in before searching

The page detects the Odoo session automatically — no additional config needed.

---

## Notes

- `.gitignore` excludes all `locations/*.csv` files — never commit office data
- Bureaucrat ITSM requires a licence from [crnd.pro](https://crnd.pro)
- `generic.location` symlinks to other Odoo location models via:
  `Settings → Technical → Generic Location → Location Types → Link to Model`

https://staging.app.cadra.ng/web/database/manager
