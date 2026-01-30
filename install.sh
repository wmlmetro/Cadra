#!/bin/bash
################################################################################
# Odoo 15 Installation Script (Virtual Environment)
# Repository: https://github.com/sojiabolarin/CRND
# 
# This script installs Odoo 15 in a Python virtual environment
# with custom modules from this repository.
#
# Usage:
#   git clone https://github.com/sojiabolarin/CRND
#   cd CRND
#   sudo ./install.sh
#
# WestMetro Limited
# Phone: +234 806 902 0996
# Email: info@westmetrong.com
# Website: www.westmetrong.com
################################################################################

set -e

# Configuration - Modify these as needed
ODOO_VERSION="15.0"
ODOO_USER="odoo"
ODOO_HOME="/opt/odoo"
ODOO_HOME_EXT="${ODOO_HOME}/odoo-server"
ODOO_CONFIG="${ODOO_USER}"
ODOO_PORT="8069"
ODOO_LONGPOLLING_PORT="8072"
ADMIN_PASSWORD="admin"  # Change this!
WORKERS=2
INSTALL_NGINX=true
INSTALL_WKHTMLTOPDF=true

# Repository info
REPO_URL="https://github.com/sojiabolarin/CRND"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}"
echo "================================================================================"
echo "   Odoo ${ODOO_VERSION} Installation (Virtual Environment)"
echo "   Repository: ${REPO_URL}"
echo "   WestMetro Limited"
echo "================================================================================"
echo -e "${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}" 
   exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VERSION=$VERSION_ID
else
    echo -e "${RED}Cannot detect OS. This script supports Ubuntu 20.04/22.04/24.04${NC}"
    exit 1
fi

echo -e "${BLUE}Detected OS:${NC} $OS $VERSION"

#--------------------------------------------------
# Step 1: Update and Install Dependencies
#--------------------------------------------------
echo -e "\n${BLUE}[Step 1/10]${NC} Updating system and installing dependencies..."

apt-get update && apt-get upgrade -y

apt-get install -y \
    git \
    wget \
    curl \
    zip \
    unzip \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    python3-wheel \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libevent-dev \
    libsasl2-dev \
    libldap2-dev \
    libpq-dev \
    libpng-dev \
    libjpeg-dev \
    libfreetype6-dev \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    liblcms2-dev \
    libblas-dev \
    libatlas-base-dev \
    node-less \
    npm \
    xfonts-75dpi \
    xfonts-base \
    fontconfig \
    libxrender1 \
    gdebi-core

# Install Node.js packages
npm install -g rtlcss less less-plugin-clean-css

#--------------------------------------------------
# Step 2: Install PostgreSQL
#--------------------------------------------------
echo -e "\n${BLUE}[Step 2/10]${NC} Installing PostgreSQL..."

# Add PostgreSQL repo for version 14
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list

apt-get update
apt-get install -y postgresql-14

# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

#--------------------------------------------------
# Step 3: Create Odoo System User
#--------------------------------------------------
echo -e "\n${BLUE}[Step 3/10]${NC} Creating Odoo system user..."

if id "$ODOO_USER" &>/dev/null; then
    echo "User ${ODOO_USER} already exists"
else
    useradd -m -d ${ODOO_HOME} -U -r -s /bin/bash ${ODOO_USER}
    echo "Created user ${ODOO_USER}"
fi

#--------------------------------------------------
# Step 4: Create PostgreSQL User
#--------------------------------------------------
echo -e "\n${BLUE}[Step 4/10]${NC} Creating PostgreSQL user..."

sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='${ODOO_USER}'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE USER ${ODOO_USER} WITH SUPERUSER CREATEDB CREATEROLE PASSWORD '${ADMIN_PASSWORD}';"

echo "PostgreSQL user ${ODOO_USER} ready"

#--------------------------------------------------
# Step 5: Install Wkhtmltopdf
#--------------------------------------------------
if [ "$INSTALL_WKHTMLTOPDF" = true ]; then
    echo -e "\n${BLUE}[Step 5/10]${NC} Installing Wkhtmltopdf..."
    
    ARCH=$(dpkg --print-architecture)
    cd /tmp
    
    if [ "$ARCH" = "amd64" ]; then
        wget -q https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb -O wkhtmltox.deb
    else
        wget -q https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_arm64.deb -O wkhtmltox.deb
    fi
    
    apt-get install -y ./wkhtmltox.deb || apt-get install -y wkhtmltopdf
    
    ln -sf /usr/local/bin/wkhtmltopdf /usr/bin/wkhtmltopdf 2>/dev/null || true
    ln -sf /usr/local/bin/wkhtmltoimage /usr/bin/wkhtmltoimage 2>/dev/null || true
    
    rm -f /tmp/wkhtmltox.deb
