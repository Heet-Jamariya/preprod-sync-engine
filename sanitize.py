import os
import json
import time
import logging
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy import inspect

# =============================================================
# STEP 1 — LOAD ENVIRONMENT VARIABLES
# =============================================================

load_dotenv()

ENVIRONMENT    = os.getenv("ENVIRONMENT", "").upper()
DB_TYPE        = os.getenv("DB_TYPE", "").lower()
DB_HOST        = os.getenv("DB_HOST", "localhost")
DB_PORT        = os.getenv("DB_PORT", "5432")
DB_NAME        = os.getenv("DB_NAME", "")
DB_USER        = os.getenv("DB_USER", "")
DB_PASSWORD    = os.getenv("DB_PASSWORD", "")
RETRY_INTERVAL = int(os.getenv("DB_RETRY_INTERVAL", "5"))
MAX_RETRIES    = int(os.getenv("DB_MAX_RETRIES", "20"))

# =============================================================
# STEP 2 — SETUP LOGGING
# =============================================================

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/sanitizer.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# =============================================================
# STEP 3 — PRODUCTION SAFETY CHECK
# =============================================================

def check_environment_safety():
    logger.info(f"Environment detected: {ENVIRONMENT}")

    if ENVIRONMENT == "PRODUCTION":
        logger.error("=" * 60)
        logger.error("SAFETY ABORT: ENVIRONMENT is set to PRODUCTION.")
        logger.error("This script must NEVER run against production database.")
        logger.error("Change ENVIRONMENT in .env to PREPRODUCTION or DEV.")
        logger.error("=" * 60)
        sys.exit(1)

    if not ENVIRONMENT:
        logger.error("ENVIRONMENT variable is not set in .env — aborting.")
        sys.exit(1)

    logger.info(f"Safety check passed. Running on: {ENVIRONMENT}")

# =============================================================
# STEP 4 — BUILD DATABASE CONNECTION URL
# =============================================================

def build_connection_url():
    if not DB_TYPE:
        logger.error("DB_TYPE is not set in .env — must be 'postgres' or 'mysql'.")
        sys.exit(1)

    if DB_TYPE == "postgres":
        url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        logger.info("Database engine detected: PostgreSQL")

    elif DB_TYPE == "mysql":
        url = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        logger.info("Database engine detected: MySQL")

    else:
        logger.error(f"Unknown DB_TYPE '{DB_TYPE}' in .env — must be 'postgres' or 'mysql'.")
        sys.exit(1)

    return url

# =============================================================
# STEP 5 — WAIT FOR DATABASE TO COME ONLINE
# =============================================================

def wait_for_database(engine):
    logger.info(f"Waiting for database '{DB_NAME}' to come online...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"Database is online. (attempt {attempt})")
            return

        except OperationalError:
            logger.info(f"[{attempt}/{MAX_RETRIES}] Database not ready yet — retrying in {RETRY_INTERVAL}s...")
            time.sleep(RETRY_INTERVAL)

    logger.error(f"Database did not come online after {MAX_RETRIES} attempts. Aborting.")
    sys.exit(1)

# =============================================================
# STEP 6 — LOAD CONFIG
# =============================================================

def load_config():
    config_path = "config.json"

    if not os.path.exists(config_path):
        logger.error("config.json not found. Please create it before running.")
        sys.exit(1)

    with open(config_path, "r") as f:
        config = json.load(f)

    patches = config.get("patches", [])

    if not patches:
        logger.error("No patches defined in config.json — nothing to do.")
        sys.exit(1)

    logger.info(f"Config loaded. Total patch rules found: {len(patches)}")
    return patches

# =============================================================
# STEP 7 — VALIDATE TABLE AND COLUMNS
# =============================================================

def validate_patch(inspector, patch):
    table   = patch.get("table")
    columns = patch.get("set", {})

    # Check table exists
    available_tables = inspector.get_table_names()
    if table not in available_tables:
        raise ValueError(f"Table '{table}' does not exist in the database.")

    # Check each column exists in that table
    available_columns = [col["name"] for col in inspector.get_columns(table)]
    for col in columns.keys():
        if col not in available_columns:
            raise ValueError(f"Column '{col}' does not exist in table '{table}'.")

    logger.info(f"Validation passed for table '{table}'.")

# =============================================================
# STEP 8 — BUILD DYNAMIC SQL QUERY
# =============================================================

def build_query(patch):
    table      = patch.get("table")
    set_values = patch.get("set", {})
    where      = patch.get("where", "").strip()

    # Safely quote table name
    quoted_table = f'"{table}"'

    # Build SET clause with parameterized values
    set_parts  = []
    params     = {}

    for col, val in set_values.items():
        param_key = f"val_{col}"
        set_parts.append(f'"{col}" = :{param_key}')
        params[param_key] = val

    set_clause = ", ".join(set_parts)

    # Build final query
    if where:
        query = f'UPDATE {quoted_table} SET {set_clause} WHERE {where}'
    else:
        query = f'UPDATE {quoted_table} SET {set_clause}'

    return query, params

# =============================================================
# STEP 9 — APPLY ALL PATCHES INSIDE ONE TRANSACTION
# =============================================================

def apply_patches(engine, patches):
    logger.info("Starting sanitization. Opening transaction...")

    try:
        with engine.begin() as conn:
            inspector = inspect(engine)

            for patch in patches:
                table = patch.get("table")

                # Validate first
                validate_patch(inspector, patch)

                # Build query
                query, params = build_query(patch)

                # Execute
                logger.info(f"Patching table '{table}' — Query: {query} | Params: {params}")
                result = conn.execute(text(query), params)

                logger.info(f"Table '{table}' — {result.rowcount} rows updated.")

        logger.info("=" * 60)
        logger.info("All patches applied successfully. Transaction committed.")
        logger.info("=" * 60)

    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        logger.error("Transaction rolled back. No changes made.")
        sys.exit(1)

    except SQLAlchemyError as e:
        logger.error(f"Database error during patching: {e}")
        logger.error("Transaction rolled back. No changes made.")
        sys.exit(1)

# =============================================================
# MAIN
# =============================================================

def main():
    logger.info("=" * 60)
    logger.info("DB Refresh Sanitizer — Starting")
    logger.info("=" * 60)

    # Step 3 — Safety check
    check_environment_safety()

    # Step 4 — Build connection URL
    connection_url = build_connection_url()

    # Create engine
    engine = create_engine(connection_url)

    # Step 5 — Wait for DB
    wait_for_database(engine)

    # Step 6 — Load config
    patches = load_config()

    # Step 9 — Apply patches
    apply_patches(engine, patches)

    logger.info("Sanitizer finished. Pre-production database is ready.")


if __name__ == "__main__":
    main()