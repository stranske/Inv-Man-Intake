# Data Fixture Reset and Load Runbook

This runbook resets a local SQLite test database, loads data fixtures, and verifies row counts.

## Prerequisites

- Run commands from the repository root.
- Use Python 3.11+ with project dependencies installed.

## Fixture Files

- `tests/fixtures/data/firms.json`
- `tests/fixtures/data/funds.json`
- `tests/fixtures/data/documents.json`
- `tests/fixtures/data/core_seed_bundle.json`

## 1. Drop/Recreate the Test Database

```bash
rm -f /tmp/inv_man_fixtures.db
python - <<'PY'
import sqlite3
from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.migrations.provenance_history import apply_provenance_history_schema

conn = sqlite3.connect("/tmp/inv_man_fixtures.db")
conn.execute("PRAGMA foreign_keys = ON")
apply_core_schema(conn)
apply_provenance_history_schema(conn)
conn.close()
print("database recreated: /tmp/inv_man_fixtures.db")
PY
```

## 2. Load All Fixture Files

```bash
python - <<'PY'
import json
import sqlite3
from pathlib import Path
from inv_man_intake.data.fixtures import load_core_seed_rows

fixtures_dir = Path("tests/fixtures/data")
fixture = {
    "firms": json.loads((fixtures_dir / "firms.json").read_text(encoding="utf-8")),
    "funds": json.loads((fixtures_dir / "funds.json").read_text(encoding="utf-8")),
    "documents": json.loads((fixtures_dir / "documents.json").read_text(encoding="utf-8")),
}

conn = sqlite3.connect("/tmp/inv_man_fixtures.db")
conn.execute("PRAGMA foreign_keys = ON")
load_core_seed_rows(conn, fixture)
conn.close()
print("fixtures loaded into /tmp/inv_man_fixtures.db")
PY
```

## 3. Verify Successful Load with Row Counts

```bash
python - <<'PY'
import sqlite3

conn = sqlite3.connect("/tmp/inv_man_fixtures.db")
counts = {
    "firms": conn.execute("SELECT COUNT(*) FROM firms").fetchone()[0],
    "funds": conn.execute("SELECT COUNT(*) FROM funds").fetchone()[0],
    "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
}
conn.close()

for table, count in counts.items():
    print(f"{table}: {count}")

assert counts["firms"] >= 3
assert counts["funds"] >= 5
assert counts["documents"] >= 10
print("row-count verification passed")
PY
```

## 4. Optional: Reset and Reload in Place

```bash
python - <<'PY'
import json
import sqlite3
from pathlib import Path
from inv_man_intake.data.fixtures import load_core_seed_rows, reset_core_seed_tables

fixtures_dir = Path("tests/fixtures/data")
fixture = {
    "firms": json.loads((fixtures_dir / "firms.json").read_text(encoding="utf-8")),
    "funds": json.loads((fixtures_dir / "funds.json").read_text(encoding="utf-8")),
    "documents": json.loads((fixtures_dir / "documents.json").read_text(encoding="utf-8")),
}

conn = sqlite3.connect("/tmp/inv_man_fixtures.db")
conn.execute("PRAGMA foreign_keys = ON")
reset_core_seed_tables(conn)
load_core_seed_rows(conn, fixture)
conn.close()
print("reset + reload complete")
PY
```
