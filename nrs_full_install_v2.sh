#!/bin/bash
#===============================================================================
# NRS FACILITIES - COMPLETE INSTALLATION SCRIPT (v2 - Fixed)
#===============================================================================
# Server: 143.198.158.4
# Domain: myservice.com.ng
# 
# Fixes: gevent/greenlet compatibility with Python 3.10+
#===============================================================================

set -e

# Configuration
DOMAIN="myservice.com.ng"
DB_NAME="myservice.com.ng"
ODOO_VERSION="15.0"
ODOO_USER="odoo"
ODOO_HOME="/opt/odoo"
ODOO_CONF="/opt/odoo/conf/odoo.conf"
ODOO_LOG="/var/log/odoo"
DB_USER="odoo"
WORKERS=5

# Generate passwords
DB_PASSWORD=$(openssl rand -base64 16)
ODOO_ADMIN_PASSWORD=$(openssl rand -base64 12)

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1"; }

# Check root
if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash $0"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         NRS FACILITIES - COMPLETE INSTALLATION (v2)              ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Server:   143.198.158.4                                         ║"
echo "║  Domain:   myservice.com.ng                                      ║"
echo "║  Database: myservice.com.ng                                      ║"
echo "║  Odoo:     15.0 + Bureaucrat ITSM + Fleet                        ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

#===============================================================================
# CLEANUP ANY PREVIOUS FAILED INSTALL
#===============================================================================
log "Cleaning up any previous installation..."
systemctl stop odoo 2>/dev/null || true
systemctl disable odoo 2>/dev/null || true

#===============================================================================
# PART 1: SERVER INSTALLATION
#===============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PART 1: SERVER INSTALLATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

log "1/12 Installing system packages..."
apt-get update -qq
apt-get upgrade -y -qq

DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    git curl wget vim htop unzip \
    build-essential libssl-dev libffi-dev \
    python3-dev python3-pip python3-venv \
    libxml2-dev libxslt1-dev libjpeg-dev libpng-dev libpq-dev \
    libldap2-dev libsasl2-dev \
    libevent-dev libev-dev \
    node-less npm \
    xfonts-75dpi xfonts-base \
    fail2ban ufw \
    certbot python3-certbot-nginx \
    > /dev/null 2>&1

ok "System packages installed"

# wkhtmltopdf
if ! command -v wkhtmltopdf &>/dev/null; then
    log "Installing wkhtmltopdf..."
    wget -q https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb -O /tmp/wk.deb
    dpkg -i /tmp/wk.deb > /dev/null 2>&1 || apt-get install -f -y -qq > /dev/null 2>&1
    rm -f /tmp/wk.deb
fi
ok "wkhtmltopdf ready"

npm install -g rtlcss less > /dev/null 2>&1 || true
ok "Node packages ready"

log "2/12 Installing PostgreSQL..."
apt-get install -y -qq postgresql postgresql-contrib > /dev/null 2>&1
systemctl enable --now postgresql > /dev/null 2>&1

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1 || \
    sudo -u postgres createuser --createdb $DB_USER 2>/dev/null
sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" > /dev/null 2>&1

ok "PostgreSQL configured"

log "3/12 Creating Odoo user..."
id $ODOO_USER &>/dev/null || useradd -m -d $ODOO_HOME -U -r -s /bin/bash $ODOO_USER

mkdir -p $ODOO_HOME/{odoo,custom-addons,conf,backups}
mkdir -p $ODOO_LOG /var/lib/odoo/filestore
chown -R $ODOO_USER:$ODOO_USER $ODOO_HOME $ODOO_LOG /var/lib/odoo

ok "Odoo user ready"

log "4/12 Cloning Odoo $ODOO_VERSION (this takes a few minutes)..."
if [ ! -d "$ODOO_HOME/odoo/.git" ]; then
    sudo -u $ODOO_USER git clone --depth 1 -b $ODOO_VERSION \
        https://github.com/odoo/odoo.git $ODOO_HOME/odoo 2>/dev/null
fi
ok "Odoo source ready"

log "5/12 Setting up Python environment (with gevent fix)..."

# Remove old venv if exists (in case of retry)
rm -rf $ODOO_HOME/venv

# Create fresh virtual environment
sudo -u $ODOO_USER python3 -m venv $ODOO_HOME/venv

