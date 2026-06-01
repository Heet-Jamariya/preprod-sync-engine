#!/bin/bash

# =============================================================
# DB REFRESH AUTOMATION — RESTORE & SANITIZE
# =============================================================
# This script:
#   1. Auto-creates virtual environment if not exists
#   2. Auto-installs all dependencies
#   3. Restores the production backup into pre-production
#   4. Automatically runs the Python sanitizer
# =============================================================
# HOW TO RUN:
#   bash restore_and_sanitize.sh
# =============================================================

set -e  # Exit immediately if any command fails


# =============================================================
# HOW TO SWITCH BETWEEN PROJECTS
# =============================================================
# For PostgreSQL project → keep POSTGRES block active, comment out MYSQL block
# For MySQL project     → keep MYSQL block active, comment out POSTGRES block
# Only ONE block should be active at a time
# =============================================================


# =============================================================
# POSTGRES PROJECT (Sub-project 1) — CURRENTLY ACTIVE
# =============================================================
BACKUP_FILE="/home/nishi/Desktop/production_test_backup.sql"  # path to your postgres backup file
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="preprod_test"                                        # your postgres pre-prod DB name
DB_USER="postgres"                                            # your postgres username
DB_PASSWORD="admin123"                                        # your postgres password
DB_TYPE="postgres"


# =============================================================
# MYSQL PROJECT (Sub-project 2) — COMMENTED OUT
# =============================================================
# To activate: remove # from lines below
# and add # to all lines in POSTGRES block above
#
# BACKUP_FILE="/home/nishi/Desktop/mysql_backup.sql"          # path to your mysql backup file
# DB_HOST="localhost"
# DB_PORT="3306"
# DB_NAME="preprod_db"                                        # your mysql pre-prod DB name
# DB_USER="root"                                              # your mysql username
# DB_PASSWORD="yourpassword"                                  # your mysql password
# DB_TYPE="mysql"


# =============================================================
# COLORS FOR OUTPUT
# =============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================
# HELPER FUNCTIONS
# =============================================================

log_info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $1"; }

# =============================================================
# STEP 1 — AUTO SETUP VIRTUAL ENVIRONMENT
# =============================================================

log_info "=========================================="
log_info "DB Refresh Automation — Starting"
log_info "=========================================="

VENV_DIR=".venv"
PYTHON="$VENV_DIR/Scripts/python"    # Windows path
PIP="$VENV_DIR/Scripts/pip"          # Windows path

# If .venv doesn't exist, create it automatically
if [ ! -d "$VENV_DIR" ]; then
    log_info "Virtual environment not found. Creating .venv automatically..."
    python -m venv "$VENV_DIR"
    log_success "Virtual environment created."
else
    log_info "Virtual environment found."
fi

# Always install/update dependencies
log_info "Installing dependencies..."
"$PIP" install -r requirements.txt --quiet
log_success "Dependencies ready."

# =============================================================
# STEP 2 — PRE-FLIGHT CHECKS
# =============================================================

# Check backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup file not found: $BACKUP_FILE"
    log_error "Please update BACKUP_FILE path at the top of this script."
    exit 1
fi

# Check sanitize.py exists
if [ ! -f "sanitize.py" ]; then
    log_error "sanitize.py not found. Make sure you are running this from the project folder."
    exit 1
fi

# Check .env exists
if [ ! -f ".env" ]; then
    log_error ".env file not found. Please make sure it exists in the project folder."
    exit 1
fi

# Check requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    log_error "requirements.txt not found. Please make sure it exists in the project folder."
    exit 1
fi

log_success "Pre-flight checks passed."

# =============================================================
# STEP 3 — RESTORE PRODUCTION BACKUP INTO PRE-PRODUCTION
# =============================================================

log_info "Restoring production backup into '$DB_NAME'..."
log_info "Backup file: $BACKUP_FILE"

PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -f "$BACKUP_FILE"

log_success "Database restore complete."

# =============================================================
# STEP 4 — RUN PYTHON SANITIZER
# =============================================================

log_info "=========================================="
log_info "Launching Python Sanitizer..."
log_info "=========================================="

"$PYTHON" sanitize.py

# Check if sanitizer exited successfully
if [ $? -eq 0 ]; then
    log_info "=========================================="
    log_success "DB Refresh Complete!"
    log_success "Pre-production database is ready to use."
    log_info "=========================================="
else
    log_error "Sanitizer failed. Check logs/sanitizer.log for details."
    exit 1
fi