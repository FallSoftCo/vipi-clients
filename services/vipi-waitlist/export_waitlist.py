#!/usr/bin/env python3
"""Export launch-list rows as CSV for an authorized operator."""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    db = Path(os.environ.get("VIPI_WAITLIST_DB", "/var/lib/vipi-waitlist/waitlist.sqlite3"))
    if not db.exists():
        raise SystemExit(f"No waitlist database at {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM waitlist ORDER BY first_created_at, id").fetchall()
    writer = csv.writer(sys.stdout)
    if rows:
        writer.writerow(rows[0].keys())
        writer.writerows([tuple(row) for row in rows])


if __name__ == "__main__":
    main()
