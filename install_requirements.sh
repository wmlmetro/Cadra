#!/bin/bash
# ============================================================
# myservice.com.ng — Complete Python Requirements Install
# Covers: Odoo 15, Bureaucrat ITSM, all custom modules
# Run as root on Ubuntu 22.04
# ============================================================

VENV="/opt/odoo/venv"
PIP="$VENV/bin/pip"
ODOO="$VENV/bin/python"

echo "=== Step 1: Upgrade pip, wheel, setuptools ==="
$PIP install --upgrade pip wheel "setuptools==67.8.0"

echo "=== Step 2: Install gevent FIRST (must precede requirements.txt) ==="
$PIP install --only-binary=:all: "gevent==22.10.2" "greenlet==2.0.2"

echo "=== Step 3: Odoo 15 core requirements ==="
$PIP install -r /opt/odoo/odoo/requirements.txt

echo "=== Step 4: Bureaucrat / CRND extras ==="
# html2text needed by generic_request
$PIP install html2text

# first package needed by some CRND modules
$PIP install first

echo "=== Step 5: Odoo standard extras ==="
$PIP install \
    PyPDF2 \
    Babel \
    chardet \
    cryptography \
    decorator \
    docutils \
    freezegun \
    geoip2 \
    idna \
    Jinja2 \
    libsass \
    lxml \
    Markdown \
    num2words \
    ofxparse \
    passlib \
    Pillow \
    polib \
    psutil \
    psycopg2-binary \
    pydot \
    pyOpenSSL \
    pyserial \
    python-dateutil \
    python-slugify \
    python-stdnum \
    pytz \
    qrcode \
    reportlab \
    requests \
    vobject \
    Werkzeug \
    xlrd \
    xlsxwriter \
    xlwt \
    zxcvbn \
    zope.interface \
    pdf2image \
    wkhtmltopdf

echo "=== Step 6: Custom module extras ==="
# myservice_osint — OSINT feeds
$PIP install \
    feedparser \
    beautifulsoup4 \
    lxml \
    requests

# myservice_ai_patterns — Claude API
$PIP install \
    anthropic

# myservice_barcode_station — barcode/QR
$PIP install \
    qrcode \
    python-barcode \
    Pillow

# myservice_asset_register — asset management
$PIP install \
    openpyxl

echo "=== Step 7: Verify critical packages ==="
$ODOO -c "import gevent; print('gevent:', gevent.__version__)"
$ODOO -c "import greenlet; print('greenlet:', greenlet.__version__)"
$ODOO -c "import pkg_resources; print('setuptools: OK')"
$ODOO -c "import lxml; print('lxml: OK')"
$ODOO -c "import PIL; print('Pillow: OK')"
$ODOO -c "import psycopg2; print('psycopg2: OK')"
$ODOO -c "import html2text; print('html2text: OK')"
$ODOO -c "import zope.interface; print('zope.interface: OK')"

echo ""
echo "=== All requirements installed ==="
echo "Next: create database and install modules"
