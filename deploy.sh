#!/bin/bash
# =============================================================================
#  WestMetro Limited — myservice.com.ng Deploy Script
#  Usage:
#    bash deploy.sh              → pull + deploy homepage only
#    bash deploy.sh --seed       → pull + deploy homepage + run seed
#    bash deploy.sh --seed --db myservice.com.ng  → specify database
# =============================================================================

set -e

REPO_DIR="/root/CRND"
BRANCH="15.0"
WEB_ROOT="/var/www/html"
ODOO_DIR="/opt/odoo"
ODOO_CONF="/opt/odoo/conf/odoo.conf"
ODOO_BIN="/opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin"
DEFAULT_DB="myservice.com.ng"
SEED_SCRIPT="myservice_master_seed.py"
HOMEPAGE="index.html"

# Colours
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
NC="\033[0m"

# Parse args
RUN_SEED=false
DB="$DEFAULT_DB"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --seed)   RUN_SEED=true ;;
        --db)     DB="$2"; shift ;;
        *)        echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
    shift
done

echo ""
echo "============================================================"
echo "  myservice.com.ng — Deploy"
echo "  WestMetro Limited | www.westmetrong.com"
echo "============================================================"
echo ""

# ── STEP 1: Pull latest from GitHub ──────────────────────────────
echo -e "${CYAN}[1/4] Pulling latest from GitHub (branch: $BRANCH)...${NC}"
cd "$REPO_DIR"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"
echo -e "${GREEN}  ✓ Repo up to date${NC}"
echo ""

# ── STEP 2: Deploy homepage ───────────────────────────────────────
echo -e "${CYAN}[2/4] Deploying homepage...${NC}"

if [ -f "$REPO_DIR/$HOMEPAGE" ]; then
    mkdir -p "$WEB_ROOT"
    cp "$REPO_DIR/$HOMEPAGE" "$WEB_ROOT/index.html"
    echo -e "${GREEN}  ✓ index.html → $WEB_ROOT/index.html${NC}"
else
    echo -e "${YELLOW}  ! $HOMEPAGE not found in repo — skipping homepage deploy${NC}"
fi
echo ""

# ── STEP 3: Reload Nginx ──────────────────────────────────────────
echo -e "${CYAN}[3/4] Reloading Nginx...${NC}"
if nginx -t 2>/dev/null; then
    service nginx reload
    echo -e "${GREEN}  ✓ Nginx reloaded${NC}"
else
    echo -e "${RED}  ✗ Nginx config has errors — skipping reload${NC}"
    nginx -t
fi
echo ""

# ── STEP 4: Run seed (optional) ───────────────────────────────────
if [ "$RUN_SEED" = true ]; then
    echo -e "${CYAN}[4/4] Running master seed on database: $DB...${NC}"

    if [ ! -f "$REPO_DIR/$SEED_SCRIPT" ]; then
        echo -e "${RED}  ✗ $SEED_SCRIPT not found in $REPO_DIR${NC}"
        exit 1
    fi

    # Check DB exists
    DB_EXISTS=$(cd /tmp && sudo -u odoo psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -w "$DB" | wc -l)
    if [ "$DB_EXISTS" -eq 0 ]; then
        echo -e "${RED}  ✗ Database '$DB' not found. Create it first via Odoo database manager.${NC}"
        exit 1
    fi

    cd "$ODOO_DIR"
    sudo -u odoo $ODOO_BIN shell \
        -c "$ODOO_CONF" \
        -d "$DB" \
        --no-http < "$REPO_DIR/$SEED_SCRIPT"

    echo -e "${GREEN}  ✓ Seed complete on $DB${NC}"
else
    echo -e "${CYAN}[4/4] Skipping seed (use --seed flag to run)${NC}"
fi

echo ""
echo "============================================================"
echo -e "${GREEN}  ✓ Deploy complete${NC}"
echo ""
echo "  Homepage:  https://myservice.com.ng"
echo "  Portal:    https://myservice.com.ng/web"
echo ""
echo "  To run seed next time:"
echo "  bash $REPO_DIR/deploy.sh --seed"
echo "  bash $REPO_DIR/deploy.sh --seed --db myservice.com.ng"
echo "============================================================"
echo ""