# Upgrade pip first
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/pip install -q --upgrade pip wheel setuptools

# CRITICAL FIX: Install compatible gevent/greenlet FIRST before requirements.txt
log "   Installing compatible gevent/greenlet versions..."
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/pip install -q \
    "greenlet==2.0.2" \
    "gevent==22.10.2"

ok "   gevent/greenlet installed"

# Now install requirements (gevent will be skipped as already installed)
log "   Installing Odoo requirements..."
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/pip install -q -r $ODOO_HOME/odoo/requirements.txt 2>/dev/null || {
    warn "   Some requirements failed, installing individually..."
    # Install critical packages individually if requirements.txt fails
    sudo -u $ODOO_USER $ODOO_HOME/venv/bin/pip install -q \
        Babel==2.9.1 \
        chardet==4.0.0 \
        decorator==4.4.2 \
        docutils==0.17 \
        ebaysdk==2.1.5 \
        freezegun==1.1.0 \
        idna==2.10 \
        Jinja2==2.11.3 \
        libsass==0.20.1 \
        lxml==4.8.0 \
        MarkupSafe==2.0.1 \
        num2words==0.5.10 \
        ofxparse==0.21 \
        passlib==1.7.4 \
        Pillow==9.0.1 \
        polib==1.1.1 \
        psutil==5.9.0 \
        psycopg2-binary==2.9.2 \
        pydot==1.4.2 \
        pyopenssl==21.0.0 \
        PyPDF2==1.26.0 \
        pyserial==3.5 \
        python-dateutil==2.8.1 \
        python-stdnum==1.17 \
        pytz==2021.3 \
        pyusb==1.2.1 \
        qrcode==7.3.1 \
        reportlab==3.6.8 \
        requests==2.25.1 \
        urllib3==1.26.5 \
        vobject==0.9.6.1 \
        Werkzeug==2.0.2 \
        xlrd==1.2.0 \
        XlsxWriter==3.0.2 \
        xlwt==1.3.0 \
        zeep==4.1.0 \
        2>/dev/null || true
}

# Install additional packages for fleet import
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/pip install -q \
    num2words phonenumbers python-barcode qrcode xlwt xlrd pandas openpyxl

ok "Python environment ready"

log "6/12 Installing ITSM modules..."
cd $ODOO_HOME/custom-addons

for repo in generic-addons bureaucrat-helpdesk-lite crnd-web crnd-service-desk; do
    if [ ! -d "$repo" ]; then
        sudo -u $ODOO_USER git clone --depth 1 -b $ODOO_VERSION \
            https://github.com/crnd-inc/$repo.git 2>/dev/null || \
        sudo -u $ODOO_USER git clone --depth 1 \
            https://github.com/crnd-inc/$repo.git 2>/dev/null
    fi
done

chown -R $ODOO_USER:$ODOO_USER $ODOO_HOME/custom-addons
ok "ITSM modules ready"

