"""Apply one or more .sql files to the configured database, in order.

Usage: python scripts/apply_sql.py schema.sql sql/views.sql
"""

import sys

from src.rmagent.db import get_conn


def main(paths: list[str]) -> None:
    """Execute each .sql file (in order) against the configured DB in one transaction."""
    if not paths:
        raise SystemExit("usage: python scripts/apply_sql.py FILE.sql [FILE.sql ...]")
    with get_conn() as conn:
        for p in paths:
            with open(p, encoding="utf-8") as f:
                sql = f.read()
            with conn.cursor() as cur:
                cur.execute(sql)
        conn.commit()
    print(f"Applied: {', '.join(paths)}")


if __name__ == "__main__":
    main(sys.argv[1:])
