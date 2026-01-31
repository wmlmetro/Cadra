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
echo -e "\n${BLUE}[Step 1/7]${NC} Installing basic dependencies..."

apt-get update
apt-get install -y git wget curl sudo

#--------------------------------------------------
# Step 2: Clone Official CRND Deploy
#--------------------------------------------------
echo -e "\n${BLUE}[Step 2/7]${NC} Downloading CRND Deploy installer..."

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
echo -e "\n${BLUE}[Step 3/7]${NC} Installing Odoo ${ODOO_VERSION} with CRND Deploy..."
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
echo -e "\n${BLUE}[Step 4/7]${NC} Starting services..."

service postgresql start
service odoo start

#--------------------------------------------------
# Step 5: Configure Nginx
#--------------------------------------------------
echo -e "\n${BLUE}[Step 5/7]${NC} Configuring Nginx..."

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
# Step 6: Fetch Custom Modules Repository
#--------------------------------------------------
echo -e "\n${BLUE}[Step 6/7]${NC} Fetching custom modules from repository..."

cd /opt/odoo

# Create repositories directory if it doesn't exist
mkdir -p /opt/odoo/repositories
chown odoo:odoo /opt/odoo/repositories

# Fetch the custom CRND repository using odoo-helper
echo -e "${BLUE}Running: odoo-helper fetch --repo ${REPO_URL}${NC}"
sudo -u odoo odoo-helper fetch --repo ${REPO_URL} || true

# Wait a moment for fetch to complete
sleep 2

# Find the dist folder - check all possible paths
DIST_PATH=""

if [ -d "/opt/odoo/repositories/sojiabolarin/CRND/dist" ]; then
    DIST_PATH="/opt/odoo/repositories/sojiabolarin/CRND/dist"
    echo -e "${GREEN}Found dist at: ${DIST_PATH}${NC}"
elif [ -d "/opt/odoo/repositories/CRND/dist" ]; then
    DIST_PATH="/opt/odoo/repositories/CRND/dist"
    echo -e "${GREEN}Found dist at: ${DIST_PATH}${NC}"
else
    # Search for dist folder anywhere in repositories
    DIST_PATH=$(find /opt/odoo/repositories -type d -name "dist" 2>/dev/null | head -1)
    if [ -n "$DIST_PATH" ]; then
        echo -e "${GREEN}Found dist at: ${DIST_PATH}${NC}"
    fi
fi

# If still not found, clone directly
if [ -z "$DIST_PATH" ] || [ ! -d "$DIST_PATH" ]; then
    echo -e "${YELLOW}Dist folder not found via odoo-helper, cloning directly...${NC}"
    
    cd /opt/odoo/repositories
    rm -rf CRND
    sudo -u odoo git clone ${REPO_URL} CRND
    
    if [ -d "/opt/odoo/repositories/CRND/dist" ]; then
        DIST_PATH="/opt/odoo/repositories/CRND/dist"
        echo -e "${GREEN}Found dist at: ${DIST_PATH}${NC}"
    fi
fi

# Link modules from dist folder to custom_addons
if [ -n "$DIST_PATH" ] && [ -d "$DIST_PATH" ]; then
    echo -e "${BLUE}Linking modules from ${DIST_PATH} to /opt/odoo/custom_addons/${NC}"
    
    # Create custom_addons if it doesn't exist
    mkdir -p /opt/odoo/custom_addons
    chown odoo:odoo /opt/odoo/custom_addons
    
    # Create symlinks for each module in dist folder
    MODULE_COUNT=0
    for module_dir in ${DIST_PATH}/*/; do
        if [ -d "$module_dir" ]; then
            module_name=$(basename "$module_dir")
            # Remove trailing slash from module_dir
            module_dir="${module_dir%/}"
            
            # Remove existing symlink if present
            rm -f /opt/odoo/custom_addons/${module_name}
            
            # Create new symlink
            sudo -u odoo ln -sf "${module_dir}" /opt/odoo/custom_addons/${module_name}
            echo -e "  ✓ Linked: ${module_name}"
            MODULE_COUNT=$((MODULE_COUNT + 1))
        fi
    done
    
    echo -e "${GREEN}Successfully linked ${MODULE_COUNT} modules${NC}"
else
    echo -e "${RED}ERROR: Could not find dist folder!${NC}"
    echo -e "${YELLOW}Please manually run:${NC}"
    echo -e "  cd /opt/odoo/repositories"
    echo -e "  sudo -u odoo git clone ${REPO_URL}"
    echo -e "  # Then create symlinks from dist folder to custom_addons"
fi

#--------------------------------------------------
# Step 7: Update Addons List and Restart
#--------------------------------------------------
echo -e "\n${BLUE}[Step 7/7]${NC} Finalizing installation..."

cd /opt/odoo

# Verify symlinks were created
echo -e "${BLUE}Verifying symlinks in custom_addons:${NC}"
ls -la /opt/odoo/custom_addons/ | grep "^l" || echo "No symlinks found"

# Update the addons list
echo -e "${BLUE}Updating addons list...${NC}"
sudo -u odoo odoo-helper addons update-list || true

# Restart Odoo to pick up new modules
echo -e "${BLUE}Restarting Odoo...${NC}"
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
echo "  - Module Source:      ${DIST_PATH:-'Not found - check manually'}"
echo ""
echo -e "${YELLOW}Access Odoo:${NC}"
echo "  - Direct URL:  http://${SERVER_IP}:8069"
echo "  - Via Nginx:   http://${SERVER_IP}"
echo ""
echo -e "${YELLOW}Master Password:${NC} admin"
echo -e "${RED}  ⚠ CHANGE THIS IN PRODUCTION!${NC}"
echo "  Edit: /opt/odoo/odoo.conf → admin_passwd"
echo ""
echo -e "${YELLOW}Service Commands:${NC}"
echo "  sudo service odoo start|stop|restart|status"
echo ""
echo -e "${YELLOW}odoo-helper Commands (run from /opt/odoo):${NC}"
echo "  cd /opt/odoo"
echo "  sudo -u odoo odoo-helper server status"
echo "  sudo -u odoo odoo-helper server restart"
echo "  sudo -u odoo odoo-helper server log"
echo "  sudo -u odoo odoo-helper db list"
echo "  sudo -u odoo odoo-helper addons list"
echo "  sudo -u odoo odoo-helper addons update-list"
echo "  sudo -u odoo odoo-helper addons install -d <database> <module_name>"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Open http://${SERVER_IP}:8069"
echo "  2. Create your first database (master password: admin)"
echo "  3. Go to Settings → Activate Developer Mode"
echo "  4. Go to Apps → Update Apps List"
echo "  5. Remove 'Apps' filter in search bar"
echo "  6. Search and install your custom modules"
echo ""
echo -e "${GREEN}Thank you for using WestMetro Limited solutions!${NC}"
echo ""