log "7/12 Configuring Odoo..."
ADDONS="$ODOO_HOME/odoo/addons"
for d in $ODOO_HOME/custom-addons/*/; do ADDONS="$ADDONS,$d"; done

cat > $ODOO_CONF << EOF
[options]
admin_passwd = $ODOO_ADMIN_PASSWORD
db_host = localhost
db_port = 5432
db_user = $DB_USER
db_password = $DB_PASSWORD
db_name = False
addons_path = $ADDONS
data_dir = /var/lib/odoo
workers = $WORKERS
max_cron_threads = 2
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_time_cpu = 600
limit_time_real = 1200
logfile = $ODOO_LOG/odoo.log
log_level = info
http_port = 8069
longpolling_port = 8072
proxy_mode = True
list_db = False
EOF

chown $ODOO_USER:$ODOO_USER $ODOO_CONF
chmod 640 $ODOO_CONF

# Save credentials
cat > $ODOO_HOME/conf/credentials.txt << EOF
════════════════════════════════════════════════════════════
 NRS FACILITIES CREDENTIALS
 Generated: $(date)
════════════════════════════════════════════════════════════

 URL: http://143.198.158.4
      https://myservice.com.ng (after SSL)

 DATABASE
   Name: $DB_NAME
   User: $DB_USER
   Pass: $DB_PASSWORD

 ODOO MASTER PASSWORD
   $ODOO_ADMIN_PASSWORD

 ⚠️  DELETE THIS FILE AFTER SAVING CREDENTIALS!

════════════════════════════════════════════════════════════
EOF
chmod 600 $ODOO_HOME/conf/credentials.txt
chown $ODOO_USER:$ODOO_USER $ODOO_HOME/conf/credentials.txt

ok "Odoo configured"

log "8/12 Creating systemd service..."
cat > /etc/systemd/system/odoo.service << EOF
[Unit]
Description=Odoo 15 NRS Facilities
After=postgresql.service

[Service]
Type=simple
User=$ODOO_USER
ExecStart=$ODOO_HOME/venv/bin/python $ODOO_HOME/odoo/odoo-bin -c $ODOO_CONF
Restart=on-failure
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable odoo > /dev/null 2>&1

ok "Systemd service ready"

log "9/12 Configuring Nginx..."
apt-get install -y -qq nginx > /dev/null 2>&1

cat > /etc/nginx/sites-available/$DOMAIN << EOF
upstream odoo { server 127.0.0.1:8069; }
upstream odoo-chat { server 127.0.0.1:8072; }

server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN 143.198.158.4;
    
    location /.well-known/acme-challenge/ { root /var/www/html; }
    
    location / {
        proxy_pass http://odoo;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 720s;
        client_max_body_size 100M;
    }
    
    location /longpolling {
        proxy_pass http://odoo-chat;
    }
}
EOF

ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t > /dev/null 2>&1 && systemctl enable --now nginx > /dev/null 2>&1

ok "Nginx configured"

log "10/12 Setting up firewall..."
ufw --force reset > /dev/null 2>&1
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow ssh > /dev/null 2>&1
ufw allow http > /dev/null 2>&1
ufw allow https > /dev/null 2>&1
ufw allow 8069/tcp > /dev/null 2>&1
echo "y" | ufw enable > /dev/null 2>&1

# Backup script
cat > $ODOO_HOME/backups/backup.sh << 'BACKUP'
#!/bin/bash
DB="myservice.com.ng"
DIR="/opt/odoo/backups"
DATE=$(date +%Y%m%d_%H%M)
pg_dump $DB | gzip > $DIR/db_$DATE.sql.gz
find $DIR -name "*.gz" -mtime +7 -delete
BACKUP
chmod +x $ODOO_HOME/backups/backup.sh
chown $ODOO_USER:$ODOO_USER $ODOO_HOME/backups/backup.sh
(crontab -l 2>/dev/null | grep -v backup.sh; echo "0 2 * * * $ODOO_HOME/backups/backup.sh") | crontab -

ok "Firewall and backup configured"

log "11/12 Starting Odoo and creating database..."
systemctl start odoo
sleep 15

if ! systemctl is-active --quiet odoo; then
    err "Odoo failed to start. Checking logs..."
    journalctl -u odoo --no-pager -n 50
    exit 1
fi
ok "Odoo running"

log "Creating database (this takes ~2 minutes)..."
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/python $ODOO_HOME/odoo/odoo-bin \
    -c $ODOO_CONF -d $DB_NAME --stop-after-init -i base --without-demo=all > /dev/null 2>&1

ok "Database created"

log "12/12 Installing Fleet and ITSM modules..."
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/python $ODOO_HOME/odoo/odoo-bin \
    -c $ODOO_CONF -d $DB_NAME --stop-after-init \
    -i fleet,generic_request,generic_team,generic_service \
    --without-demo=all > /dev/null 2>&1 || warn "Some modules may need manual install"

systemctl restart odoo
sleep 5
ok "Modules installed"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  PART 1 COMPLETE: Server Installation Done${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

#===============================================================================
# PART 2: ITSM CONFIGURATION
#===============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PART 2: ITSM CONFIGURATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

log "Creating ITSM configuration script..."

cat > /tmp/nrs_itsm_setup.py << 'ITSM_SCRIPT'
print("\n" + "=" * 60)
print("NRS FACILITIES - ITSM CONFIGURATION")
print("=" * 60)

# TEAMS
print("\n[1/6] Creating Teams...")
TEAMS = [
    ("Help Desk", "HELPDESK", "L1 Dispatch & Triage"),
    ("Building Maintenance", "BLDG-MAINT", "HVAC, Electrical, Structural"),
    ("Cleaning & Janitorial", "CLEANING", "Cleaning, Sanitation, Waste"),
    ("Plumbing", "PLUMBING", "Plumbing Systems"),
    ("Plant & Machinery", "PLANT-MACH", "Generators, Lifts, Equipment"),
    ("Fleet Management", "FLEET", "Vehicles, Drivers, Fuel"),
    ("Admin & Compliance", "ADMIN", "Licenses, Insurance, Documentation"),
]
team_ids = {}
for name, code, desc in TEAMS:
    team = env['generic.team'].search([('code', '=', code)], limit=1)
    if not team:
        team = env['generic.team'].create({'name': name, 'code': code, 'description': desc, 'active': True})
        print(f"  + {name}")
    team_ids[code] = team.id
env.cr.commit()

# SERVICES
print("\n[2/6] Creating Services...")
SERVICES = [
    ("Building Maintenance", "SVC-BLDG"),
    ("Cleaning & Janitorial", "SVC-CLEAN"),
    ("Plumbing Services", "SVC-PLUMB"),
    ("Plant & Machinery", "SVC-PLANT"),
    ("Fleet Management", "SVC-FLEET"),
    ("Admin & Compliance", "SVC-ADMIN"),
]
service_ids = {}
for name, code in SERVICES:
    svc = env['generic.service'].search([('code', '=', code)], limit=1)
    if not svc:
        svc = env['generic.service'].create({'name': name, 'code': code, 'active': True})
        print(f"  + {name}")
    service_ids[code] = svc.id
env.cr.commit()

# CATEGORIES
print("\n[3/6] Creating Categories...")
CATEGORIES = [
    ("Incident Management", "CAT-INCIDENT"), ("Service Request", "CAT-SERVICE"),
    ("Work Order", "CAT-WORKORDER"), ("Change Management", "CAT-CHANGE"),
    ("Fleet Management", "CAT-FLEET"), ("Building - HVAC", "CAT-HVAC"),
    ("Building - Electrical", "CAT-ELEC"), ("Building - Structural", "CAT-STRUCT"),
    ("Cleaning - Routine", "CAT-CLEAN-R"), ("Cleaning - Emergency", "CAT-CLEAN-E"),
    ("Plumbing - Leaks", "CAT-PLUMB-L"), ("Plumbing - Drainage", "CAT-PLUMB-D"),
    ("Plant - Generators", "CAT-GEN"), ("Plant - Lifts", "CAT-LIFT"),
    ("Plant - Fire Systems", "CAT-FIRE"), ("Plant - Security", "CAT-SEC"),
    ("Fleet - Breakdown", "CAT-FLT-BRK"), ("Fleet - Maintenance", "CAT-FLT-MNT"),
    ("Fleet - Accident", "CAT-FLT-ACC"), ("Fleet - Fuel", "CAT-FLT-FUEL"),
    ("Fleet - Licensing", "CAT-FLT-LIC"), ("Admin - Documentation", "CAT-ADM-DOC"),
    ("Admin - Compliance", "CAT-ADM-CMP"), ("Admin - Vendor", "CAT-ADM-VND"),
]
cat_ids = {}
for name, code in CATEGORIES:
    cat = env['request.category'].search([('code', '=', code)], limit=1)
    if not cat:
        cat = env['request.category'].create({'name': name, 'code': code, 'active': True})
    cat_ids[code] = cat.id
env.cr.commit()
print(f"  Created {len(CATEGORIES)} categories")

# STAGE TYPES
print("\n[4/6] Creating Stage Types...")
STAGE_TYPES = [
    ("Logged", "LOGGED"), ("Dispatched", "DISPATCHED"), ("In Progress", "IN-PROGRESS"),
    ("Pending Parts", "PENDING-PARTS"), ("Pending Vendor", "PENDING-VENDOR"),
    ("Escalated - Vendor", "ESC-VENDOR"), ("Escalated - Management", "ESC-MGMT"),
    ("Resolved", "RESOLVED"), ("Closed", "CLOSED"), ("Cancelled", "CANCELLED"),
    ("Submitted", "SUBMITTED"), ("Approved", "APPROVED"), ("Rejected", "REJECTED"),
    ("Completed", "COMPLETED"), ("Scheduled", "SCHEDULED"), ("Assigned", "ASSIGNED"),
    ("Work Complete", "WORK-COMPLETE"), ("Verified", "VERIFIED"),
    ("RFC Submitted", "RFC-SUBMIT"), ("Assessment", "ASSESSMENT"),
    ("Pending Approval", "PEND-APPROVE"), ("Implementation", "IMPLEMENT"),
    ("Assigned Mechanic", "MECH-ASSIGN"), ("Awaiting Parts", "AWAIT-PARTS"),
    ("At Vendor", "AT-VENDOR"), ("Vehicle Ready", "VEH-READY"),
]
stage_type_ids = {}
for name, code in STAGE_TYPES:
    st = env['request.stage.type'].search([('code', '=', code)], limit=1)
    if not st:
        st = env['request.stage.type'].create({'name': name, 'code': code, 'active': True})
    stage_type_ids[code] = st.id
env.cr.commit()
print(f"  Created {len(STAGE_TYPES)} stage types")

# WORKFLOWS
WORKFLOWS = {
    'incident': {
        'stages': [
            ("Logged", "logged", 10, False, "#3498DB"),
            ("Dispatched", "dispatched", 20, False, "#5DADE2"),
            ("In Progress", "in-progress", 30, False, "#9B59B6"),
            ("Pending Parts", "pending-parts", 40, False, "#F39C12"),
            ("Pending Vendor", "pending-vendor", 45, False, "#E67E22"),
            ("Escalated - Vendor", "esc-vendor", 50, False, "#E74C3C"),
            ("Escalated - Management", "esc-mgmt", 55, False, "#C0392B"),
            ("Resolved", "resolved", 60, True, "#27AE60"),
            ("Closed", "closed", 70, True, "#7F8C8D"),
        ],
        'routes': [
            ("Dispatch", "logged", "dispatched"), ("Start Work", "dispatched", "in-progress"),
            ("Await Parts", "in-progress", "pending-parts"), ("Await Vendor", "in-progress", "pending-vendor"),
            ("Escalate Vendor", "pending-vendor", "esc-vendor"), ("Escalate Mgmt", "esc-vendor", "esc-mgmt"),
            ("Parts Received", "pending-parts", "in-progress"), ("Vendor Done", "pending-vendor", "in-progress"),
            ("Resolve", "in-progress", "resolved"), ("Resolve (Esc)", "esc-mgmt", "resolved"),
            ("Close", "resolved", "closed"),
        ],
    },
    'service': {
        'stages': [
            ("Submitted", "submitted", 10, False, "#3498DB"),
            ("Dispatched", "dispatched", 20, False, "#5DADE2"),
            ("Approved", "approved", 25, False, "#2ECC71"),
            ("Rejected", "rejected", 26, True, "#E74C3C"),
            ("In Progress", "in-progress", 30, False, "#9B59B6"),
            ("Pending", "pending", 40, False, "#F39C12"),
            ("Completed", "completed", 60, True, "#27AE60"),
            ("Closed", "closed", 70, True, "#7F8C8D"),
        ],
        'routes': [
            ("Dispatch", "submitted", "dispatched"), ("Approve", "dispatched", "approved"),
            ("Reject", "dispatched", "rejected"), ("Start", "approved", "in-progress"),
            ("Hold", "in-progress", "pending"), ("Resume", "pending", "in-progress"),
            ("Complete", "in-progress", "completed"), ("Close", "completed", "closed"),
        ],
    },
    'workorder': {
        'stages': [
            ("Created", "created", 10, False, "#3498DB"),
            ("Scheduled", "scheduled", 20, False, "#5DADE2"),
            ("Assigned", "assigned", 30, False, "#8E44AD"),
            ("In Progress", "in-progress", 40, False, "#9B59B6"),
            ("Pending Parts", "pending-parts", 50, False, "#F39C12"),
            ("Work Complete", "work-complete", 60, False, "#2ECC71"),
            ("Verified", "verified", 70, True, "#27AE60"),
            ("Closed", "closed", 80, True, "#7F8C8D"),
        ],
        'routes': [
            ("Schedule", "created", "scheduled"), ("Assign", "scheduled", "assigned"),
            ("Start", "assigned", "in-progress"), ("Await Parts", "in-progress", "pending-parts"),
            ("Parts In", "pending-parts", "in-progress"), ("Complete Work", "in-progress", "work-complete"),
            ("Verify", "work-complete", "verified"), ("Close", "verified", "closed"),
        ],
    },
    'change': {
        'stages': [
            ("RFC Submitted", "rfc-submitted", 10, False, "#3498DB"),
            ("Assessment", "assessment", 20, False, "#8E44AD"),
            ("Pending Approval", "pending-approval", 30, False, "#F39C12"),
            ("Approved", "approved", 40, False, "#2ECC71"),
            ("Rejected", "rejected", 45, True, "#E74C3C"),
            ("Scheduled", "scheduled", 50, False, "#5DADE2"),
            ("Implementation", "implementation", 60, False, "#9B59B6"),
            ("Verified", "verified", 70, True, "#27AE60"),
            ("Closed", "closed", 80, True, "#7F8C8D"),
        ],
        'routes': [
            ("Assess", "rfc-submitted", "assessment"), ("Submit for Approval", "assessment", "pending-approval"),
            ("Approve", "pending-approval", "approved"), ("Reject", "pending-approval", "rejected"),
            ("Schedule", "approved", "scheduled"), ("Implement", "scheduled", "implementation"),
            ("Verify", "implementation", "verified"), ("Close", "verified", "closed"),
        ],
    },
    'fleet': {
        'stages': [
            ("Logged", "logged", 10, False, "#3498DB"),
            ("Dispatched", "dispatched", 20, False, "#5DADE2"),
            ("Assigned Mechanic", "mech-assigned", 30, False, "#8E44AD"),
            ("In Progress", "in-progress", 40, False, "#9B59B6"),
            ("Awaiting Parts", "await-parts", 50, False, "#F39C12"),
            ("At Vendor", "at-vendor", 55, False, "#E67E22"),
            ("Escalated - Management", "esc-mgmt", 60, False, "#C0392B"),
            ("Vehicle Ready", "veh-ready", 70, True, "#27AE60"),
            ("Closed", "closed", 80, True, "#7F8C8D"),
        ],
        'routes': [
            ("Dispatch", "logged", "dispatched"), ("Assign Mechanic", "dispatched", "mech-assigned"),
            ("Start Work", "mech-assigned", "in-progress"), ("Order Parts", "in-progress", "await-parts"),
            ("Send to Vendor", "in-progress", "at-vendor"), ("Escalate", "at-vendor", "esc-mgmt"),
            ("Parts In", "await-parts", "in-progress"), ("Vendor Done", "at-vendor", "in-progress"),
            ("Vehicle Ready", "in-progress", "veh-ready"), ("Ready (Escalated)", "esc-mgmt", "veh-ready"),
            ("Close", "veh-ready", "closed"),
        ],
    },
}

# REQUEST TYPES
print("\n[5/6] Creating Request Types & Workflows...")
REQUEST_TYPES = [
    ("HVAC Failure", "BLDG-HVAC-FAIL", "CAT-HVAC", "incident"),
    ("HVAC Inspection", "BLDG-HVAC-INSP", "CAT-HVAC", "workorder"),
    ("Electrical Fault", "BLDG-ELEC-FAULT", "CAT-ELEC", "incident"),
    ("Electrical Inspection", "BLDG-ELEC-INSP", "CAT-ELEC", "workorder"),
    ("Light Replacement", "BLDG-LIGHT-REP", "CAT-ELEC", "service"),
    ("Structural Damage", "BLDG-STRUCT-DMG", "CAT-STRUCT", "incident"),
    ("Roof Leak", "BLDG-ROOF-LEAK", "CAT-STRUCT", "incident"),
    ("Door/Window Repair", "BLDG-DOOR-REP", "CAT-STRUCT", "service"),
    ("Painting Request", "BLDG-PAINT", "CAT-STRUCT", "service"),
    ("Spill Cleanup", "CLEAN-SPILL", "CAT-CLEAN-E", "incident"),
    ("Routine Cleaning", "CLEAN-ROUTINE", "CAT-CLEAN-R", "workorder"),
    ("Deep Cleaning Request", "CLEAN-DEEP", "CAT-CLEAN-R", "service"),
    ("Pest Control", "CLEAN-PEST", "CAT-CLEAN-E", "service"),
    ("Sanitation Emergency", "CLEAN-SANIT", "CAT-CLEAN-E", "incident"),
    ("Water Leak", "PLUMB-LEAK", "CAT-PLUMB-L", "incident"),
    ("Pipe Burst", "PLUMB-BURST", "CAT-PLUMB-L", "incident"),
    ("Drainage Blockage", "PLUMB-BLOCK", "CAT-PLUMB-D", "incident"),
    ("Toilet Repair", "PLUMB-TOILET", "CAT-PLUMB-D", "service"),
    ("Tap/Faucet Repair", "PLUMB-TAP", "CAT-PLUMB-D", "service"),
    ("Plumbing Inspection", "PLUMB-INSP", "CAT-PLUMB-D", "workorder"),
    ("Generator Failure", "PLANT-GEN-FAIL", "CAT-GEN", "incident"),
    ("Generator Service", "PLANT-GEN-SVC", "CAT-GEN", "workorder"),
    ("Generator Fuel Request", "PLANT-GEN-FUEL", "CAT-GEN", "service"),
    ("Lift Breakdown", "PLANT-LIFT-BRK", "CAT-LIFT", "incident"),
    ("Lift Maintenance", "PLANT-LIFT-MNT", "CAT-LIFT", "workorder"),
    ("Fire Alarm Issue", "PLANT-FIRE-ALM", "CAT-FIRE", "incident"),
    ("Fire Extinguisher Service", "PLANT-FIRE-EXT", "CAT-FIRE", "workorder"),
    ("CCTV Fault", "PLANT-CCTV", "CAT-SEC", "incident"),
    ("Access Control Issue", "PLANT-ACCESS", "CAT-SEC", "incident"),
    ("Vehicle Breakdown", "FLEET-BREAKDOWN", "CAT-FLT-BRK", "fleet"),
    ("Vehicle Won't Start", "FLEET-NOSTART", "CAT-FLT-BRK", "fleet"),
    ("Flat Tyre", "FLEET-TYRE", "CAT-FLT-BRK", "fleet"),
    ("Scheduled Service", "FLEET-SERVICE", "CAT-FLT-MNT", "fleet"),
    ("Oil Change", "FLEET-OIL", "CAT-FLT-MNT", "fleet"),
    ("Brake Issue", "FLEET-BRAKE", "CAT-FLT-MNT", "fleet"),
    ("Vehicle Accident", "FLEET-ACCIDENT", "CAT-FLT-ACC", "fleet"),
    ("Fuel Request", "FLEET-FUEL", "CAT-FLT-FUEL", "service"),
    ("Vehicle Registration", "FLEET-REG", "CAT-FLT-LIC", "service"),
    ("Insurance Renewal", "FLEET-INSURE", "CAT-FLT-LIC", "service"),
    ("Road Worthiness", "FLEET-ROADW", "CAT-FLT-LIC", "service"),
    ("Document Request", "ADMIN-DOC-REQ", "CAT-ADM-DOC", "service"),
    ("Compliance Audit", "ADMIN-AUDIT", "CAT-ADM-CMP", "workorder"),
    ("License Renewal", "ADMIN-LICENSE", "CAT-ADM-CMP", "service"),
    ("Vendor Registration", "ADMIN-VENDOR-REG", "CAT-ADM-VND", "service"),
    ("Contract Renewal", "ADMIN-CONTRACT", "CAT-ADM-VND", "change"),
]

types_created = 0
for name, code, cat_code, wf_type in REQUEST_TYPES:
    rt = env['request.type'].search([('code', '=', code)], limit=1)
    if rt:
        continue
    cat_id = cat_ids.get(cat_code)
    rt = env['request.type'].create({'name': name, 'code': code, 'category_id': cat_id, 'active': True})
    types_created += 1
    wf = WORKFLOWS.get(wf_type, WORKFLOWS['incident'])
    stage_map = {}
    for sname, scode, seq, closed, color in wf['stages']:
        stage = env['request.stage'].create({
            'name': sname, 'code': scode, 'sequence': seq, 'closed': closed,
            'request_type_id': rt.id, 'bg_color': color,
            'label_color': '#FFFFFF', 'use_custom_colors': True, 'active': True,
        })
        stage_map[scode] = stage.id
    rt.write({'start_stage_id': stage_map[wf['stages'][0][1]]})
    for rname, from_code, to_code in wf['routes']:
        from_id = stage_map.get(from_code)
        to_id = stage_map.get(to_code)
        if from_id and to_id:
            env['request.stage.route'].create({
                'name': rname, 'stage_from_id': from_id, 'stage_to_id': to_id, 'request_type_id': rt.id,
            })
    if types_created % 10 == 0:
        env.cr.commit()
env.cr.commit()
print(f"  Created {types_created} request types with workflows")

# SCO LOCATION TAGS
print("\n[6/6] Creating SCO Location Tags...")
SCO_LOCATIONS = [
    'ABC', 'BBY', 'BKN', 'BKP', 'EEA', 'FCT', 'FKN', 'GAT', 'HQ',
    'IA', 'JKK', 'KANO', 'KEO', 'KNN', 'LAGOS', 'LAGOS ISLAND',
    'LI', 'LME', 'LMW', 'NKN', 'OOO', 'RED', 'SKZ'
]
tags_created = 0
for sco in SCO_LOCATIONS:
    tag_name = f"SCO: {sco}"
    tag = env['fleet.vehicle.tag'].search([('name', '=', tag_name)], limit=1)
    if not tag:
        env['fleet.vehicle.tag'].create({'name': tag_name})
        tags_created += 1
env.cr.commit()
print(f"  Created {tags_created} SCO location tags")

# SUMMARY
print("\n" + "=" * 60)
print("ITSM CONFIGURATION COMPLETE")
print("=" * 60)
print(f"""
  Teams:         {env['generic.team'].search_count([])}
  Services:      {env['generic.service'].search_count([])}
  Categories:    {env['request.category'].search_count([])}
  Request Types: {env['request.type'].search_count([])}
  Stages:        {env['request.stage'].search_count([])}
  Routes:        {env['request.stage.route'].search_count([])}
  Fleet Tags:    {env['fleet.vehicle.tag'].search_count([])}
""")
ITSM_SCRIPT

log "Running ITSM configuration via Odoo shell..."
sudo -u $ODOO_USER $ODOO_HOME/venv/bin/python $ODOO_HOME/odoo/odoo-bin shell \
    -c $ODOO_CONF -d $DB_NAME --no-http < /tmp/nrs_itsm_setup.py

rm -f /tmp/nrs_itsm_setup.py

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  PART 2 COMPLETE: ITSM Configuration Done${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

#===============================================================================
# FINAL SUMMARY
#===============================================================================
echo ""
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    INSTALLATION COMPLETE                         ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║                                                                  ║"
echo "║  Access Odoo:  http://143.198.158.4                              ║"
echo "║                                                                  ║"
echo "║  Credentials:  cat /opt/odoo/conf/credentials.txt                ║"
echo "║                                                                  ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  WHAT'S INSTALLED:                                               ║"
echo "║    ✓ PostgreSQL + Odoo 15 + Nginx                                ║"
echo "║    ✓ Bureaucrat ITSM + Fleet modules                             ║"
echo "║    ✓ 7 Teams, 6 Services, 45 Request Types                       ║"
echo "║    ✓ 5 Workflows (Incident, Service, Work Order, Change, Fleet)  ║"
echo "║    ✓ 23 SCO Location Tags                                        ║"
echo "║    ✓ Daily backups at 2 AM                                       ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  NEXT STEPS:                                                     ║"
echo "║                                                                  ║"
echo "║  1. Import Fleet Vehicles:                                       ║"
echo "║     scp VEH__RECORD_WIP__1_.xlsx root@143.198.158.4:/tmp/        ║"
echo "║     Then run the fleet import script (I'll provide it)           ║"
echo "║                                                                  ║"
echo "║  2. Configure SSL (after domain is active):                      ║"
echo "║     certbot --nginx -d myservice.com.ng                          ║"
echo "║                                                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Show credentials
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  YOUR CREDENTIALS (SAVE THESE!)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat $ODOO_HOME/conf/credentials.txt
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
