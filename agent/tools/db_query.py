"""
CLI tool: Execute SQL against the database via REST API.
Usage: python -m agent.tools.db_query "SELECT ..." [--limit N]
Output: JSON array of rows to stdout, or {"error": "..."} on failure.
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.tools.db_connector import create_connector_from_config, DBConnectorError
from agent.config import MAX_RESULT_ROWS


def main():
    args = sys.argv[1:]

    limit = MAX_RESULT_ROWS
    sql = None

    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif sql is None:
            sql = args[i]
            i += 1
        else:
            sql += " " + args[i]
            i += 1

    if not sql or not sql.strip():
        print(json.dumps({"error": "No SQL provided"}, ensure_ascii=False))
        sys.exit(1)

    try:
        db = create_connector_from_config()
        rows = db.execute_query(sql.strip())

        if not rows:
            print(json.dumps([], ensure_ascii=False))
            sys.exit(0)

        if len(rows) > limit:
            print(json.dumps(rows[:limit], ensure_ascii=False, default=str))
            print(f"[WARN] Truncated from {len(rows)} to {limit} rows", file=sys.stderr)
        else:
            print(json.dumps(rows, ensure_ascii=False, default=str))

    except DBConnectorError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Unexpected: {e}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
