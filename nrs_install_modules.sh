#!/bin/bash
################################################################################
# NRS Facilities — ITSM Modules Installer
# Installs all Bureaucrat/CRND ITSM modules and their dependencies
#
# Usage:
#   sudo bash nrs_install_modules.sh [--db <database>]
#
# WestMetro Limited
# Phone: +234 806 902 0996
# Email: info@westmetrong.com
# Website: www.westmetrong.com
################################################################################

set -e

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
DB_NAME="nrs-facilities"
ODOO_HOME="/opt/odoo"
VENV_PIP="${ODOO_HOME}/venv/bin/pip"
ODOO_USER="odoo"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --db) DB_NAME="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}"
echo "================================================================================"
echo "   NRS Facilities — ITSM Modules Installer"
echo "   Database: ${DB_NAME}"
echo "   Powered by WestMetro Limited"
echo "================================================================================"
echo -e "${NC}"

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Run as root: sudo bash nrs_install_modules.sh${NC}"
    exit 1
fi

cd ${ODOO_HOME}

# ─────────────────────────────────────────────
# Step 1 — System-level dependencies
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[1/6]${NC} Installing system packages..."

apt-get update -qq
apt-get install -y \
    poppler-utils \
    wkhtmltopdf \
    libpq-dev \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    libjpeg-dev \
    libfreetype6-dev \
    libmagic1 \
    zlib1g-dev \
    antiword \
    catdoc

echo -e "${GREEN}  ✓ System packages installed${NC}"

# ─────────────────────────────────────────────
# Step 2 — Python dependencies in Odoo venv
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[2/6]${NC} Installing Python packages into Odoo virtualenv..."

PYTHON_PACKAGES=(
    # PDF & document handling
    "PyPDF2"
    "pdf2image"
    "python-magic"
    "Pillow"
    "reportlab"
    "pdfminer.six"
    # Text processing
    "html2text"
    "beautifulsoup4"
    "lxml"
    "pytils"
    # Communication & formatting
    "phonenumbers"
    "vobject"
    "num2words"
    # Spreadsheet
    "xlrd"
    "xlwt"
    "xlsxwriter"
    "openpyxl"
    # Utilities
    "qrcode"
    "python-barcode"
    "pyserial"
    "Jinja2"
    "psutil"
    "decorator"
    "requests"
    "passlib"
    "babel"
    "python-dateutil"
    "pytz"
    "markupsafe"
    "werkzeug"
    "psycopg2-binary"
    "gevent"
    "greenlet"
)

for pkg in "${PYTHON_PACKAGES[@]}"; do
    echo -e "  ${CYAN}→ Installing: ${pkg}${NC}"
    ${VENV_PIP} install "${pkg}" --quiet 2>/dev/null && \
        echo -e "  ${GREEN}  ✓ ${pkg}${NC}" || \
        echo -e "  ${YELLOW}  ! ${pkg} — skipped (may already satisfy)${NC}"
done

echo -e "${GREEN}  ✓ Python packages done${NC}"

# ─────────────────────────────────────────────
# Step 3 — Install requirements from all repos
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[3/6]${NC} Installing requirements from repository files..."

# Find all requirements.txt files in the Odoo repos
REQ_FILES=$(find ${ODOO_HOME}/repositories -name "requirements.txt" 2>/dev/null)
REQ_FILES="${REQ_FILES} ${ODOO_HOME}/odoo/requirements.txt"

for req_file in ${REQ_FILES}; do
    if [ -f "$req_file" ]; then
        echo -e "  ${CYAN}→ Processing: ${req_file}${NC}"
        ${VENV_PIP} install -r "${req_file}" --quiet 2>/dev/null && \
            echo -e "  ${GREEN}  ✓ Done${NC}" || \
            echo -e "  ${YELLOW}  ! Some packages skipped${NC}"
    fi
done

echo -e "${GREEN}  ✓ Requirements files processed${NC}"

# ─────────────────────────────────────────────
# Step 4 — Update addons list
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[4/6]${NC} Updating addons list..."

sudo -u ${ODOO_USER} odoo-helper addons update-list
echo -e "${GREEN}  ✓ Addons list updated${NC}"