else
    echo -e "\n${BLUE}[Step 5/10]${NC} Skipping Wkhtmltopdf installation"
fi

#--------------------------------------------------
# Step 6: Clone Odoo Source
#--------------------------------------------------
echo -e "\n${BLUE}[Step 6/10]${NC} Cloning Odoo ${ODOO_VERSION} source code..."

mkdir -p ${ODOO_HOME}
chown -R ${ODOO_USER}:${ODOO_USER} ${ODOO_HOME}

sudo -u ${ODOO_USER} git clone --depth 1 --branch ${ODOO_VERSION} \
    https://github.com/odoo/odoo.git ${ODOO_HOME_EXT}

#--------------------------------------------------
# Step 7: Create Virtual Environment and Install Dependencies
#--------------------------------------------------
echo -e "\n${BLUE}[Step 7/10]${NC} Creating Python virtual environment..."

sudo -u ${ODOO_USER} python3 -m venv ${ODOO_HOME}/venv

echo -e "${BLUE}Installing Python dependencies in virtual environment...${NC}"

sudo -u ${ODOO_USER} bash << EOF
source ${ODOO_HOME}/venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r ${ODOO_HOME_EXT}/requirements.txt
pip install phonenumbers psycopg2-binary watchdog python-ldap num2words xlwt
deactivate
EOF

echo -e "${GREEN}Virtual environment created at ${ODOO_HOME}/venv${NC}"

#--------------------------------------------------
# Step 8: Setup Custom Addons Directory and Clone CRND
#--------------------------------------------------
echo -e "\n${BLUE}[Step 8/10]${NC} Setting up custom addons..."

# Create directories
mkdir -p ${ODOO_HOME}/custom_addons
mkdir -p /var/log/${ODOO_USER}

# Set permissions BEFORE cloning
chown -R ${ODOO_USER}:${ODOO_USER} ${ODOO_HOME}
chown -R ${ODOO_USER}:${ODOO_USER} /var/log/${ODOO_USER}

# Clone CRND repository as odoo user
sudo -u ${ODOO_USER} git clone ${REPO_URL} ${ODOO_HOME}/custom_addons/crnd

#--------------------------------------------------
# Step 9: Create Odoo Configuration File
#--------------------------------------------------
echo -e "\n${BLUE}[Step 9/10]${NC} Creating Odoo configuration..."

cat > /etc/${ODOO_CONFIG}.conf << EOF
[options]
; Admin and Database
admin_passwd = ${ADMIN_PASSWORD}
db_host = False
db_port = False
db_user = ${ODOO_USER}
db_password = False
;db_filter = ^%d\$

; Paths
addons_path = ${ODOO_HOME_EXT}/addons,${ODOO_HOME}/custom_addons,${ODOO_HOME}/custom_addons/crnd
data_dir = ${ODOO_HOME}/.local/share/Odoo

; Logging
logfile = /var/log/${ODOO_USER}/${ODOO_CONFIG}.log
log_level = info
logrotate = True

; Network
http_port = ${ODOO_PORT}
longpolling_port = ${ODOO_LONGPOLLING_PORT}
proxy_mode = True
xmlrpc_interface = 127.0.0.1
netrpc_interface = 127.0.0.1

; Performance
workers = ${WORKERS}
max_cron_threads = 1
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 600
limit_time_real = 1200
EOF

chown ${ODOO_USER}:${ODOO_USER} /etc/${ODOO_CONFIG}.conf
chmod 640 /etc/${ODOO_CONFIG}.conf

echo -e "${GREEN}Configuration saved to /etc/${ODOO_CONFIG}.conf${NC}"

#--------------------------------------------------
# Step 10: Create Systemd Service
#--------------------------------------------------
echo -e "\n${BLUE}[Step 10/10]${NC} Creating systemd service..."

cat > /etc/systemd/system/${ODOO_CONFIG}.service << EOF
[Unit]
Description=Odoo ${ODOO_VERSION}
Documentation=https://www.odoo.com
After=network.target postgresql.service

[Service]
Type=simple
SyslogIdentifier=${ODOO_CONFIG}
PermissionsStartOnly=true
User=${ODOO_USER}
Group=${ODOO_USER}
ExecStart=${ODOO_HOME}/venv/bin/python ${ODOO_HOME_EXT}/odoo-bin -c /etc/${ODOO_CONFIG}.conf
WorkingDirectory=${ODOO_HOME_EXT}
StandardOutput=journal+console
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable ${ODOO_CONFIG}
systemctl start ${ODOO_CONFIG}

