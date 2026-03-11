#!/bin/bash
# ==============================================================================
# NRS myservice.com.ng — Full Server Install Script
# Ubuntu 22.04 LTS · Odoo 15 · Bureaucrat ITSM
#
# Usage:
#   sudo bash install.sh
#
# What this does (in order):
#   1.  System packages & dependencies
#   2.  PostgreSQL setup
#   3.  Odoo 15 user & directory structure
#   4.  Python virtualenv & Odoo requirements
#   5.  Odoo 15 source from CRND (includes Bureaucrat ITSM)
#   6.  wkhtmltopdf (PDF reports)
#   7.  odoo.conf from config/odoo.conf template
#   8.  Systemd service
#   9.  Nginx reverse proxy
#   10. Database creation
#   11. Bureaucrat ITSM module installation
#   12. ITSM structure seed  (Groups / Services / Categories / Types)
#   13. Location skeleton    (Zones / States / Cities)
#   14. Portal homepage      (web/index.html → Odoo website assets)
#
# After install:
#   - Access Odoo at http://myservice.com.ng
#   - Add SSL:  certbot --nginx -d myservice.com.ng
#   - Load offices:  OFFICES_CSV=/path/to/file.csv bash /opt/odoo/myservicenrs/load_all.sh
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# CONFIG — edit these before running
# ------------------------------------------------------------------------------
DOMAIN="myservice.com.ng"
DB_NAME="myservice"
DB_USER="odoo"
DB_PASS="$(openssl rand -base64 24)"          # auto-generated, saved to /etc/odoo/.dbpass
ODOO_USER="odoo"
ODOO_HOME="/opt/odoo"
ODOO_VENV="${ODOO_HOME}/venv"
ODOO_CONF="/etc/odoo/odoo.conf"
ODOO_LOG="/var/log/odoo/odoo.log"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADMIN_PASS="$(openssl rand -base64 16)"       # Odoo master password

# Bureaucrat ITSM modules to install (order matters)
ITSM_MODULES=(
    "generic_location"
    "generic_request"
    "generic_request_field"
    "generic_request_service"
    "generic_service"
    "generic_service_group"
    "generic_request_kind"
    "generic_request_sla"
    "generic_request_sla_log"
    "generic_team"
    "website_service_desk"
    "bureaucrat_servicedesk_ultimate"
)

