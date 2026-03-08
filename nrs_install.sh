#!/bin/bash
################################################################################
# Odoo 15 Installation Script — NRS Facilities Service Desk
# Powered by WestMetro Limited (WML)
#
# Client:    Nigeria Revenue Service — Facilities Management
# Platform:  Bureaucrat ITSM / CRND on Odoo 15
# Domains:   Building Services | Plumbing | Plant & Machinery
#            Security & Safety | Fleet Management
#
# Usage:
#   git clone https://github.com/sojiabolarin/CRND
#   cd CRND
#   sudo ./nrs_install.sh [--db-name <name>] [--domain <domain>]
#
# WestMetro Limited
# Phone: +234 806 902 0996
# Email: info@westmetrong.com
# Website: www.westmetrong.com
################################################################################

set -e

# ─────────────────────────────────────────────
# Configuration — override via flags or edit here
# ─────────────────────────────────────────────
ODOO_VERSION="15.0"
WORKERS=2
INSTALL_MODE="git"
DB_NAME="nrs-facilities"
DOMAIN=""
ADMIN_PASSWD="NRS@Facilities2025!"    # Change in production

REPO_URL="https://github.com/sojiabolarin/CRND"
CRND_DEPLOY_URL="https://github.com/crnd-inc/crnd-deploy.git"
SEED_SCRIPT="/opt/odoo/nrs_seed.py"

# ─────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─────────────────────────────────────────────
# Parse arguments
# ─────────────────────────────────────────────
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --db-name)   DB_NAME="$2";   shift ;;
        --domain)    DOMAIN="$2";    shift ;;
        --workers)   WORKERS="$2";   shift ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
    shift
done

# ─────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────
echo -e "${GREEN}"
echo "================================================================================"
echo "   NRS Facilities Service Desk — Odoo ${ODOO_VERSION} Installation"
echo "   Client:   Nigeria Revenue Service"
echo "   Modules:  Building | Plumbing | Plant & Machinery | Security | Fleet"
echo "   Powered by WestMetro Limited"
echo "================================================================================"
echo -e "${NC}"

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}This script must be run as root (sudo ./nrs_install.sh)${NC}"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID; VERSION=$VERSION_ID
else
    echo -e "${RED}Cannot detect OS. Ubuntu 20.04/22.04/24.04 required.${NC}"; exit 1
fi
echo -e "${BLUE}OS:${NC} $OS $VERSION | ${BLUE}DB:${NC} $DB_NAME | ${BLUE}Workers:${NC} $WORKERS"

# ─────────────────────────────────────────────
# Step 1 — System dependencies
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[1/8]${NC} Installing system dependencies..."
apt-get update -qq
apt-get install -y git wget curl sudo python3-pip

# ─────────────────────────────────────────────
# Step 2 — CRND Deploy
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[2/8]${NC} Downloading CRND Deploy..."
cd /tmp
rm -rf crnd-deploy-official
git clone ${CRND_DEPLOY_URL} crnd-deploy-official

if [ ! -f "/tmp/crnd-deploy-official/crnd-deploy.bash" ]; then
    echo -e "${RED}ERROR: crnd-deploy.bash not found!${NC}"; exit 1
fi

# ─────────────────────────────────────────────
# Step 3 — Install Odoo 15
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[3/8]${NC} Installing Odoo ${ODOO_VERSION} with CRND Deploy..."
echo -e "${YELLOW}This installs Odoo, PostgreSQL, Nginx, and odoo-helper-scripts${NC}"

bash /tmp/crnd-deploy-official/crnd-deploy.bash \
    --odoo-version ${ODOO_VERSION} \
    --install-mode ${INSTALL_MODE} \
    --local-postgres \
    --local-nginx \
    --proxy-mode \
    --workers ${WORKERS}

# ─────────────────────────────────────────────
# Step 4 — Start services
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[4/8]${NC} Starting services..."
service postgresql start
service odoo start

# ─────────────────────────────────────────────
# Step 5 — Nginx
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[5/8]${NC} Configuring Nginx..."
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
HOSTNAME_SHORT=$(hostname -s)

if [ -n "$DOMAIN" ]; then
    NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}.conf"
    if [ ! -f "$NGINX_CONF" ]; then
        cat > "$NGINX_CONF" <<NGINXEOF
upstream odoo_nrs {
    server 127.0.0.1:8069;
}
server {
    listen 80;
    server_name ${DOMAIN};
    access_log /var/log/nginx/nrs-odoo.access.log;
    error_log  /var/log/nginx/nrs-odoo.error.log;

    location / {
        proxy_pass http://odoo_nrs;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 200M;
        proxy_read_timeout 720s;
    }
    location /longpolling {
        proxy_pass http://127.0.0.1:8072;
    }
    gzip on;
    gzip_types text/css text/javascript application/json;
}
NGINXEOF
    fi
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
    service nginx restart
    echo -e "${GREEN}Nginx configured for domain: ${DOMAIN}${NC}"
elif [ -f "/etc/nginx/sites-available/${HOSTNAME_SHORT}.conf" ]; then
    ln -sf "/etc/nginx/sites-available/${HOSTNAME_SHORT}.conf" /etc/nginx/sites-enabled/
    service nginx restart
    echo -e "${GREEN}Nginx configured: ${HOSTNAME_SHORT}.conf${NC}"
else
    echo -e "${YELLOW}Nginx config not found — configure manually${NC}"
fi