#--------------------------------------------------
# Install Nginx (Optional)
#--------------------------------------------------
if [ "$INSTALL_NGINX" = true ]; then
    echo -e "\n${BLUE}[Bonus]${NC} Installing and configuring Nginx..."
    
    apt-get install -y nginx
    
    cat > /etc/nginx/sites-available/odoo << 'NGINX_EOF'
upstream odoo {
    server 127.0.0.1:8069;
}

upstream odoochat {
    server 127.0.0.1:8072;
}

server {
    listen 80;
    server_name _;

    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;
    proxy_buffers 16 64k;
    proxy_buffer_size 128k;

    # Logs
    access_log /var/log/nginx/odoo.access.log;
    error_log /var/log/nginx/odoo.error.log;

    # Redirect longpoll requests to odoo longpolling port
    location /longpolling {
        proxy_pass http://odoochat;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Redirect requests to odoo backend server
    location / {
        proxy_pass http://odoo;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Cache static files
    location ~* /web/static/ {
        proxy_cache_valid 200 90m;
        proxy_buffering on;
        expires 864000;
        proxy_pass http://odoo;
    }

    # Gzip compression
    gzip on;
    gzip_min_length 1000;
    gzip_types text/css text/plain text/xml application/xml application/javascript application/json;
}
NGINX_EOF

    # Enable site
    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/odoo /etc/nginx/sites-enabled/odoo
    
    # Test and restart nginx
    nginx -t && systemctl restart nginx
    systemctl enable nginx
    
    echo -e "${GREEN}Nginx configured successfully${NC}"
fi

#--------------------------------------------------
# Configure Firewall
#--------------------------------------------------
echo -e "\n${BLUE}[Firewall]${NC} Configuring firewall rules..."

if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow ${ODOO_PORT}/tcp
    echo "Firewall rules added"
fi

#--------------------------------------------------
# Print Summary
#--------------------------------------------------
SERVER_IP=$(hostname -I | awk '{print $1}')

echo -e "\n${GREEN}"
echo "================================================================================"
echo "                    Installation Complete!"
echo "================================================================================"
echo -e "${NC}"
echo ""
echo "Odoo ${ODOO_VERSION} installed in virtual environment!"
echo ""
echo -e "${YELLOW}Installation Details:${NC}"
echo "  - Odoo User:          ${ODOO_USER}"
echo "  - Odoo Home:          ${ODOO_HOME}"
echo "  - Odoo Server:        ${ODOO_HOME_EXT}"
echo "  - Virtual Env:        ${ODOO_HOME}/venv"
echo "  - Custom Addons:      ${ODOO_HOME}/custom_addons"
echo "  - CRND Modules:       ${ODOO_HOME}/custom_addons/crnd"
echo "  - Config File:        /etc/${ODOO_CONFIG}.conf"
echo "  - Log File:           /var/log/${ODOO_USER}/${ODOO_CONFIG}.log"
echo "  - Service Name:       ${ODOO_CONFIG}"
echo ""
echo -e "${YELLOW}Access Odoo:${NC}"
echo "  - Direct:  http://${SERVER_IP}:${ODOO_PORT}"
if [ "$INSTALL_NGINX" = true ]; then
echo "  - Nginx:   http://${SERVER_IP}"
fi
echo ""
echo -e "${YELLOW}Default Credentials:${NC}"
echo "  - Master Password: ${ADMIN_PASSWORD}"
echo "  - (Change this in /etc/${ODOO_CONFIG}.conf)"
echo ""
echo -e "${YELLOW}Service Commands:${NC}"
echo "  sudo systemctl start ${ODOO_CONFIG}"
echo "  sudo systemctl stop ${ODOO_CONFIG}"
echo "  sudo systemctl restart ${ODOO_CONFIG}"
echo "  sudo systemctl status ${ODOO_CONFIG}"
echo ""
echo -e "${YELLOW}View Logs:${NC}"
echo "  sudo tail -f /var/log/${ODOO_USER}/${ODOO_CONFIG}.log"
echo "  sudo journalctl -u ${ODOO_CONFIG} -f"
echo ""
echo -e "${YELLOW}Activate Virtual Environment:${NC}"
echo "  source ${ODOO_HOME}/venv/bin/activate"
echo ""
echo -e "${YELLOW}Run Odoo Manually (for debugging):${NC}"
echo "  sudo -u ${ODOO_USER} ${ODOO_HOME}/venv/bin/python ${ODOO_HOME_EXT}/odoo-bin -c /etc/${ODOO_CONFIG}.conf"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Open http://${SERVER_IP}:${ODOO_PORT} in your browser"
echo "  2. Create your first database"
echo "  3. Go to Apps → Update Apps List"
echo "  4. Search and install your custom modules"
echo ""
echo -e "${GREEN}Thank you for using WestMetro Limited solutions!${NC}"
echo ""
