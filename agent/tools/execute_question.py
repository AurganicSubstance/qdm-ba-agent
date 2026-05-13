"""
CLI tool: Execute ONE question — direct DeepSeek SQL gen + DB execution + retry.
Usage: python -m agent.tools.execute_question <index>
Reads question from state, builds SQL, executes, retries once on error, saves result.
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.data_retriever import execute_question, _build_sql
from agent.config import STATE_FILE


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: python -m agent.tools.execute_question <index>"}, ensure_ascii=False))
        sys.exit(1)

    idx = int(sys.argv[1])
    today = __import__('datetime').datetime.now().strftime('%Y-%m-%d')

    # Read state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    else:
        print(json.dumps({"error": "state file not found"}, ensure_ascii=False))
        sys.exit(1)

    try:
        question = state["daily_runs"][today]["sent"][idx]
    except (KeyError, IndexError):
        print(json.dumps({"error": f"Question not found: {today}[{idx}]"}, ensure_ascii=False))
        sys.exit(1)

    # Execute
    result = execute_question(question)

    # Retry once on error
    if result["status"] == "error":
        try:
            sql = _build_sql(question)
            from src.tools.db_connector import create_connector_from_config, DBConnectorError
            db = create_connector_from_config()
            data = db.execute_query(sql)
            if data:
                columns = list(data[0].keys())
                rows = [[row.get(c) for c in columns] for row in data[:20]]
                result = {
                    "question_id": question["id"],
                    "status": "success",
                    "sql": sql,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(data),
                    "error": None,
                }
        except Exception as e:
            result["sql"] = sql if 'sql' in locals() else result["sql"]
            result["error"] = f"Retry also failed: {e}"

    # Save back to state
    question["sql"] = result["sql"]
    question["status"] = result["status"]
    question["columns"] = result.get("columns", [])
    question["row_count"] = result.get("row_count", 0)
    question["rows"] = result.get("rows", [])
    if result.get("error"):
        question["error"] = result["error"]

    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

    print(json.dumps({
        "ok": result["status"] == "success",
        "question_id": result["question_id"],
        "status": result["status"],
        "sql": result["sql"],
        "row_count": result.get("row_count", 0),
        "error": result.get("error"),
    }, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
