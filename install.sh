#!/bin/bash
################################################################################
# Odoo 15 Complete Installation Script
# Repository: https://github.com/sojiabolarin/CRND
# 
# This script:
# 1. Installs Odoo 15 using official CRND Deploy (with odoo-helper-scripts)
# 2. Fetches and links custom modules from this repository's dist folder
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
WORKERS=2
INSTALL_MODE="git"

# Repository info
REPO_URL="https://github.com/sojiabolarin/CRND"
CRND_DEPLOY_URL="https://github.com/crnd-inc/crnd-deploy.git"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}"
echo "================================================================================"
echo "   Odoo ${ODOO_VERSION} Complete Installation"
echo "   Custom Modules: ${REPO_URL}"
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
# Step 1: Install Basic Dependencies
#--------------------------------------------------
echo -e "\n${BLUE}[Step 1/6]${NC} Installing basic dependencies..."

apt-get update
apt-get install -y git wget curl sudo

#--------------------------------------------------
# Step 2: Clone Official CRND Deploy
#--------------------------------------------------
echo -e "\n${BLUE}[Step 2/6]${NC} Downloading CRND Deploy installer..."

cd /tmp
rm -rf crnd-deploy-official
git clone ${CRND_DEPLOY_URL} crnd-deploy-official

# Verify the script exists
if [ ! -f "/tmp/crnd-deploy-official/crnd-deploy.bash" ]; then
    echo -e "${RED}ERROR: crnd-deploy.bash not found!${NC}"
    exit 1
fi

#--------------------------------------------------
# Step 3: Run CRND Deploy to Install Odoo
#--------------------------------------------------
echo -e "\n${BLUE}[Step 3/6]${NC} Installing Odoo ${ODOO_VERSION} with CRND Deploy..."
echo -e "${YELLOW}This will install Odoo, PostgreSQL, Nginx, and odoo-helper-scripts${NC}"

bash /tmp/crnd-deploy-official/crnd-deploy.bash \
    --odoo-version ${ODOO_VERSION} \
    --install-mode ${INSTALL_MODE} \
    --local-postgres \
    --local-nginx \
    --proxy-mode \
    --workers ${WORKERS}

#--------------------------------------------------
# Step 4: Start Services
#--------------------------------------------------
echo -e "\n${BLUE}[Step 4/6]${NC} Starting services..."

service postgresql start
service odoo start

#--------------------------------------------------
# Step 5: Configure Nginx
#--------------------------------------------------
echo -e "\n${BLUE}[Step 5/6]${NC} Configuring Nginx..."

cd /etc/nginx/sites-enabled
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

HOSTNAME_SHORT=$(hostname -s)
if [ -f "/etc/nginx/sites-available/${HOSTNAME_SHORT}.conf" ]; then
    ln -sf "/etc/nginx/sites-available/${HOSTNAME_SHORT}.conf" ./
    service nginx restart
    echo -e "${GREEN}Nginx configured with ${HOSTNAME_SHORT}.conf${NC}"
else
    echo -e "${YELLOW}Nginx config not found at expected path - may need manual configuration${NC}"
fi

#--------------------------------------------------
# Step 6: Fetch and Link Custom Modules
#--------------------------------------------------
echo -e "\n${BLUE}[Step 6/6]${NC} Adding custom modules from repository..."

cd /opt/odoo

# Fetch the custom CRND repository
sudo -u odoo odoo-helper fetch ${REPO_URL}

# Find and link the dist folder
if [ -d "/opt/odoo/repositories/sojiabolarin/CRND/dist" ]; then
    sudo -u odoo odoo-helper link /opt/odoo/repositories/sojiabolarin/CRND/dist
    echo -e "${GREEN}Linked modules from /opt/odoo/repositories/sojiabolarin/CRND/dist${NC}"
elif [ -d "/opt/odoo/repositories/CRND/dist" ]; then
    sudo -u odoo odoo-helper link /opt/odoo/repositories/CRND/dist
    echo -e "${GREEN}Linked modules from /opt/odoo/repositories/CRND/dist${NC}"
else
    echo -e "${YELLOW}Warning: dist folder not found - checking repository structure...${NC}"
    find /opt/odoo/repositories -type d -name "dist" 2>/dev/null
fi

# Restart Odoo to pick up new modules
service odoo restart

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
echo "Odoo ${ODOO_VERSION} installed with odoo-helper-scripts!"
echo ""
echo -e "${YELLOW}Installation Details:${NC}"
echo "  - Odoo Home:          /opt/odoo"
echo "  - Config File:        /opt/odoo/odoo.conf"
echo "  - Custom Addons:      /opt/odoo/custom_addons"
echo "  - Your Modules:       /opt/odoo/repositories/sojiabolarin/CRND/dist"
echo ""
echo -e "${YELLOW}Access Odoo:${NC}"
echo "  - URL: http://${SERVER_IP}:8069"
echo "  - Via Nginx: http://${SERVER_IP}"
echo ""
echo -e "${YELLOW}Service Commands:${NC}"
echo "  sudo service odoo start|stop|restart|status"
echo ""
echo -e "${YELLOW}odoo-helper Commands (run from /opt/odoo):${NC}"
echo "  cd /opt/odoo"
echo "  odoo-helper server status"
echo "  odoo-helper server restart"
echo "  odoo-helper server log"
echo "  odoo-helper db list"
echo "  odoo-helper addons list"
echo "  odoo-helper addons install -d <database> <module_name>"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Open http://${SERVER_IP}:8069"
echo "  2. Create your first database"
echo "  3. Go to Apps → Update Apps List"
echo "  4. Install your custom modules:"
echo ""
echo "     cd /opt/odoo"
echo "     odoo-helper addons install --dir /opt/odoo/repositories/sojiabolarin/CRND/dist -d <YOUR_DATABASE>"
echo ""
echo -e "${GREEN}Thank you for using WestMetro Limited solutions!${NC}"
echo ""
