# nrs_watchlist — NRS SOC Watchlist Module
## WestMetro Limited | myservice.com.ng

### Module Overview
Full SOC watchlist management with:
- `nrs.watchlist.subject` model — mugshot, threat tier, status, charge, location, API source
- Kiosk board (OWL client action) — auto-scrolling mugshot grid, tier/status filters, search
- Detail overlay — full subject card with Flag / Alert / Clear actions
- Standard Odoo views — Kanban (mugshot board), List, Form with chatter
- Security groups — Viewer / Operator / Administrator
- API-ready — `get_board_data()` RPC endpoint for external feed integration
- 12 demo records pre-loaded

### Dependencies
- `myservice_security` — parent Security & Safety menu must exist
- `mail` — chatter / tracking
- `generic_request` (Bureaucrat ITSM) — for linked incidents

### Deployment

#### 1. Copy to addons path
```bash
cp -r nrs_watchlist /opt/odoo/myservicenrs/
```

#### 2. Commit and push to security-ops branch
```bash
cd /opt/odoo/myservicenrs
git add nrs_watchlist/
git commit -m "feat: nrs_watchlist SOC watchlist board module"
git push origin security-ops
```

#### 3. Pull on server (already on security-ops)
```bash
cd /opt/odoo/myservicenrs
git pull origin security-ops
```

#### 4. Install module
```bash
cd /opt/odoo
sudo -u odoo /opt/odoo/venv/bin/python3 odoo/odoo-bin \
    -c /etc/odoo/odoo.conf -d myservice \
    --update nrs_watchlist --stop-after-init
```

Or install via Odoo UI: Settings → Apps → search "watchlist" → Install

### Adding Real Photos
- **Odoo upload**: Open subject form → upload to Photo field (JPEG/PNG, passport style)
- **External URL**: Set `photo_source = url`, paste URL in `photo_url` field
- **API auto**: Set `photo_source = api`, set `api_record_id` — implement feed connector

### API Feed Integration (future)
The `get_board_data()` method on `nrs.watchlist.subject` returns JSON-serialisable
subject data for the JS board. To integrate DSS/NPF/INTERPOL:
1. Create a scheduled action (cron) that calls the external API
2. Upsert records by `api_record_id` to avoid duplicates
3. Set `last_api_sync` on each synced record
4. Update `photo_url` from the API response

### File Structure
```
nrs_watchlist/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── watchlist_subject.py       # Core model
├── views/
│   ├── watchlist_views.xml        # Form, List, Kanban, Search, Actions
│   └── watchlist_menus.xml        # Menu items under Security & Safety
├── static/src/
│   ├── js/watchlist_board.js      # OWL board component
│   ├── xml/watchlist_board.xml    # OWL templates
│   └── css/watchlist.css          # Dark SOC theme
├── security/
│   ├── watchlist_security.xml     # Groups + sequence
│   └── ir.model.access.csv        # ACL
└── data/
    └── watchlist_demo.xml         # 12 demo subjects
```
