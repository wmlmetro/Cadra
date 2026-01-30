#!/bin/bash
################################################################################
# Odoo 15 Installation using CRND Deploy + odoo-helper-scripts
# With Custom CRND Repository: https://github.com/sojiabolarin/CRND
# WestMetro Limited
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}"
echo "================================================================================"
echo "   Odoo 15 Installation - CRND Deploy + odoo-helper-scripts"
echo "   Custom Repository: https://github.com/sojiabolarin/CRND"
echo "   WestMetro Limited"
echo "================================================================================"
echo -e "${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}" 
   exit 1
fi

#--------------------------------------------------
# Step 1: Install System Requirements
#--------------------------------------------------
echo -e "\n${BLUE}[Step 1/5]${NC} Installing system requirements..."
apt-get update && apt-get install -y sudo git wget curl

#--------------------------------------------------
# Step 2: Clone CRND Deploy
#--------------------------------------------------
echo -e "\n${BLUE}[Step 2/5]${NC} Cloning CRND Deploy script..."
cd /tmp
rm -rf crnd-deploy
git clone https://github.com/crnd-inc/crnd-deploy

#--------------------------------------------------
# Step 3: Run CRND Deploy for Odoo 15
#--------------------------------------------------
echo -e "\n${BLUE}[Step 3/5]${NC} Running CRND Deploy for Odoo 15.0..."
echo -e "${YELLOW}This will install Odoo 15, PostgreSQL, Nginx, and odoo-helper-scripts${NC}"

/tmp/crnd-deploy/crnd-deploy.bash \
    --odoo-version 15.0 \
    --odoo-branch 15.0 \
    --install-mode git \
    --local-postgres \
    --local-nginx \
    --proxy-mode \
    --workers 2

#--------------------------------------------------
# Step 4: Start Services
#--------------------------------------------------
echo -e "\n${BLUE}[Step 4/5]${NC} Starting services..."
systemctl start postgresql
systemctl enable postgresql

# Start Odoo service
systemctl start odoo
systemctl enable odoo

#--------------------------------------------------
# Step 5: Fetch Custom CRND Repository
#--------------------------------------------------
echo -e "\n${BLUE}[Step 5/5]${NC} Fetching custom CRND repository..."
cd /opt/odoo

# Fetch your custom CRND modules using odoo-helper
odoo-helper fetch https://github.com/sojiabolarin/CRND

# Link the addons (creates symlinks in custom_addons)
odoo-helper link https://github.com/sojiabolarin/CRND 2>/dev/null || true

# Restart Odoo to pick up new addons
systemctl restart odoo

#--------------------------------------------------
# Step 6: Configure Nginx
#--------------------------------------------------
echo -e "\n${BLUE}[Bonus]${NC} Configuring Nginx..."
cd /etc/nginx/sites-enabled

# Remove default site if exists
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Enable the generated Odoo config
HOSTNAME_SHORT=$(hostname -s)
if [ -f "/etc/nginx/sites-available/${HOSTNAME_SHORT}.conf" ]; then
    ln -sf "/etc/nginx/sites-available/${HOSTNAME_SHORT}.conf" ./
    systemctl restart nginx
    echo -e "${GREEN}Nginx configured with ${HOSTNAME_SHORT}.conf${NC}"
else
    echo -e "${YELLOW}Nginx config not found, you may need to configure manually${NC}"
fi

#--------------------------------------------------
# Print Summary
#--------------------------------------------------
echo -e "\n${GREEN}"
echo "================================================================================"
echo "                    Installation Complete!"
echo "================================================================================"
echo -e "${NC}"
echo ""
echo "Odoo 15 has been installed with odoo-helper-scripts!"
echo ""
echo "Installation Summary:"
echo "  - Odoo Version:       15.0"
echo "  - Install Directory:  /opt/odoo"
echo "  - Custom Addons:      /opt/odoo/custom_addons"
echo "  - Repositories:       /opt/odoo/repositories"
echo "  - CRND Modules:       /opt/odoo/repositories/sojiabolarin/CRND"
echo "  - Config File:        /opt/odoo/odoo.conf"
echo ""
echo "Service Commands:"
echo "  - Start:    sudo systemctl start odoo"
echo "  - Stop:     sudo systemctl stop odoo"
echo "  - Restart:  sudo systemctl restart odoo"
echo "  - Status:   sudo systemctl status odoo"
echo ""
echo "odoo-helper Commands (run from /opt/odoo):"
echo "  - cd /opt/odoo"
echo "  - odoo-helper server status"
echo "  - odoo-helper server restart"
echo "  - odoo-helper server log"
echo "  - odoo-helper db list"
echo "  - odoo-helper addons list"
echo "  - odoo-helper addons install -d <database> <addon_name>"
echo "  - odoo-helper addons update -d <database> <addon_name>"
echo ""
echo "Fetch More Addons:"
echo "  - odoo-helper fetch --oca <repo-name>           # OCA repos"
echo "  - odoo-helper fetch https://github.com/...     # Any git repo"
echo ""
echo "Access Odoo:"
echo "  - Direct:  http://your-server-ip:8069"
echo "  - Nginx:   http://your-server-ip (port 80)"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Access http://your-server-ip:8069"
echo "  2. Create your first database"
echo "  3. Go to Apps > Update Apps List"
echo "  4. Search and install your CRND modules"
echo ""