# ─────────────────────────────────────────────
# Step 6 — Fetch custom CRND modules
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[6/8]${NC} Fetching custom modules from ${REPO_URL}..."

mkdir -p /opt/odoo/repositories
chown odoo:odoo /opt/odoo/repositories

sudo -u odoo odoo-helper fetch --repo ${REPO_URL} || true
sleep 2

# Locate dist folder
DIST_PATH=""
for CANDIDATE in \
    "/opt/odoo/repositories/sojiabolarin/CRND/dist" \
    "/opt/odoo/repositories/CRND/dist"; do
    if [ -d "$CANDIDATE" ]; then
        DIST_PATH="$CANDIDATE"; break
    fi
done

if [ -z "$DIST_PATH" ]; then
    DIST_PATH=$(find /opt/odoo/repositories -type d -name "dist" 2>/dev/null | head -1)
fi

if [ -z "$DIST_PATH" ] || [ ! -d "$DIST_PATH" ]; then
    echo -e "${YELLOW}Cloning repository directly...${NC}"
    cd /opt/odoo/repositories
    rm -rf CRND
    sudo -u odoo git clone ${REPO_URL} CRND
    DIST_PATH="/opt/odoo/repositories/CRND/dist"
fi

# Symlink modules to custom_addons
mkdir -p /opt/odoo/custom_addons
chown odoo:odoo /opt/odoo/custom_addons

MODULE_COUNT=0
if [ -d "$DIST_PATH" ]; then
    for module_dir in ${DIST_PATH}/*/; do
        if [ -d "$module_dir" ]; then
            module_name=$(basename "${module_dir%/}")
            rm -f /opt/odoo/custom_addons/${module_name}
            sudo -u odoo ln -sf "${module_dir%/}" /opt/odoo/custom_addons/${module_name}
            echo -e "  ${GREEN}✓${NC} Linked: ${module_name}"
            MODULE_COUNT=$((MODULE_COUNT + 1))
        fi
    done
    echo -e "${GREEN}Linked ${MODULE_COUNT} modules${NC}"
else
    echo -e "${RED}ERROR: dist folder not found at ${DIST_PATH}${NC}"
fi

# ─────────────────────────────────────────────
# Step 7 — Create NRS database and seed data
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[7/8]${NC} Deploying NRS seed data..."

# Write the seed script to disk (sourced inline below)
cp "$(dirname "$0")/nrs_seed.py" ${SEED_SCRIPT} 2>/dev/null || true

# Restart Odoo before seeding
service odoo restart
sleep 5
sudo -u odoo odoo-helper addons update-list || true

if [ -f "${SEED_SCRIPT}" ]; then
    echo -e "${CYAN}Running NRS seed script on database: ${DB_NAME}${NC}"
    cd /opt/odoo
    sudo -u odoo python3 /opt/odoo/odoo/odoo-bin shell \
        -c /opt/odoo/conf/odoo.conf \
        -d ${DB_NAME} \
        --no-http < ${SEED_SCRIPT} && \
    echo -e "${GREEN}Seed completed successfully${NC}" || \
    echo -e "${YELLOW}Seed script run — check output above for errors${NC}"
else
    echo -e "${YELLOW}nrs_seed.py not found alongside install script.${NC}"
    echo -e "${YELLOW}Run manually after DB creation:${NC}"
    echo -e "  sudo -u odoo python3 /opt/odoo/odoo/odoo-bin shell \\"
    echo -e "    -c /opt/odoo/conf/odoo.conf -d ${DB_NAME} --no-http < nrs_seed.py"
fi

# ─────────────────────────────────────────────
# Step 8 — Finalise
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[8/8]${NC} Finalising..."
service odoo restart

SERVER_IP=$(hostname -I | awk '{print $1}')

echo -e "\n${GREEN}"
echo "================================================================================"
echo "        NRS Facilities Service Desk — Installation Complete!"
echo "================================================================================"
echo -e "${NC}"
echo -e "${YELLOW}Access URLs:${NC}"
echo "  Direct:   http://${SERVER_IP}:8069"
[ -n "$DOMAIN" ] && echo "  Domain:   http://${DOMAIN}"
echo ""
echo -e "${YELLOW}Database:${NC} ${DB_NAME}"
echo -e "${YELLOW}Master password:${NC} ${ADMIN_PASSWD}"
echo -e "${RED}  ⚠ Change master password before go-live!${NC}"
echo "  Edit: /opt/odoo/conf/odoo.conf → admin_passwd"
echo ""
echo -e "${YELLOW}Custom modules:${NC} /opt/odoo/custom_addons (${MODULE_COUNT} modules)"
echo -e "${YELLOW}Module source:${NC}  ${DIST_PATH}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Open http://${SERVER_IP}:8069 → Create database '${DB_NAME}'"
echo "  2. Settings → Activate Developer Mode"
echo "  3. Apps → Update Apps List → Install 'Bureaucrat ITSM' modules"
echo "  4. Run nrs_seed.py in Odoo shell (if not auto-run above)"
echo "  5. Settings → General → Company → set NRS branding"
echo ""
echo -e "${YELLOW}odoo-helper Commands:${NC}"
echo "  cd /opt/odoo"
echo "  sudo -u odoo odoo-helper server status|restart|log"
echo "  sudo -u odoo odoo-helper db list"
echo "  sudo -u odoo odoo-helper addons install -d ${DB_NAME} <module>"
echo ""
echo -e "${GREEN}Powered by WestMetro Limited | www.westmetrong.com${NC}"
echo ""