# ─────────────────────────────────────────────
# Step 5 — Install ITSM modules
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[5/6]${NC} Installing ITSM modules into database: ${DB_NAME}..."

# Core modules first — order matters for dependencies
ITSM_MODULES=(
    # ── Layer 1: Core framework ──────────────────────────────────
    "generic_mixin"
    "generic_condition"
    "generic_tag"
    "generic_rule"

    # ── Layer 2: Generic Request base ────────────────────────────
    "generic_request"
    "generic_request_kind"
    "generic_request_category"
    "generic_request_stage"
    "generic_request_stage_route"

    # ── Layer 3: Generic Service ─────────────────────────────────
    "generic_service"
    "generic_request_service"
    "generic_service_team"
    "generic_request_team"

    # ── Layer 4: Request features ────────────────────────────────
    "generic_request_priority"
    "generic_request_tag"
    "generic_request_mail"
    "generic_request_action_request"
    "generic_request_related_doc"
    "generic_request_parent"
    "generic_request_deadline"
    "generic_request_sla_log"
    "generic_request_assignment"

    # ── Layer 5: Knowledge base ──────────────────────────────────
    "bureaucrat_knowledge"
    "bureaucrat_knowledge_base"

    # ── Layer 6: Bureaucrat ITSM ─────────────────────────────────
    "bureaucrat_helpdesk_lite"
    "bureaucrat_helpdesk"
)

INSTALLED=0
FAILED=0
FAILED_MODULES=()

for module in "${ITSM_MODULES[@]}"; do
    echo -e "\n  ${CYAN}→ Installing: ${module}${NC}"

    # Check if module exists in addons path first
    MODULE_PATH=$(sudo -u ${ODOO_USER} odoo-helper addons path "${module}" 2>/dev/null || true)

    if [ -z "$MODULE_PATH" ]; then
        echo -e "  ${YELLOW}  ! Module not found in addons path: ${module} — skipping${NC}"
        continue
    fi

    # Install with odoo-helper
    if sudo -u ${ODOO_USER} odoo-helper addons install -d "${DB_NAME}" "${module}" 2>&1; then
        echo -e "  ${GREEN}  ✓ Installed: ${module}${NC}"
        INSTALLED=$((INSTALLED + 1))
    else
        echo -e "  ${RED}  ✗ Failed: ${module}${NC}"
        FAILED=$((FAILED + 1))
        FAILED_MODULES+=("${module}")
    fi
done

# ─────────────────────────────────────────────
# Step 6 — Restart Odoo
# ─────────────────────────────────────────────
echo -e "\n${BLUE}[6/6]${NC} Restarting Odoo..."
service odoo restart
sleep 3
echo -e "${GREEN}  ✓ Odoo restarted${NC}"

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo -e "\n${GREEN}"
echo "================================================================================"
echo "                    Module Installation Complete!"
echo "================================================================================"
echo -e "${NC}"
echo -e "${YELLOW}Results:${NC}"
echo "  Installed:  ${INSTALLED} modules"
echo "  Failed:     ${FAILED} modules"

if [ ${#FAILED_MODULES[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}  Failed modules:${NC}"
    for m in "${FAILED_MODULES[@]}"; do
        echo "    - ${m}"
    done
    echo ""
    echo -e "${YELLOW}  To retry a failed module:${NC}"
    echo "    sudo -u odoo odoo-helper addons install -d ${DB_NAME} <module_name>"
    echo ""
    echo -e "${YELLOW}  To check why a module failed:${NC}"
    echo "    sudo -u odoo odoo-helper addons check-requirements <module_name>"
fi

echo ""
echo -e "${YELLOW}Next Step — Run the NRS seed script:${NC}"
echo ""
echo "  sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell \\"
echo "      -c /opt/odoo/conf/odoo.conf \\"
echo "      -d ${DB_NAME} --no-http < /root/CRND/nrs_seed.py"
echo ""
echo -e "${YELLOW}Verify installed modules:${NC}"
echo "  sudo -u odoo odoo-helper addons list -d ${DB_NAME} --installed"
echo ""
echo -e "${GREEN}Powered by WestMetro Limited | www.westmetrong.com${NC}"
echo ""