# ------------------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------------------
GREEN='\033[0;32m'; ORANGE='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅  $1${NC}"; }
warn() { echo -e "${ORANGE}[$(date '+%H:%M:%S')] ⚠️   $1${NC}"; }
die()  { echo -e "${RED}[$(date '+%H:%M:%S')] ❌  $1${NC}"; exit 1; }
step() { echo -e "\n${ORANGE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; \
         echo -e "${ORANGE}  STEP $1${NC}"; \
         echo -e "${ORANGE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

[[ $EUID -ne 0 ]] && die "Run as root: sudo bash install.sh"

# ------------------------------------------------------------------------------
# STEP 1 — System packages
# ------------------------------------------------------------------------------
step "1/14 — System packages"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-dev python3-venv \
    postgresql postgresql-client \
    libxml2-dev libxslt1-dev libevent-dev libsasl2-dev libldap2-dev \
    libpq-dev libjpeg-dev libfreetype6-dev zlib1g-dev \
    build-essential git curl wget gnupg2 ca-certificates \
    fonts-liberation fonts-noto-cjk \
    node-less npm nginx certbot python3-certbot-nginx
log "System packages installed"

# ------------------------------------------------------------------------------
# STEP 2 — PostgreSQL
# ------------------------------------------------------------------------------
step "2/14 — PostgreSQL"
systemctl enable --now postgresql

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
    sudo -u postgres createuser --createdb --no-superuser --no-createrole "${DB_USER}"
sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"

mkdir -p /etc/odoo
echo "${DB_PASS}" > /etc/odoo/.dbpass
chmod 600 /etc/odoo/.dbpass
log "PostgreSQL configured. DB password saved to /etc/odoo/.dbpass"

# ------------------------------------------------------------------------------
# STEP 3 — Odoo system user & directories
# ------------------------------------------------------------------------------
step "3/14 — Odoo user & directories"
id -u "${ODOO_USER}" &>/dev/null || useradd -m -d "${ODOO_HOME}" -s /bin/bash "${ODOO_USER}"
mkdir -p "${ODOO_HOME}" /var/log/odoo /etc/odoo
chown -R "${ODOO_USER}:${ODOO_USER}" "${ODOO_HOME}" /var/log/odoo
log "Odoo user and directories ready"

# ------------------------------------------------------------------------------
# STEP 4 — Odoo 15 source (CRND fork with Bureaucrat ITSM)
# ------------------------------------------------------------------------------
step "4/14 — Odoo 15 source"
if [ ! -d "${ODOO_HOME}/odoo" ]; then
    sudo -u "${ODOO_USER}" git clone \
        --depth=1 --branch=15.0 \
        https://github.com/odoo/odoo.git \
        "${ODOO_HOME}/odoo"
    log "Odoo 15 source cloned"
else
    warn "Odoo source already exists — skipping clone"
fi

# CRND / Bureaucrat ITSM addons
if [ ! -d "${ODOO_HOME}/bureaucrat" ]; then
    sudo -u "${ODOO_USER}" git clone \
        --depth=1 --branch=15.0 \
        https://github.com/crnd-inc/generic-addons.git \
        "${ODOO_HOME}/bureaucrat"
    log "Bureaucrat ITSM addons cloned"
else
    warn "Bureaucrat addons already exist — skipping clone"
fi

# myservicenrs repo (this repo)
if [ ! -d "${ODOO_HOME}/myservicenrs" ]; then
    sudo -u "${ODOO_USER}" git clone \
        https://github.com/sojiabolarin/myservicenrs.git \
        "${ODOO_HOME}/myservicenrs"
    log "myservicenrs repo cloned"
else
    warn "myservicenrs repo already exists — skipping clone"
    sudo -u "${ODOO_USER}" git -C "${ODOO_HOME}/myservicenrs" pull
fi

# ------------------------------------------------------------------------------
# STEP 5 — Python virtualenv
# ------------------------------------------------------------------------------
step "5/14 — Python virtualenv"
if [ ! -d "${ODOO_VENV}" ]; then
    sudo -u "${ODOO_USER}" python3 -m venv "${ODOO_VENV}"
fi
sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/pip" install --upgrade pip wheel -q
sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/pip" install -r "${ODOO_HOME}/odoo/requirements.txt" -q
# gevent pin for Python 3.10 compatibility
sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/pip" install "gevent==22.10.2" "greenlet==2.0.2" -q
log "Python virtualenv ready"

# ------------------------------------------------------------------------------
# STEP 6 — wkhtmltopdf
# ------------------------------------------------------------------------------
step "6/14 — wkhtmltopdf"
if ! command -v wkhtmltopdf &>/dev/null; then
    wget -q https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb \
        -O /tmp/wkhtmltox.deb
    apt-get install -y /tmp/wkhtmltox.deb
    rm /tmp/wkhtmltox.deb
    log "wkhtmltopdf installed"
else
    warn "wkhtmltopdf already installed"
fi

# ------------------------------------------------------------------------------
# STEP 7 — odoo.conf
# ------------------------------------------------------------------------------
step "7/14 — odoo.conf"
cat > "${ODOO_CONF}" << EOF
[options]
addons_path = ${ODOO_HOME}/odoo/addons,${ODOO_HOME}/bureaucrat,${ODOO_HOME}/myservicenrs/addons
admin_passwd = ${ADMIN_PASS}
db_host = localhost
db_port = 5432
db_user = ${DB_USER}
db_password = ${DB_PASS}
db_name = ${DB_NAME}
http_port = 8069
longpolling_port = 8072
logfile = ${ODOO_LOG}
log_level = info
workers = 2
max_cron_threads = 1
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 600
limit_time_real = 1200
proxy_mode = True
without_demo = True
EOF
chown "${ODOO_USER}:${ODOO_USER}" "${ODOO_CONF}"
chmod 640 "${ODOO_CONF}"

# Save admin password
echo "${ADMIN_PASS}" > /etc/odoo/.masterpass
chmod 600 /etc/odoo/.masterpass
log "odoo.conf written. Master password saved to /etc/odoo/.masterpass"

# ------------------------------------------------------------------------------
# STEP 8 — Systemd service
# ------------------------------------------------------------------------------
step "8/14 — Systemd service"
cat > /etc/systemd/system/odoo.service << EOF
[Unit]
Description=Odoo 15 — NRS myservice
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=${ODOO_USER}
Group=${ODOO_USER}
ExecStart=${ODOO_VENV}/bin/python ${ODOO_HOME}/odoo/odoo-bin -c ${ODOO_CONF}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=odoo

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable odoo
log "Systemd service configured"

# ------------------------------------------------------------------------------
# STEP 9 — Nginx
# ------------------------------------------------------------------------------
step "9/14 — Nginx"
cat > /etc/nginx/sites-available/myservice << EOF
upstream odoo {
    server 127.0.0.1:8069;
}
upstream odoochat {
    server 127.0.0.1:8072;
}

server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    # Redirect www to bare domain
    if (\$host = www.${DOMAIN}) {
        return 301 http://${DOMAIN}\$request_uri;
    }

    access_log /var/log/nginx/myservice.access.log;
    error_log  /var/log/nginx/myservice.error.log;

    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;

    # Longpolling
    location /longpolling {
        proxy_pass http://odoochat;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-For  \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location / {
        proxy_pass http://odoo;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-For  \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_redirect off;
    }

    # Static files cache
    location ~* /web/static/ {
        proxy_cache_valid 200 90m;
        proxy_buffering on;
        expires 864000;
        proxy_pass http://odoo;
    }

    gzip on;
    gzip_min_length 1100;
    gzip_buffers 4 32k;
    gzip_types text/plain text/xml text/css application/javascript;
    gzip_vary on;
}
EOF

ln -sf /etc/nginx/sites-available/myservice /etc/nginx/sites-enabled/myservice
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl enable --now nginx
log "Nginx configured for ${DOMAIN}"

# ------------------------------------------------------------------------------
# STEP 10 — Database creation & Odoo init
# ------------------------------------------------------------------------------
step "10/14 — Database creation"
systemctl start odoo
sleep 8   # allow Odoo to start

sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/python" "${ODOO_HOME}/odoo/odoo-bin" \
    -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    --init base,web,mail \
    --without-demo=all \
    --stop-after-init \
    --logfile /dev/null
log "Database ${DB_NAME} initialised"

# ------------------------------------------------------------------------------
# STEP 11 — Install Bureaucrat ITSM modules
# ------------------------------------------------------------------------------
step "11/14 — Bureaucrat ITSM modules"
MODULE_LIST=$(IFS=,; echo "${ITSM_MODULES[*]}")
sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/python" "${ODOO_HOME}/odoo/odoo-bin" \
    -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    --init "${MODULE_LIST}" \
    --without-demo=all \
    --stop-after-init \
    --logfile /dev/null
log "Bureaucrat ITSM modules installed"

# ------------------------------------------------------------------------------
# STEP 12 — ITSM structure seed
# ------------------------------------------------------------------------------
step "12/14 — ITSM structure seed"
sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/python" "${ODOO_HOME}/odoo/odoo-bin" shell \
    -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    --no-http << 'PYEOF'
exec(open('/opt/odoo/myservicenrs/itsm_structure.py').read())
PYEOF
log "ITSM structure loaded"

# ------------------------------------------------------------------------------
# STEP 13 — Location skeleton
# ------------------------------------------------------------------------------
step "13/14 — Location skeleton"
sudo -u "${ODOO_USER}" "${ODOO_VENV}/bin/python" "${ODOO_HOME}/odoo/odoo-bin" shell \
    -c "${ODOO_CONF}" \
    -d "${DB_NAME}" \
    --no-http << 'PYEOF'
exec(open('/opt/odoo/myservicenrs/load_locations.py').read())
PYEOF
log "Location skeleton loaded"

# ------------------------------------------------------------------------------
# STEP 14 — Portal homepage
# ------------------------------------------------------------------------------
step "14/14 — Portal homepage"
# Copy web assets to Odoo's static directory so they're served directly by Nginx
STATIC_DIR="${ODOO_HOME}/myservicenrs"
if [ -f "${STATIC_DIR}/index.html" ]; then
    cp "${STATIC_DIR}/index.html" /var/www/html/index.html
    log "Portal homepage deployed to /var/www/html/index.html"
fi

# Nginx: serve / from static, proxy /web /odoo /api to Odoo
cat >> /etc/nginx/sites-available/myservice << 'EOF'

# Serve static portal homepage
location = / {
    root /var/www/html;
    index index.html;
    try_files $uri $uri/ @odoo;
}
location @odoo {
    proxy_pass http://odoo;
}
EOF
nginx -t && systemctl reload nginx
log "Portal homepage live at http://${DOMAIN}"

# ------------------------------------------------------------------------------
# DONE
# ------------------------------------------------------------------------------
systemctl restart odoo

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  NRS myservice install complete                      ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  URL         : http://${DOMAIN}                 ║${NC}"
echo -e "${GREEN}║  DB name     : ${DB_NAME}                             ║${NC}"
echo -e "${GREEN}║  Master pass : $(cat /etc/odoo/.masterpass)   ║${NC}"
echo -e "${GREEN}║  DB password : see /etc/odoo/.dbpass                 ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Next steps:                                         ║${NC}"
echo -e "${GREEN}║  1. Add SSL:                                         ║${NC}"
echo -e "${GREEN}║     certbot --nginx -d ${DOMAIN}            ║${NC}"
echo -e "${GREEN}║  2. Load office sites:                               ║${NC}"
echo -e "${GREEN}║     OFFICES_CSV=/path/to/offices.csv \\               ║${NC}"
echo -e "${GREEN}║     bash /opt/odoo/myservicenrs/load_all.sh                         ║${NC}"
echo -e "${GREEN}║  3. Log in at http://${DOMAIN}/web            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
