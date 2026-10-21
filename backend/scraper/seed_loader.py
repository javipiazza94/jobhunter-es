"""
scraper/seed_loader.py — Loads companies_public_salary.json into the DB.
Run: python -m scraper.seed_loader
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SEEDS_PATH
from database import get_conn, init_db, upsert_company

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_seed() -> int:
    companies = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    conn = get_conn()
    init_db(conn)
    count = 0
    for c in companies:
        upsert_company(conn, {**c, "source": "seed", "salary_transparent": 1})
        count += 1
        logger.info("  ✓ %s", c["name"])
    conn.close()
    logger.info("Seed complete: %d companies loaded.", count)
    return count


if __name__ == "__main__":
    load_seed()
